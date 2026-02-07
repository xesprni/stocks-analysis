"""Analysis provider CRUD, auth, models, secrets routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from market_reporter.api.deps import get_config_store
from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.modules.analysis_engine.schemas import (
    AnalysisProviderView,
    ProviderAuthStartRequest,
    ProviderAuthStartResponse,
    ProviderAuthStatusView,
    ProviderModelsView,
    ProviderModelSelectionRequest,
    ProviderSecretRequest,
)
from market_reporter.modules.analysis_engine.service import AnalysisService
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["providers"])


def _get_analysis_service(config: AppConfig) -> AnalysisService:
    init_db(config.database.url)
    return AnalysisService(config=config, registry=ProviderRegistry())


@router.get("/providers/analysis", response_model=List[AnalysisProviderView])
async def analysis_providers(
    config_store: ConfigStore = Depends(get_config_store),
) -> List[AnalysisProviderView]:
    config = config_store.load()
    service = _get_analysis_service(config)
    return service.list_providers()


@router.put("/providers/analysis/default", response_model=AppConfig)
async def update_default_analysis(
    payload: ProviderModelSelectionRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> AppConfig:
    config = config_store.load()
    service = _get_analysis_service(config)
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


@router.put("/providers/analysis/{provider_id}/secret")
async def put_analysis_secret(
    provider_id: str,
    payload: ProviderSecretRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    service = _get_analysis_service(config)
    try:
        service.put_secret(provider_id=provider_id, api_key=payload.api_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post(
    "/providers/analysis/{provider_id}/auth/start",
    response_model=ProviderAuthStartResponse,
)
async def start_analysis_auth(
    provider_id: str,
    request: Request,
    payload: Optional[ProviderAuthStartRequest] = None,
    config_store: ConfigStore = Depends(get_config_store),
) -> ProviderAuthStartResponse:
    config = config_store.load()
    service = _get_analysis_service(config)
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


@router.get(
    "/providers/analysis/{provider_id}/auth/status",
    response_model=ProviderAuthStatusView,
)
async def analysis_auth_status(
    provider_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> ProviderAuthStatusView:
    config = config_store.load()
    service = _get_analysis_service(config)
    try:
        return await service.get_provider_auth_status(provider_id=provider_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/providers/analysis/{provider_id}/auth/callback",
    response_class=HTMLResponse,
    name="analysis_auth_callback",
)
async def analysis_auth_callback(
    provider_id: str,
    request: Request,
    state: str = Query(..., min_length=8),
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    config_store: ConfigStore = Depends(get_config_store),
) -> str:
    if error:
        return (
            "<html><body><h3>Login failed</h3>"
            f"<p>{error}</p><p>You can close this page.</p></body></html>"
        )

    config = config_store.load()
    service = _get_analysis_service(config)
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


@router.post("/providers/analysis/{provider_id}/auth/logout")
async def logout_analysis_auth(
    provider_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    service = _get_analysis_service(config)
    deleted = await service.logout_provider_auth(provider_id=provider_id)
    return {"deleted": deleted}


@router.get(
    "/providers/analysis/{provider_id}/models",
    response_model=ProviderModelsView,
)
async def analysis_provider_models(
    provider_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> ProviderModelsView:
    config = config_store.load()
    service = _get_analysis_service(config)
    try:
        return await service.list_provider_models(provider_id=provider_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/providers/analysis/{provider_id}/secret")
async def delete_analysis_secret(
    provider_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    service = _get_analysis_service(config)
    deleted = service.delete_secret(provider_id=provider_id)
    return {"deleted": deleted}


@router.delete("/providers/analysis/{provider_id}", response_model=AppConfig)
async def delete_analysis_provider(
    provider_id: str,
    config_store: ConfigStore = Depends(get_config_store),
) -> AppConfig:
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
    init_db(saved.database.url)
    service = AnalysisService(config=saved, registry=ProviderRegistry())
    await service.logout_provider_auth(provider_id=provider_id)
    service.delete_secret(provider_id=provider_id)
    return saved
