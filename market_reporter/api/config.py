"""Config routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from market_reporter.api.deps import get_config_store
from market_reporter.config import AppConfig
from market_reporter.infra.db.session import init_db
from market_reporter.schemas import ConfigUpdateRequest
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", response_model=AppConfig)
async def get_config(
    config_store: ConfigStore = Depends(get_config_store),
) -> AppConfig:
    return config_store.load()


@router.put("/config", response_model=AppConfig)
async def update_config(
    payload: ConfigUpdateRequest,
    request: Request,
    config_store: ConfigStore = Depends(get_config_store),
) -> AppConfig:
    current = config_store.load()
    updated = payload.to_config(current)
    saved = config_store.save(updated)
    init_db(saved.database.url)

    # Restart news listener scheduler if available
    _restart_listener_scheduler(request.app.state, saved)
    return saved


def _restart_listener_scheduler(app_state, config: AppConfig) -> None:
    existing = getattr(app_state, "news_listener_scheduler", None)
    if existing is not None:
        existing.shutdown()

    try:
        from market_reporter.modules.news_listener.scheduler import (
            NewsListenerScheduler,
        )
    except ModuleNotFoundError:
        app_state.news_listener_scheduler = None
        return

    run_func = getattr(app_state, "_run_news_listener_cycle", None)
    if run_func is None:
        app_state.news_listener_scheduler = None
        return

    scheduler = NewsListenerScheduler(config=config, run_func=run_func)
    scheduler.start()
    app_state.news_listener_scheduler = scheduler
