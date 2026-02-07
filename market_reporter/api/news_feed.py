"""News feed routes."""

from __future__ import annotations

import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from market_reporter.api.deps import get_config_store
from market_reporter.config import normalize_source_id
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.news.schemas import (
    NewsFeedResponse,
    NewsFeedSourceOptionView,
)
from market_reporter.modules.news.service import NewsService
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["news-feed"])


def _disable_failed_news_sources(
    config_store: ConfigStore, config, warnings: List[str]
) -> tuple:
    from market_reporter.config import NewsSource

    failed_source_ids: set[str] = set()
    for warning in warnings:
        matched = re.search(r"News source failed \[id=([^;\]]+);", warning)
        if not matched:
            continue
        source_id = normalize_source_id(matched.group(1))
        if source_id:
            failed_source_ids.add(source_id)

    if not failed_source_ids:
        return config, []

    updated_sources: List[NewsSource] = []
    disabled_ids: List[str] = []
    for source in config.news_sources:
        if source.source_id in failed_source_ids and source.enabled:
            updated_sources.append(source.model_copy(update={"enabled": False}))
            if source.source_id:
                disabled_ids.append(source.source_id)
        else:
            updated_sources.append(source)

    if not disabled_ids:
        return config, []

    next_config = config.model_copy(update={"news_sources": updated_sources})
    saved = config_store.save(next_config)
    notes = [f"Auto-disabled failed sources: {', '.join(sorted(disabled_ids))}"]
    return saved, notes


@router.get("/news-feed/options", response_model=List[NewsFeedSourceOptionView])
async def news_feed_options(
    config_store: ConfigStore = Depends(get_config_store),
) -> List[NewsFeedSourceOptionView]:
    config = config_store.load()
    return [
        NewsFeedSourceOptionView(
            source_id=source.source_id or "",
            name=source.name,
            enabled=source.enabled,
        )
        for source in config.news_sources
    ]


@router.get("/news-feed", response_model=NewsFeedResponse)
async def news_feed(
    source_id: str = Query("ALL", min_length=1, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    config_store: ConfigStore = Depends(get_config_store),
) -> NewsFeedResponse:
    config = config_store.load()
    selected_source_id = (
        "ALL" if source_id.upper() == "ALL" else normalize_source_id(source_id)
    )
    async with HttpClient(
        timeout_seconds=config.request_timeout_seconds,
        user_agent=config.user_agent,
    ) as client:
        service = NewsService(config=config, client=client, registry=ProviderRegistry())
        try:
            items, warnings, selected = await service.collect_feed(
                limit=limit,
                source_id=selected_source_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    config, disable_notes = _disable_failed_news_sources(
        config_store=config_store, config=config, warnings=warnings
    )
    if disable_notes:
        warnings = [*warnings, *disable_notes]

    return NewsFeedResponse(
        items=items,
        warnings=warnings,
        selected_source_id=selected,
    )
