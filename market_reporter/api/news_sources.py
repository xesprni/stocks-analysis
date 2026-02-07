"""News sources CRUD routes."""

from __future__ import annotations

import re
from typing import List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from market_reporter.api.deps import get_config_store
from market_reporter.config import AppConfig, NewsSource, normalize_source_id
from market_reporter.infra.db.session import init_db
from market_reporter.modules.news.schemas import (
    NewsSourceCreateRequest,
    NewsSourceUpdateRequest,
    NewsSourceView,
)
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["news-sources"])


def _validate_source_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid source url. Only http/https URLs are supported.")
    return url


def _next_source_id(existing: List[NewsSource], name: str) -> str:
    used_ids = {source.source_id for source in existing if source.source_id}
    base_id = normalize_source_id(name)
    source_id = base_id
    cursor = 2
    while source_id in used_ids:
        source_id = f"{base_id}-{cursor}"
        cursor += 1
    return source_id


def _to_news_source_view(source: NewsSource) -> NewsSourceView:
    return NewsSourceView(
        source_id=source.source_id or "",
        name=source.name,
        category=source.category,
        url=source.url,
        enabled=source.enabled,
    )


@router.get("/news-sources", response_model=List[NewsSourceView])
async def list_news_sources(
    config_store: ConfigStore = Depends(get_config_store),
) -> List[NewsSourceView]:
    config = config_store.load()
    return [_to_news_source_view(source) for source in config.news_sources]


@router.post("/news-sources", response_model=NewsSourceView)
async def create_news_source(
    payload: NewsSourceCreateRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> NewsSourceView:
    config = config_store.load()
    try:
        source = NewsSource(
            source_id=_next_source_id(config.news_sources, payload.name),
            name=payload.name.strip(),
            category=payload.category.strip(),
            url=_validate_source_url(payload.url),
            enabled=payload.enabled,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    next_config = config.model_copy(
        update={"news_sources": [*config.news_sources, source]}
    )
    saved = config_store.save(next_config)
    init_db(saved.database.url)
    created = next(
        (item for item in saved.news_sources if item.source_id == source.source_id),
        source,
    )
    return _to_news_source_view(created)


@router.patch("/news-sources/{source_id}", response_model=NewsSourceView)
async def update_news_source(
    source_id: str,
    payload: NewsSourceUpdateRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> NewsSourceView:
    config = config_store.load()
    normalized_source_id = normalize_source_id(source_id)
    target = next(
        (
            item
            for item in config.news_sources
            if item.source_id == normalized_source_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"News source not found: {source_id}"
        )

    try:
        updated = target.model_copy(
            update={
                "name": payload.name.strip()
                if payload.name is not None
                else target.name,
                "category": payload.category.strip()
                if payload.category is not None
                else target.category,
                "url": _validate_source_url(payload.url)
                if payload.url is not None
                else target.url,
                "enabled": payload.enabled
                if payload.enabled is not None
                else target.enabled,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    next_sources = [
        updated if item.source_id == normalized_source_id else item
        for item in config.news_sources
    ]
    saved = config_store.save(config.model_copy(update={"news_sources": next_sources}))
    init_db(saved.database.url)
    item = next(
        (row for row in saved.news_sources if row.source_id == normalized_source_id),
        updated,
    )
    return _to_news_source_view(item)


@router.delete("/news-sources/{source_id}")
async def delete_news_source(
    source_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    normalized_source_id = normalize_source_id(source_id)
    next_sources = [
        row for row in config.news_sources if row.source_id != normalized_source_id
    ]
    if len(next_sources) == len(config.news_sources):
        raise HTTPException(
            status_code=404, detail=f"News source not found: {source_id}"
        )
    saved = config_store.save(config.model_copy(update={"news_sources": next_sources}))
    init_db(saved.database.url)
    return {"deleted": True}
