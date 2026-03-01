"""Config routes with per-user isolation."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.config import AppConfig, LongbridgeConfig, TelegramConfig
from market_reporter.infra.db.session import init_db
from market_reporter.schemas import ConfigUpdateRequest
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.longbridge_credentials import LongbridgeCredentialService
from market_reporter.services.telegram_config import TelegramConfigService
from market_reporter.services.user_config_store import UserConfigStore
from market_reporter.settings import AppSettings

router = APIRouter(prefix="/api", tags=["config"])


def _resolve_effective_user_id(user: CurrentUser) -> Optional[int]:
    user_id = int(getattr(user, "user_id", 0) or 0)
    return user_id if user_id > 0 else None


def _get_user_config_store(request: Request, user: CurrentUser) -> UserConfigStore:
    settings: AppSettings = request.app.state.settings
    global_store: ConfigStore = request.app.state.config_store
    effective_user_id = _resolve_effective_user_id(user)
    return UserConfigStore(
        database_url=global_store.load().database.url,
        global_config_path=settings.config_file,
        user_id=effective_user_id,
    )


def _redact_sensitive_config(cfg: AppConfig) -> AppConfig:
    redacted_lb = cfg.longbridge.model_copy(
        update={
            "app_secret": "***" if cfg.longbridge.app_secret else "",
            "access_token": "***" if cfg.longbridge.access_token else "",
        }
    )
    redacted_tg = cfg.telegram.model_copy(
        update={
            "bot_token": "***" if cfg.telegram.bot_token else "",
        }
    )
    return cfg.model_copy(update={"longbridge": redacted_lb, "telegram": redacted_tg})


@router.get("/config", response_model=AppConfig)
async def get_config(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> AppConfig:
    store = _get_user_config_store(request, user)
    if not store.has_user_config():
        store.init_from_global()
    cfg = store.load()
    return _redact_sensitive_config(cfg)


@router.put("/config", response_model=AppConfig)
async def update_config(
    payload: ConfigUpdateRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> AppConfig:
    store = _get_user_config_store(request, user)
    current = store.load()
    updated = payload.to_config(current)
    saved = store.save(updated)
    init_db(saved.database.url)

    _restart_listener_scheduler(request.app.state, saved)
    return _redact_sensitive_config(saved)


class LongbridgeTokenRequest(BaseModel):
    app_key: str
    app_secret: str
    access_token: str


class TelegramConfigRequest(BaseModel):
    enabled: bool = False
    chat_id: str = ""
    bot_token: str = ""
    timeout_seconds: int = Field(default=10, ge=3, le=60)


@router.get("/longbridge", response_model=LongbridgeConfig)
async def get_longbridge_config(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> LongbridgeConfig:
    store = _get_user_config_store(request, user)
    cfg = store.load()
    return cfg.longbridge.model_copy(
        update={
            "app_secret": "***" if cfg.longbridge.app_secret else "",
            "access_token": "***" if cfg.longbridge.access_token else "",
        }
    )


@router.put("/longbridge/token")
async def update_longbridge_token(
    payload: LongbridgeTokenRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> dict:
    store = _get_user_config_store(request, user)
    current = store.load()
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
    store.save(next_config)
    return {"ok": True}


@router.delete("/longbridge/token")
async def delete_longbridge_token(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> dict:
    store = _get_user_config_store(request, user)
    current = store.load()
    init_db(current.database.url)
    credential_service = LongbridgeCredentialService(
        database_url=current.database.url,
        user_id=_resolve_effective_user_id(user),
    )
    credential_service.delete()
    next_lb = LongbridgeConfig()
    next_config = current.model_copy(update={"longbridge": next_lb})
    store.save(next_config)
    return {"ok": True}


@router.get("/telegram", response_model=TelegramConfig)
async def get_telegram_config(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> TelegramConfig:
    store = _get_user_config_store(request, user)
    cfg = store.load()
    return cfg.telegram.model_copy(
        update={
            "bot_token": "***" if cfg.telegram.bot_token else "",
        }
    )


@router.put("/telegram")
async def update_telegram_config(
    payload: TelegramConfigRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> dict:
    store = _get_user_config_store(request, user)
    current = store.load()
    bot_token_input = str(payload.bot_token or "").strip()
    if bot_token_input in {"", "***"}:
        bot_token = current.telegram.bot_token
    else:
        bot_token = bot_token_input
    chat_id = str(payload.chat_id or "").strip()
    enabled = bool(payload.enabled and chat_id and bot_token)
    next_tg = current.telegram.model_copy(
        update={
            "enabled": enabled,
            "chat_id": chat_id,
            "bot_token": bot_token,
            "timeout_seconds": payload.timeout_seconds,
        }
    )
    next_config = current.model_copy(update={"telegram": next_tg})
    store.save(next_config)
    return {"ok": True}


@router.delete("/telegram")
async def delete_telegram_config(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> dict:
    store = _get_user_config_store(request, user)
    current = store.load()
    init_db(current.database.url)
    TelegramConfigService(
        database_url=current.database.url,
        user_id=_resolve_effective_user_id(user),
    ).delete()
    next_config = current.model_copy(update={"telegram": TelegramConfig()})
    store.save(next_config)
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
