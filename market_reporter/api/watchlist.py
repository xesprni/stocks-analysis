"""Watchlist CRUD routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from market_reporter.api.deps import get_config_store
from market_reporter.modules.watchlist.schemas import (
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistUpdateRequest,
)
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.services.config_store import ConfigStore

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.get("/watchlist", response_model=List[WatchlistItem])
async def list_watchlist(
    config_store: ConfigStore = Depends(get_config_store),
) -> List[WatchlistItem]:
    config = config_store.load()
    service = WatchlistService(config)
    return service.list_items()


@router.post("/watchlist", response_model=WatchlistItem)
async def create_watchlist_item(
    payload: WatchlistCreateRequest,
    config_store: ConfigStore = Depends(get_config_store),
) -> WatchlistItem:
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


@router.patch("/watchlist/{item_id}", response_model=WatchlistItem)
async def update_watchlist_item(
    item_id: int,
    payload: WatchlistUpdateRequest,
    config_store: ConfigStore = Depends(get_config_store),
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


@router.delete("/watchlist/{item_id}")
async def delete_watchlist_item(
    item_id: int,
    config_store: ConfigStore = Depends(get_config_store),
) -> dict:
    config = config_store.load()
    service = WatchlistService(config)
    deleted = service.delete_item(item_id=item_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Watchlist item not found: {item_id}"
        )
    return {"deleted": True}
