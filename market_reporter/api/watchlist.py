"""Watchlist CRUD routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.api.deps import get_effective_user_id, get_user_config
from market_reporter.config import AppConfig
from market_reporter.modules.watchlist.schemas import (
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistUpdateRequest,
)
from market_reporter.modules.watchlist.service import WatchlistService

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.get("/watchlist", response_model=List[WatchlistItem])
async def list_watchlist(
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> List[WatchlistItem]:
    service = WatchlistService(config, user_id=get_effective_user_id(user))
    return service.list_items()


@router.post("/watchlist", response_model=WatchlistItem)
async def create_watchlist_item(
    payload: WatchlistCreateRequest,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> WatchlistItem:
    service = WatchlistService(config, user_id=get_effective_user_id(user))
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


@router.patch("/watchlist/{item_id}", response_model=WatchlistItem)
async def update_watchlist_item(
    item_id: int,
    payload: WatchlistUpdateRequest,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> WatchlistItem:
    service = WatchlistService(config, user_id=get_effective_user_id(user))
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


@router.delete("/watchlist/{item_id}")
async def delete_watchlist_item(
    item_id: int,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> dict:
    service = WatchlistService(config, user_id=get_effective_user_id(user))
    deleted = service.delete_item(item_id=item_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Watchlist item not found: {item_id}"
        )
    return {"deleted": True}
