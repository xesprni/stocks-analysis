"""News feed routes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from market_reporter.api.deps import get_config
from market_reporter.config import AppConfig, NewsSource, normalize_source_id
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.models import NewsSourceTable
from market_reporter.infra.db.session import get_engine
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.news.schemas import (
    NewsFeedResponse,
    NewsFeedSourceOptionView,
)
from market_reporter.modules.news.service import NewsService

router = APIRouter(prefix="/api", tags=["news-feed"])


def _load_news_sources(config: AppConfig) -> List[NewsSource]:
    """Load news sources from database."""
    engine = get_engine(config.database.url)
    with Session(engine) as session:
        rows = session.exec(select(NewsSourceTable).order_by(NewsSourceTable.id)).all()
        return [
            NewsSource(
                source_id=row.source_id,
                name=row.name,
                category=row.category,
                url=row.url,
                enabled=row.enabled,
            )
            for row in rows
        ]


def _disable_failed_news_sources(config: AppConfig, warnings: List[str]) -> List[str]:
    failed_source_ids: set[str] = set()
    for warning in warnings:
        matched = re.search(r"News source failed \[id=([^;\]]+);", warning)
        if not matched:
            continue
        source_id = normalize_source_id(matched.group(1))
        if source_id:
            failed_source_ids.add(source_id)

    if not failed_source_ids:
        return []

    engine = get_engine(config.database.url)
    disabled_ids: List[str] = []
    with Session(engine) as session:
        for sid in failed_source_ids:
            row = session.exec(
                select(NewsSourceTable).where(
                    NewsSourceTable.source_id == sid,
                    NewsSourceTable.enabled == True,  # noqa: E712
                )
            ).first()
            if row is not None:
                row.enabled = False
                row.updated_at = datetime.utcnow
                session.add(row)
                disabled_ids.append(sid)
        if disabled_ids:
            session.commit()

    if disabled_ids:
        return [f"Auto-disabled failed sources: {', '.join(sorted(disabled_ids))}"]
    return []


@router.get("/news-feed/options", response_model=List[NewsFeedSourceOptionView])
async def news_feed_options(
    config: AppConfig = Depends(get_config),
) -> List[NewsFeedSourceOptionView]:
    sources = _load_news_sources(config)
    return [
        NewsFeedSourceOptionView(
            source_id=source.source_id or "",
            name=source.name,
            enabled=source.enabled,
        )
        for source in sources
    ]


@router.get("/news-feed", response_model=NewsFeedResponse)
async def news_feed(
    source_id: str = Query("ALL", min_length=1, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    config: AppConfig = Depends(get_config),
) -> NewsFeedResponse:
    news_sources = _load_news_sources(config)
    selected_source_id = (
        "ALL" if source_id.upper() == "ALL" else normalize_source_id(source_id)
    )
    async with HttpClient(
        timeout_seconds=config.request_timeout_seconds,
        user_agent=config.user_agent,
    ) as client:
        service = NewsService(
            config=config,
            client=client,
            registry=ProviderRegistry(),
            news_sources=news_sources,
        )
        try:
            items, warnings, selected = await service.collect_feed(
                limit=limit,
                source_id=selected_source_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    disable_notes = _disable_failed_news_sources(config=config, warnings=warnings)
    if disable_notes:
        warnings = [*warnings, *disable_notes]

    return NewsFeedResponse(
        items=items,
        warnings=warnings,
        selected_source_id=selected,
    )
