"""Dashboard snapshot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.api.deps import (
    get_effective_user_id,
    get_user_config,
    get_user_config_store,
)
from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.modules.dashboard.schemas import (
    DashboardAutoRefreshUpdateRequest,
    DashboardAutoRefreshView,
    DashboardIndicesSnapshotView,
    DashboardSnapshotView,
    DashboardWatchlistSnapshotView,
)
from market_reporter.modules.dashboard.service import DashboardService
from market_reporter.services.user_config_store import UserConfigStore

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/snapshot", response_model=DashboardSnapshotView)
async def dashboard_snapshot(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=5, le=50),
    enabled_only: bool = Query(True),
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> DashboardSnapshotView:
    init_db(config.database.url)
    service = DashboardService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    return await service.get_snapshot(
        page=page,
        page_size=page_size,
        enabled_only=enabled_only,
    )


@router.get("/dashboard/indices", response_model=DashboardIndicesSnapshotView)
async def dashboard_indices_snapshot(
    enabled_only: bool = Query(True),
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> DashboardIndicesSnapshotView:
    init_db(config.database.url)
    service = DashboardService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    return await service.get_index_snapshot(enabled_only=enabled_only)


@router.get("/dashboard/watchlist", response_model=DashboardWatchlistSnapshotView)
async def dashboard_watchlist_snapshot(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=5, le=50),
    enabled_only: bool = Query(True),
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> DashboardWatchlistSnapshotView:
    init_db(config.database.url)
    service = DashboardService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    return await service.get_watchlist_snapshot(
        page=page,
        page_size=page_size,
        enabled_only=enabled_only,
    )


@router.put("/dashboard/auto-refresh", response_model=DashboardAutoRefreshView)
async def update_dashboard_auto_refresh(
    payload: DashboardAutoRefreshUpdateRequest,
    config_store: UserConfigStore = Depends(get_user_config_store),
) -> DashboardAutoRefreshView:
    config = config_store.load()
    next_config = config.model_copy(
        update={
            "dashboard": config.dashboard.model_copy(
                update={"auto_refresh_enabled": payload.auto_refresh_enabled}
            )
        }
    )
    saved = config_store.save(next_config)
    return DashboardAutoRefreshView(
        auto_refresh_enabled=saved.dashboard.auto_refresh_enabled,
        auto_refresh_seconds=saved.dashboard.auto_refresh_seconds,
    )
