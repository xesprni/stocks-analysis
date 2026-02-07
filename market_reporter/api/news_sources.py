"""News sources CRUD routes — backed by SQLite."""

from __future__ import annotations

from datetime import datetime
from typing import List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from market_reporter.api.deps import get_config
from market_reporter.config import AppConfig, normalize_source_id
from market_reporter.infra.db.models import NewsSourceTable
from market_reporter.infra.db.session import get_engine
from market_reporter.modules.news.schemas import (
    NewsSourceCreateRequest,
    NewsSourceUpdateRequest,
    NewsSourceView,
)

router = APIRouter(prefix="/api", tags=["news-sources"])


def _validate_source_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid source url. Only http/https URLs are supported.")
    return url


def _next_source_id(session: Session, name: str) -> str:
    used_ids: set[str] = set()
    rows = session.exec(select(NewsSourceTable.source_id)).all()
    for row in rows:
        used_ids.add(row)
    base_id = normalize_source_id(name)
    source_id = base_id
    cursor = 2
    while source_id in used_ids:
        source_id = f"{base_id}-{cursor}"
        cursor += 1
    return source_id


def _to_view(row: NewsSourceTable) -> NewsSourceView:
    return NewsSourceView(
        source_id=row.source_id,
        name=row.name,
        category=row.category,
        url=row.url,
        enabled=row.enabled,
    )


def _get_session(config: AppConfig = Depends(get_config)) -> Session:
    engine = get_engine(config.database.url)
    return Session(engine)


@router.get("/news-sources", response_model=List[NewsSourceView])
async def list_news_sources(
    config: AppConfig = Depends(get_config),
) -> List[NewsSourceView]:
    engine = get_engine(config.database.url)
    with Session(engine) as session:
        rows = session.exec(select(NewsSourceTable).order_by(NewsSourceTable.id)).all()
        return [_to_view(row) for row in rows]


@router.post("/news-sources", response_model=NewsSourceView)
async def create_news_source(
    payload: NewsSourceCreateRequest,
    config: AppConfig = Depends(get_config),
) -> NewsSourceView:
    engine = get_engine(config.database.url)
    with Session(engine) as session:
        try:
            url = _validate_source_url(payload.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        source_id = _next_source_id(session, payload.name)
        now = datetime.utcnow()
        row = NewsSourceTable(
            source_id=source_id,
            name=payload.name.strip(),
            category=payload.category.strip(),
            url=url,
            enabled=payload.enabled,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_view(row)


@router.patch("/news-sources/{source_id}", response_model=NewsSourceView)
async def update_news_source(
    source_id: str,
    payload: NewsSourceUpdateRequest,
    config: AppConfig = Depends(get_config),
) -> NewsSourceView:
    normalized_source_id = normalize_source_id(source_id)
    engine = get_engine(config.database.url)
    with Session(engine) as session:
        row = session.exec(
            select(NewsSourceTable).where(
                NewsSourceTable.source_id == normalized_source_id
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"News source not found: {source_id}"
            )

        try:
            if payload.name is not None:
                row.name = payload.name.strip()
            if payload.category is not None:
                row.category = payload.category.strip()
            if payload.url is not None:
                row.url = _validate_source_url(payload.url)
            if payload.enabled is not None:
                row.enabled = payload.enabled
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_view(row)


@router.delete("/news-sources/{source_id}")
async def delete_news_source(
    source_id: str,
    config: AppConfig = Depends(get_config),
) -> dict:
    normalized_source_id = normalize_source_id(source_id)
    engine = get_engine(config.database.url)
    with Session(engine) as session:
        row = session.exec(
            select(NewsSourceTable).where(
                NewsSourceTable.source_id == normalized_source_id
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"News source not found: {source_id}"
            )
        session.delete(row)
        session.commit()
        return {"deleted": True}
