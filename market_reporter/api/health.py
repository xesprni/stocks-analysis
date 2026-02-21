"""Health and UI options routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from market_reporter.api.deps import get_config_store
from market_reporter.schemas import UIOptionsResponse
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/options/ui", response_model=UIOptionsResponse)
async def ui_options(
    config_store: ConfigStore = Depends(get_config_store),
) -> UIOptionsResponse:
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
        market_data_providers=["longbridge"],
        analysis_providers=analysis_provider_ids,
        analysis_models_by_provider={},
        listener_threshold_presets=[1.0, 1.5, 2.0, 3.0, 5.0],
        listener_intervals=[5, 10, 15, 30, 60],
    )
