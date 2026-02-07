"""News listener and news alerts routes."""

from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from market_reporter.api.deps import build_listener_query_service, get_config_store
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis_engine.service import AnalysisService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.news_listener.schemas import (
    NewsAlertStatusUpdateRequest,
    NewsAlertView,
    NewsListenerRunView,
)
from market_reporter.modules.news_listener.service import NewsListenerService
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["news-listener"])


async def _run_news_listener_cycle(
    config_store: ConfigStore, lock: asyncio.Lock
) -> NewsListenerRunView:
    if lock.locked():
        raise ValueError("News listener task is already running")
    async with lock:
        config = config_store.load()
        async with HttpClient(
            timeout_seconds=config.request_timeout_seconds,
            user_agent=config.user_agent,
        ) as client:
            registry = ProviderRegistry()
            news_service = NewsService(config=config, client=client, registry=registry)
            market_data_service = MarketDataService(config=config, registry=registry)
            watchlist_service = WatchlistService(config)
            analysis_service = AnalysisService(
                config=config,
                registry=registry,
                market_data_service=market_data_service,
            )
            listener_service = NewsListenerService(
                config=config,
                registry=registry,
                news_service=news_service,
                watchlist_service=watchlist_service,
                market_data_service=market_data_service,
                analysis_service=analysis_service,
            )
            return await listener_service.run_once()


@router.post("/news-listener/run", response_model=NewsListenerRunView)
async def run_news_listener_once(
    request: Request,
    config_store: ConfigStore = Depends(get_config_store),
) -> NewsListenerRunView:
    try:
        return await _run_news_listener_cycle(
            config_store=config_store,
            lock=request.app.state.news_listener_lock,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/news-listener/runs", response_model=List[NewsListenerRunView])
async def list_news_listener_runs(
    limit: int = Query(50, ge=1, le=200),
    config_store: ConfigStore = Depends(get_config_store),
) -> List[NewsListenerRunView]:
    config = config_store.load()
    service = build_listener_query_service(config)
    return service.list_runs(limit=limit)


@router.get("/news-alerts", response_model=List[NewsAlertView])
async def list_news_alerts(
    status: str = Query("UNREAD", pattern="^(UNREAD|READ|DISMISSED|ALL)$"),
    symbol: str = Query("", max_length=32),
    market: str = Query("", pattern="^(CN|HK|US)?$"),
    limit: int = Query(50, ge=1, le=200),
    config_store: ConfigStore = Depends(get_config_store),
) -> List[NewsAlertView]:
    config = config_store.load()
    service = build_listener_query_service(config)
    return service.list_alerts(
        status=status,
        symbol=symbol or None,
        market=market or None,
        limit=limit,
    )


@router.patch("/news-alerts/{alert_id}", response_model=NewsAlertView)
async def update_news_alert(
    alert_id: int,
    payload: NewsAlertStatusUpdateRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> NewsAlertView:
    config = config_store.load()
    service = build_listener_query_service(config)
    try:
        return service.update_alert_status(alert_id=alert_id, status=payload.status)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/news-alerts/mark-all-read")
async def mark_news_alerts_read(
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    service = build_listener_query_service(config)
    changed = service.mark_all_read()
    return {"updated": changed}
