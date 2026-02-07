"""Market Reporter API package — FastAPI application factory."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from market_reporter.api.stock_analysis_tasks import StockAnalysisTaskManager
from market_reporter.infra.db.session import init_db
from market_reporter.modules.reports.service import ReportService
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings

try:
    from market_reporter.modules.news_listener.scheduler import NewsListenerScheduler
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency guard
    NewsListenerScheduler = None  # type: ignore[assignment]

from market_reporter.api import (
    analysis,
    config,
    health,
    news_feed,
    news_listener,
    news_sources,
    providers,
    reports,
    stocks,
    watchlist,
)


def create_app() -> FastAPI:
    settings = AppSettings()
    config_store = ConfigStore(config_path=settings.config_file)
    report_service = ReportService(config_store=config_store)

    app = FastAPI(
        title="Market Reporter Admin API",
        version="0.2.0",
        default_response_class=ORJSONResponse,
    )

    # ---------- state --------------------------------------------------------
    app.state.settings = settings
    app.state.config_store = config_store
    app.state.report_service = report_service
    app.state.news_listener_lock = asyncio.Lock()
    app.state.stock_analysis_task_manager = StockAnalysisTaskManager(config_store)

    # ---------- CORS ---------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- routers ------------------------------------------------------
    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(news_sources.router)
    app.include_router(news_feed.router)
    app.include_router(reports.router)
    app.include_router(watchlist.router)
    app.include_router(stocks.router)
    app.include_router(news_listener.router)
    app.include_router(providers.router)
    app.include_router(analysis.router)

    # ---------- news listener cycle wrapper ----------------------------------
    # The scheduler needs a zero-arg async callable.  The router-level
    # ``_run_news_listener_cycle`` expects (config_store, lock), so we bind
    # those here and store the wrapper on ``app.state`` for the scheduler and
    # for ``config.py``'s ``_restart_listener_scheduler``.

    async def _run_news_listener_cycle_wrapper():
        return await news_listener._run_news_listener_cycle(
            config_store=config_store,
            lock=app.state.news_listener_lock,
        )

    app.state._run_news_listener_cycle = _run_news_listener_cycle_wrapper

    # ---------- scheduler helper ---------------------------------------------
    def _start_scheduler(app_inst: FastAPI) -> None:
        cfg = config_store.load()
        if NewsListenerScheduler is None:
            app_inst.state.news_listener_scheduler = None
            return
        scheduler = NewsListenerScheduler(
            config=cfg,
            run_func=app_inst.state._run_news_listener_cycle,
        )
        scheduler.start()
        app_inst.state.news_listener_scheduler = scheduler

    # ---------- lifecycle events ---------------------------------------------
    @app.on_event("startup")
    async def startup_event() -> None:
        cfg = config_store.load()
        init_db(cfg.database.url)
        _start_scheduler(app)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        # Stop scheduler
        scheduler = getattr(app.state, "news_listener_scheduler", None)
        if scheduler is not None:
            scheduler.shutdown()

        # Cancel in-flight stock analysis tasks
        task_manager: StockAnalysisTaskManager = app.state.stock_analysis_task_manager
        await task_manager.cancel_all()

    # ---------- static files / fallback UI -----------------------------------
    frontend_dist = Path(settings.frontend_dist)
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def index() -> str:
            return (
                "<h2>Market Reporter Admin API</h2>"
                "<p>Frontend not built. Start frontend dev server from "
                "<code>frontend/</code>.</p>"
            )

    return app


app = create_app()
