from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from market_reporter.config import AppConfig, NewsSource, normalize_source_id
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis_engine.schemas import (
    AnalysisProviderView,
    ProviderAuthStartRequest,
    ProviderAuthStartResponse,
    ProviderAuthStatusView,
    ProviderModelsView,
    ProviderModelSelectionRequest,
    ProviderSecretRequest,
    StockAnalysisHistoryItem,
    StockAnalysisRunRequest,
    StockAnalysisRunView,
    StockAnalysisTaskStatus,
    StockAnalysisTaskView,
)
from market_reporter.modules.analysis_engine.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.news.schemas import (
    NewsFeedResponse,
    NewsFeedSourceOptionView,
    NewsSourceCreateRequest,
    NewsSourceUpdateRequest,
    NewsSourceView,
)
from market_reporter.modules.news_listener.schemas import (
    NewsAlertStatusUpdateRequest,
    NewsAlertView,
    NewsListenerRunView,
)
from market_reporter.modules.news_listener.service import NewsListenerService
from market_reporter.modules.reports.service import ReportService
from market_reporter.modules.symbol_search.schemas import StockSearchResult
from market_reporter.modules.symbol_search.service import SymbolSearchService
from market_reporter.modules.watchlist.schemas import (
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistUpdateRequest,
)
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.schemas import (
    ConfigUpdateRequest,
    ReportRunDetail,
    ReportRunSummary,
    ReportRunTaskView,
    RunRequest,
    RunResult,
    UIOptionsResponse,
)
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings

try:
    from market_reporter.modules.news_listener.scheduler import NewsListenerScheduler
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency guard
    NewsListenerScheduler = None  # type: ignore[assignment]


