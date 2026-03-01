"""Stock data routes (search, quote, kline, curve)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from market_reporter.api.deps import get_user_config
from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import Quote
from market_reporter.infra.db.session import init_db
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.symbol_search.schemas import StockSearchResult
from market_reporter.modules.symbol_search.service import SymbolSearchService

router = APIRouter(prefix="/api", tags=["stocks"])


class QuoteBatchItemRequest(BaseModel):
    symbol: str = Field(min_length=1)
    market: str = Field(pattern="^(CN|HK|US)$")


class QuoteBatchRequest(BaseModel):
    items: List[QuoteBatchItemRequest] = Field(min_length=1, max_length=100)


@router.get("/stocks/search", response_model=List[StockSearchResult])
async def stock_search(
    q: str = Query(..., min_length=1),
    market: str = Query("ALL", pattern="^(ALL|CN|HK|US)$"),
    limit: int = Query(20, ge=1, le=100),
    config: AppConfig = Depends(get_user_config),
) -> List[StockSearchResult]:
    init_db(config.database.url)
    service = SymbolSearchService(config=config, registry=ProviderRegistry())
    try:
        return await service.search(query=q, market=market, limit=limit)
    except Exception:
        return []


@router.get("/stocks/{symbol}/quote")
async def stock_quote(
    symbol: str,
    market: str = Query(..., pattern="^(CN|HK|US)$"),
    config: AppConfig = Depends(get_user_config),
):
    init_db(config.database.url)
    service = MarketDataService(config=config, registry=ProviderRegistry())
    try:
        return await service.get_quote(symbol=symbol, market=market)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stocks/quotes", response_model=List[Quote])
async def stock_quotes_batch(
    payload: QuoteBatchRequest,
    config: AppConfig = Depends(get_user_config),
) -> List[Quote]:
    init_db(config.database.url)
    service = MarketDataService(config=config, registry=ProviderRegistry())
    return await service.get_quotes(
        items=[(item.symbol, item.market) for item in payload.items]
    )


@router.get("/stocks/{symbol}/kline")
async def stock_kline(
    symbol: str,
    market: str = Query(..., pattern="^(CN|HK|US)$"),
    interval: str = Query("1m", pattern="^(1m|5m|1d)$"),
    limit: int = Query(300, ge=20, le=1000),
    config: AppConfig = Depends(get_user_config),
):
    init_db(config.database.url)
    service = MarketDataService(config=config, registry=ProviderRegistry())
    return await service.get_kline(
        symbol=symbol, market=market, interval=interval, limit=limit
    )


@router.get("/stocks/{symbol}/curve")
async def stock_curve(
    symbol: str,
    market: str = Query(..., pattern="^(CN|HK|US)$"),
    window: str = Query("1d"),
    config: AppConfig = Depends(get_user_config),
):
    init_db(config.database.url)
    service = MarketDataService(config=config, registry=ProviderRegistry())
    return await service.get_curve(symbol=symbol, market=market, window=window)
