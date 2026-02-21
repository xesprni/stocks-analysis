"""Config routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from market_reporter.api.deps import get_config_store
from market_reporter.config import AppConfig, LongbridgeConfig
from market_reporter.infra.db.session import init_db
from market_reporter.schemas import ConfigUpdateRequest
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.longbridge_credentials import LongbridgeCredentialService

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", response_model=AppConfig)
async def get_config(
    config_store: ConfigStore = Depends(get_config_store),
) -> AppConfig:
    cfg = config_store.load()
    # Redact Longbridge secrets before sending to frontend.
    redacted_lb = cfg.longbridge.model_copy(
        update={
            "app_secret": "***" if cfg.longbridge.app_secret else "",
            "access_token": "***" if cfg.longbridge.access_token else "",
        }
    )
    return cfg.model_copy(update={"longbridge": redacted_lb})


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


class LongbridgeTokenRequest(BaseModel):
    app_key: str
    app_secret: str
    access_token: str


@router.get("/longbridge", response_model=LongbridgeConfig)
async def get_longbridge_config(
    config_store: ConfigStore = Depends(get_config_store),
) -> LongbridgeConfig:
    cfg = config_store.load()
    return cfg.longbridge.model_copy(
        update={
            "app_secret": "***" if cfg.longbridge.app_secret else "",
            "access_token": "***" if cfg.longbridge.access_token else "",
        }
    )


@router.put("/longbridge/token")
async def update_longbridge_token(
    payload: LongbridgeTokenRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    current = config_store.load()
    next_lb = current.longbridge.model_copy(
        update={
            "app_key": payload.app_key,
            "app_secret": payload.app_secret,
            "access_token": payload.access_token,
            "enabled": bool(
                payload.app_key and payload.app_secret and payload.access_token
            ),
        }
    )
    next_config = current.model_copy(update={"longbridge": next_lb})
    config_store.save(next_config)
    return {"ok": True}


@router.delete("/longbridge/token")
async def delete_longbridge_token(
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    current = config_store.load()
    init_db(current.database.url)
    credential_service = LongbridgeCredentialService(database_url=current.database.url)
    credential_service.delete()
    next_lb = LongbridgeConfig()  # Reset to defaults (disabled, empty credentials)
    next_config = current.model_copy(update={"longbridge": next_lb})
    config_store.save(next_config)
    return {"ok": True}


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