def create_app() -> FastAPI:
    settings = AppSettings()
    config_store = ConfigStore(config_path=settings.config_file)
    report_service = ReportService(config_store=config_store)

    app = FastAPI(
        title="Market Reporter Admin API",
        version="0.2.0",
        default_response_class=ORJSONResponse,
    )
    app.state.settings = settings
    app.state.config_store = config_store
    app.state.report_service = report_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.news_listener_lock = asyncio.Lock()
    app.state.stock_analysis_lock = asyncio.Lock()
    app.state.stock_analysis_tasks: Dict[str, StockAnalysisTaskView] = {}
    app.state.stock_analysis_handles: Dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _ensure_database(config: AppConfig) -> None:
        init_db(config.database.url)

    def _build_listener_query_service(config: AppConfig) -> NewsListenerService:
        registry = ProviderRegistry()
        market_data_service = MarketDataService(config=config, registry=registry)
        watchlist_service = WatchlistService(config)
        analysis_service = AnalysisService(
            config=config,
            registry=registry,
            market_data_service=market_data_service,
        )
        return NewsListenerService(
            config=config,
            registry=registry,
            news_service=None,
            watchlist_service=watchlist_service,
            market_data_service=market_data_service,
            analysis_service=analysis_service,
        )

    async def _run_news_listener_cycle() -> NewsListenerRunView:
        lock = app.state.news_listener_lock
        if lock.locked():
            raise ValueError("News listener task is already running")
        async with lock:
            config = config_store.load()
            async with HttpClient(
                timeout_seconds=config.request_timeout_seconds,
                user_agent=config.user_agent,
            ) as client:
                registry = ProviderRegistry()
                news_service = NewsService(
                    config=config, client=client, registry=registry
                )
                market_data_service = MarketDataService(
                    config=config, registry=registry
                )
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

    async def _run_stock_analysis_once(
        symbol: str, payload: StockAnalysisRunRequest
    ) -> StockAnalysisRunView:
        config = config_store.load()
        _ensure_database(config)
        async with HttpClient(
            timeout_seconds=config.request_timeout_seconds,
            user_agent=config.user_agent,
        ) as client:
            registry = ProviderRegistry()
            news_service = NewsService(config=config, client=client, registry=registry)
            fund_flow_service = FundFlowService(
                config=config, client=client, registry=registry
            )
            market_data_service = MarketDataService(config=config, registry=registry)
            analysis_service = AnalysisService(
                config=config,
                registry=registry,
                market_data_service=market_data_service,
                news_service=news_service,
                fund_flow_service=fund_flow_service,
            )
            return await analysis_service.run_stock_analysis(
                symbol=symbol,
                market=payload.market,
                provider_id=payload.provider_id,
                model=payload.model,
                interval=payload.interval,
                lookback_bars=payload.lookback_bars,
            )

    async def _update_stock_analysis_task(
        task_id: str,
        status: StockAnalysisTaskStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        result: Optional[StockAnalysisRunView] = None,
        error_message: Optional[str] = None,
    ) -> None:
        async with app.state.stock_analysis_lock:
            current = app.state.stock_analysis_tasks.get(task_id)
            if current is None:
                return

            update_payload = {
                "status": status,
                "error_message": error_message
                if error_message is not None
                else current.error_message,
            }
            if started_at is not None:
                update_payload["started_at"] = started_at
            if finished_at is not None:
                update_payload["finished_at"] = finished_at
            if result is not None:
                update_payload["result"] = result
            app.state.stock_analysis_tasks[task_id] = current.model_copy(
                update=update_payload
            )

    async def _run_stock_analysis_task(
        task_id: str,
        symbol: str,
        payload: StockAnalysisRunRequest,
    ) -> None:
        await _update_stock_analysis_task(
            task_id=task_id,
            status=StockAnalysisTaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            error_message=None,
        )
        try:
            result = await _run_stock_analysis_once(symbol=symbol, payload=payload)
            await _update_stock_analysis_task(
                task_id=task_id,
                status=StockAnalysisTaskStatus.SUCCEEDED,
                finished_at=datetime.now(timezone.utc),
                result=result,
                error_message=None,
            )
        except Exception as exc:
            await _update_stock_analysis_task(
                task_id=task_id,
                status=StockAnalysisTaskStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )

    async def _start_stock_analysis_task(
        symbol: str, payload: StockAnalysisRunRequest
    ) -> StockAnalysisTaskView:
        task_id = uuid4().hex
        task_view = StockAnalysisTaskView(
            task_id=task_id,
            symbol=symbol.strip().upper(),
            market=payload.market.upper(),
            status=StockAnalysisTaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        async with app.state.stock_analysis_lock:
            app.state.stock_analysis_tasks[task_id] = task_view

        task_payload = payload.model_copy(deep=True)
        task = asyncio.create_task(
            _run_stock_analysis_task(
                task_id=task_id,
                symbol=symbol,
                payload=task_payload,
            )
        )
        app.state.stock_analysis_handles[task_id] = task
        task.add_done_callback(
            lambda _: app.state.stock_analysis_handles.pop(task_id, None)
        )
        return task_view

    async def _get_stock_analysis_task(task_id: str) -> StockAnalysisTaskView:
        async with app.state.stock_analysis_lock:
            task = app.state.stock_analysis_tasks.get(task_id)
            if task is None:
                raise FileNotFoundError(f"Stock analysis task not found: {task_id}")
            return task

    def _restart_listener_scheduler(config: AppConfig) -> None:
        existing = getattr(app.state, "news_listener_scheduler", None)
        if existing is not None:
            existing.shutdown()
        if NewsListenerScheduler is None:
            app.state.news_listener_scheduler = None
            return
        scheduler = NewsListenerScheduler(
            config=config, run_func=_run_news_listener_cycle
        )
        scheduler.start()
        app.state.news_listener_scheduler = scheduler

    @staticmethod
    def _validate_source_url(raw_url: str) -> str:
        url = raw_url.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Invalid source url. Only http/https URLs are supported.")
        return url

    @staticmethod
    def _next_source_id(existing: List[NewsSource], name: str) -> str:
        used_ids = {source.source_id for source in existing if source.source_id}
        base_id = normalize_source_id(name)
        source_id = base_id
        cursor = 2
        while source_id in used_ids:
            source_id = f"{base_id}-{cursor}"
            cursor += 1
        return source_id

    @staticmethod
    def _to_news_source_view(source: NewsSource) -> NewsSourceView:
        return NewsSourceView(
            source_id=source.source_id or "",
            name=source.name,
            category=source.category,
            url=source.url,
            enabled=source.enabled,
        )

    def _disable_failed_news_sources(
        config: AppConfig, warnings: List[str]
    ) -> tuple[AppConfig, List[str]]:
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

    @app.on_event("startup")
    async def startup_event() -> None:
        config = config_store.load()
        _ensure_database(config)
        _restart_listener_scheduler(config)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        scheduler = getattr(app.state, "news_listener_scheduler", None)
        if scheduler is not None:
            scheduler.shutdown()
        handles = list(app.state.stock_analysis_handles.values())
        for handle in handles:
            if not handle.done():
                handle.cancel()
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/config", response_model=AppConfig)
    async def get_config() -> AppConfig:
        return config_store.load()

    @app.put("/api/config", response_model=AppConfig)
    async def update_config(payload: ConfigUpdateRequest) -> AppConfig:
        current = config_store.load()
        updated = payload.to_config(current)
        saved = config_store.save(updated)
        _ensure_database(saved)
        _restart_listener_scheduler(saved)
        return saved

    @app.get("/api/news-sources", response_model=List[NewsSourceView])
    async def list_news_sources() -> List[NewsSourceView]:
        config = config_store.load()
        return [_to_news_source_view(source) for source in config.news_sources]

    @app.post("/api/news-sources", response_model=NewsSourceView)
    async def create_news_source(payload: NewsSourceCreateRequest) -> NewsSourceView:
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
        _ensure_database(saved)
        created = next(
            (item for item in saved.news_sources if item.source_id == source.source_id),
            source,
        )
        return _to_news_source_view(created)

    @app.patch("/api/news-sources/{source_id}", response_model=NewsSourceView)
    async def update_news_source(
        source_id: str, payload: NewsSourceUpdateRequest
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
        saved = config_store.save(
            config.model_copy(update={"news_sources": next_sources})
        )
        _ensure_database(saved)
        item = next(
            (
                row
                for row in saved.news_sources
                if row.source_id == normalized_source_id
            ),
            updated,
        )
        return _to_news_source_view(item)

    @app.delete("/api/news-sources/{source_id}")
    async def delete_news_source(source_id: str) -> dict:
        config = config_store.load()
        normalized_source_id = normalize_source_id(source_id)
        next_sources = [
            row for row in config.news_sources if row.source_id != normalized_source_id
        ]
        if len(next_sources) == len(config.news_sources):
            raise HTTPException(
                status_code=404, detail=f"News source not found: {source_id}"
            )
        saved = config_store.save(
            config.model_copy(update={"news_sources": next_sources})
        )
        _ensure_database(saved)
        _restart_listener_scheduler(saved)
        return {"deleted": True}

    @app.get("/api/news-feed/options", response_model=List[NewsFeedSourceOptionView])
    async def news_feed_options() -> List[NewsFeedSourceOptionView]:
        config = config_store.load()
        return [
            NewsFeedSourceOptionView(
                source_id=source.source_id or "",
                name=source.name,
                enabled=source.enabled,
            )
            for source in config.news_sources
        ]

    @app.get("/api/news-feed", response_model=NewsFeedResponse)
    async def news_feed(
        source_id: str = Query("ALL", min_length=1, max_length=120),
        limit: int = Query(50, ge=1, le=200),
    ) -> NewsFeedResponse:
        config = config_store.load()
        selected_source_id = (
            "ALL" if source_id.upper() == "ALL" else normalize_source_id(source_id)
        )
        async with HttpClient(
            timeout_seconds=config.request_timeout_seconds,
            user_agent=config.user_agent,
        ) as client:
            service = NewsService(
                config=config, client=client, registry=ProviderRegistry()
            )
            try:
                items, warnings, selected = await service.collect_feed(
                    limit=limit,
                    source_id=selected_source_id,
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        config, disable_notes = _disable_failed_news_sources(
            config=config, warnings=warnings
        )
        if disable_notes:
            warnings = [*warnings, *disable_notes]

        return NewsFeedResponse(
            items=items,
            warnings=warnings,
            selected_source_id=selected,
        )

    @app.post("/api/reports/run", response_model=RunResult)
    async def run_report(payload: Optional[RunRequest] = None) -> RunResult:
        return await report_service.run_report(overrides=payload)

    @app.post("/api/reports/run/async", response_model=ReportRunTaskView)
    async def run_report_async(
        payload: Optional[RunRequest] = None,
    ) -> ReportRunTaskView:
        return await report_service.start_report_async(overrides=payload)

    @app.get("/api/reports/tasks", response_model=List[ReportRunTaskView])
    async def list_report_tasks() -> List[ReportRunTaskView]:
        return await report_service.list_report_tasks()

    @app.get("/api/reports/tasks/{task_id}", response_model=ReportRunTaskView)
    async def get_report_task(task_id: str) -> ReportRunTaskView:
        try:
            return await report_service.get_report_task(task_id=task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/reports", response_model=List[ReportRunSummary])
    async def list_reports() -> List[ReportRunSummary]:
        return report_service.list_reports()

    @app.get("/api/reports/{run_id}", response_model=ReportRunDetail)
    async def get_report(run_id: str) -> ReportRunDetail:
        try:
            return report_service.get_report(run_id=run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/reports/{run_id}")
    async def delete_report(run_id: str) -> dict:
        try:
            deleted = report_service.delete_report(run_id=run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"deleted": deleted}

    @app.get("/api/reports/{run_id}/markdown", response_class=PlainTextResponse)
    async def get_report_markdown(run_id: str) -> str:
        try:
            return report_service.get_report(run_id=run_id).report_markdown
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/watchlist", response_model=List[WatchlistItem])
    async def list_watchlist() -> List[WatchlistItem]:
        config = config_store.load()
        service = WatchlistService(config)
        return service.list_items()

    @app.post("/api/watchlist", response_model=WatchlistItem)
    async def create_watchlist_item(payload: WatchlistCreateRequest) -> WatchlistItem:
        config = config_store.load()
        service = WatchlistService(config)
        try:
            return service.add_item(
                symbol=payload.symbol,
                market=payload.market,
                alias=payload.alias,
                display_name=payload.display_name,
                keywords=payload.keywords,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/watchlist/{item_id}", response_model=WatchlistItem)
    async def update_watchlist_item(
        item_id: int, payload: WatchlistUpdateRequest
    ) -> WatchlistItem:
        config = config_store.load()
        service = WatchlistService(config)
        try:
            return service.update_item(
                item_id=item_id,
                alias=payload.alias,
                enabled=payload.enabled,
                display_name=payload.display_name,
                keywords=payload.keywords,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/watchlist/{item_id}")
    async def delete_watchlist_item(item_id: int) -> dict:
        config = config_store.load()
        service = WatchlistService(config)
        deleted = service.delete_item(item_id=item_id)
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Watchlist item not found: {item_id}"
            )
        return {"deleted": True}

    @app.get("/api/stocks/search", response_model=List[StockSearchResult])
    async def stock_search(
        q: str = Query(..., min_length=1),
        market: str = Query("ALL", pattern="^(ALL|CN|HK|US)$"),
        limit: int = Query(20, ge=1, le=100),
    ) -> List[StockSearchResult]:
        config = config_store.load()
        _ensure_database(config)
        service = SymbolSearchService(config=config, registry=ProviderRegistry())
        try:
            return await service.search(query=q, market=market, limit=limit)
        except Exception:
            return []

    @app.get("/api/stocks/{symbol}/quote")
    async def stock_quote(
        symbol: str, market: str = Query(..., pattern="^(CN|HK|US)$")
    ):
        config = config_store.load()
        _ensure_database(config)
        service = MarketDataService(config=config, registry=ProviderRegistry())
        try:
            return await service.get_quote(symbol=symbol, market=market)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/stocks/{symbol}/kline")
    async def stock_kline(
        symbol: str,
        market: str = Query(..., pattern="^(CN|HK|US)$"),
        interval: str = Query("1m", pattern="^(1m|5m|1d)$"),
        limit: int = Query(300, ge=20, le=1000),
    ):
        config = config_store.load()
        _ensure_database(config)
        service = MarketDataService(config=config, registry=ProviderRegistry())
        return await service.get_kline(
            symbol=symbol, market=market, interval=interval, limit=limit
        )

    @app.get("/api/stocks/{symbol}/curve")
    async def stock_curve(
        symbol: str,
        market: str = Query(..., pattern="^(CN|HK|US)$"),
        window: str = Query("1d"),
    ):
        config = config_store.load()
        _ensure_database(config)
        service = MarketDataService(config=config, registry=ProviderRegistry())
        return await service.get_curve(symbol=symbol, market=market, window=window)

    @app.post("/api/news-listener/run", response_model=NewsListenerRunView)
    async def run_news_listener_once() -> NewsListenerRunView:
        try:
            return await _run_news_listener_cycle()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/news-listener/runs", response_model=List[NewsListenerRunView])
    async def list_news_listener_runs(
        limit: int = Query(50, ge=1, le=200),
    ) -> List[NewsListenerRunView]:
        config = config_store.load()
        service = _build_listener_query_service(config)
        return service.list_runs(limit=limit)

    @app.get("/api/news-alerts", response_model=List[NewsAlertView])
    async def list_news_alerts(
        status: str = Query("UNREAD", pattern="^(UNREAD|READ|DISMISSED|ALL)$"),
        symbol: str = Query("", max_length=32),
        market: str = Query("", pattern="^(CN|HK|US)?$"),
        limit: int = Query(50, ge=1, le=200),
    ) -> List[NewsAlertView]:
        config = config_store.load()
        service = _build_listener_query_service(config)
        return service.list_alerts(
            status=status,
            symbol=symbol or None,
            market=market or None,
            limit=limit,
        )

    @app.patch("/api/news-alerts/{alert_id}", response_model=NewsAlertView)
    async def update_news_alert(
        alert_id: int, payload: NewsAlertStatusUpdateRequest
    ) -> NewsAlertView:
        config = config_store.load()
        service = _build_listener_query_service(config)
        try:
            return service.update_alert_status(alert_id=alert_id, status=payload.status)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/news-alerts/mark-all-read")
    async def mark_news_alerts_read() -> dict:
        config = config_store.load()
        service = _build_listener_query_service(config)
        changed = service.mark_all_read()
        return {"updated": changed}

    @app.get("/api/providers/analysis", response_model=List[AnalysisProviderView])
    async def analysis_providers() -> List[AnalysisProviderView]:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        return service.list_providers()

    @app.put("/api/providers/analysis/default", response_model=AppConfig)
    async def update_default_analysis(
        payload: ProviderModelSelectionRequest,
    ) -> AppConfig:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        try:
            service.ensure_provider_ready(provider_id=payload.provider_id, model=None)
            models_view = await service.list_provider_models(
                provider_id=payload.provider_id
            )
            if models_view.models and payload.model not in models_view.models:
                raise ValueError(f"Model not found in provider models: {payload.model}")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        next_config = config.model_copy(
            update={
                "analysis": config.analysis.model_copy(
                    update={
                        "default_provider": payload.provider_id,
                        "default_model": payload.model,
                    }
                )
            }
        )
        return config_store.save(next_config)

    @app.put("/api/providers/analysis/{provider_id}/secret")
    async def put_analysis_secret(
        provider_id: str, payload: ProviderSecretRequest
    ) -> dict:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        try:
            service.put_secret(provider_id=provider_id, api_key=payload.api_key)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post(
        "/api/providers/analysis/{provider_id}/auth/start",
        response_model=ProviderAuthStartResponse,
    )
    async def start_analysis_auth(
        provider_id: str,
        request: Request,
        payload: Optional[ProviderAuthStartRequest] = None,
    ) -> ProviderAuthStartResponse:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        callback_url = str(
            request.url_for("analysis_auth_callback", provider_id=provider_id)
        )
        try:
            return await service.start_provider_auth(
                provider_id=provider_id,
                callback_url=callback_url,
                redirect_to=payload.redirect_to if payload else None,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/providers/analysis/{provider_id}/auth/status",
        response_model=ProviderAuthStatusView,
    )
    async def analysis_auth_status(provider_id: str) -> ProviderAuthStatusView:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        try:
            return await service.get_provider_auth_status(provider_id=provider_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/providers/analysis/{provider_id}/auth/callback",
        response_class=HTMLResponse,
        name="analysis_auth_callback",
    )
    async def analysis_auth_callback(
        provider_id: str,
        request: Request,
        state: str = Query(..., min_length=8),
        code: Optional[str] = Query(None),
        error: Optional[str] = Query(None),
    ) -> str:
        if error:
            return (
                "<html><body><h3>Login failed</h3>"
                f"<p>{error}</p><p>You can close this page.</p></body></html>"
            )

        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        callback_url = str(
            request.url_for("analysis_auth_callback", provider_id=provider_id)
        )
        params = {key: value for key, value in request.query_params.items()}
        try:
            await service.complete_provider_auth(
                provider_id=provider_id,
                state=state,
                code=code,
                callback_url=callback_url,
                query_params=params,
            )
            return (
                "<html><body><h3>Login succeeded</h3>"
                "<p>You can close this page and return to the app.</p>"
                "<script>window.close();</script></body></html>"
            )
        except Exception as exc:
            return (
                "<html><body><h3>Login failed</h3>"
                f"<p>{str(exc)}</p><p>You can close this page.</p></body></html>"
            )

    @app.post("/api/providers/analysis/{provider_id}/auth/logout")
    async def logout_analysis_auth(provider_id: str) -> dict:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        deleted = await service.logout_provider_auth(provider_id=provider_id)
        return {"deleted": deleted}

    @app.get(
        "/api/providers/analysis/{provider_id}/models",
        response_model=ProviderModelsView,
    )
    async def analysis_provider_models(provider_id: str) -> ProviderModelsView:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        try:
            return await service.list_provider_models(provider_id=provider_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/providers/analysis/{provider_id}/secret")
    async def delete_analysis_secret(provider_id: str) -> dict:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        deleted = service.delete_secret(provider_id=provider_id)
        return {"deleted": deleted}

    @app.delete("/api/providers/analysis/{provider_id}", response_model=AppConfig)
    async def delete_analysis_provider(provider_id: str) -> AppConfig:
        config = config_store.load()
        providers = config.analysis.providers
        if not any(item.provider_id == provider_id for item in providers):
            raise HTTPException(
                status_code=404, detail=f"Provider not found: {provider_id}"
            )
        if len(providers) <= 1:
            raise HTTPException(
                status_code=400, detail="At least one analysis provider must remain."
            )

        next_providers = [item for item in providers if item.provider_id != provider_id]
        enabled_providers = [item for item in next_providers if item.enabled]
        if not enabled_providers:
            first = next_providers[0].model_copy(update={"enabled": True})
            next_providers = [first, *next_providers[1:]]
            enabled_providers = [first]

        provider_map = {item.provider_id: item for item in next_providers}
        next_default_provider = config.analysis.default_provider
        if (
            next_default_provider not in provider_map
            or not provider_map[next_default_provider].enabled
        ):
            next_default_provider = enabled_providers[0].provider_id
        next_default_model = config.analysis.default_model
        default_cfg = provider_map[next_default_provider]
        if default_cfg.models and next_default_model not in default_cfg.models:
            next_default_model = default_cfg.models[0]

        next_config = config.model_copy(
            update={
                "analysis": config.analysis.model_copy(
                    update={
                        "providers": next_providers,
                        "default_provider": next_default_provider,
                        "default_model": next_default_model,
                    }
                )
            }
        )
        saved = config_store.save(next_config)
        _ensure_database(saved)
        service = AnalysisService(config=saved, registry=ProviderRegistry())
        await service.logout_provider_auth(provider_id=provider_id)
        service.delete_secret(provider_id=provider_id)
        return saved

    @app.post(
        "/api/analysis/stocks/{symbol}/run/async", response_model=StockAnalysisTaskView
    )
    async def run_stock_analysis_async(
        symbol: str, payload: StockAnalysisRunRequest
    ) -> StockAnalysisTaskView:
        return await _start_stock_analysis_task(symbol=symbol, payload=payload)

    @app.get(
        "/api/analysis/stocks/tasks/{task_id}", response_model=StockAnalysisTaskView
    )
    async def stock_analysis_task(task_id: str) -> StockAnalysisTaskView:
        try:
            return await _get_stock_analysis_task(task_id=task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/analysis/stocks/{symbol}/run", response_model=StockAnalysisRunView)
    async def run_stock_analysis(
        symbol: str, payload: StockAnalysisRunRequest
    ) -> StockAnalysisRunView:
        try:
            return await _run_stock_analysis_once(symbol=symbol, payload=payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/analysis/stocks/{symbol}/history",
        response_model=List[StockAnalysisHistoryItem],
    )
    async def stock_analysis_history(
        symbol: str,
        market: str = Query(..., pattern="^(CN|HK|US)$"),
        limit: int = Query(20, ge=1, le=100),
    ) -> List[StockAnalysisHistoryItem]:
        config = config_store.load()
        _ensure_database(config)
        service = AnalysisService(config=config, registry=ProviderRegistry())
        return service.list_history(symbol=symbol, market=market, limit=limit)

    @app.get("/api/options/ui", response_model=UIOptionsResponse)
    async def ui_options() -> UIOptionsResponse:
        config = config_store.load()
        analysis_provider_ids = sorted(
            provider.provider_id for provider in config.analysis.providers
        )
        return UIOptionsResponse(
            markets=["ALL", "CN", "HK", "US"],
            intervals=["1m", "5m", "1d"],
            timezones=[
                "Asia/Shanghai",
                "UTC",
                "America/New_York",
                "Europe/London",
                "Asia/Hong_Kong",
            ],
            news_providers=["rss"],
            fund_flow_providers=["eastmoney", "fred"],
            market_data_providers=["composite", "akshare", "yfinance"],
            analysis_providers=analysis_provider_ids,
            analysis_models_by_provider={},
            listener_threshold_presets=[1.0, 1.5, 2.0, 3.0, 5.0],
            listener_intervals=[5, 10, 15, 30, 60],
        )

    frontend_dist = Path(settings.frontend_dist)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def index() -> str:
            return (
                "<h2>Market Reporter Admin API</h2>"
                "<p>Frontend not built. Start frontend dev server from <code>frontend/</code>.</p>"
            )

    return app


app = create_app()
