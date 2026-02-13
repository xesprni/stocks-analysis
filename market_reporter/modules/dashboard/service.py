from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import Quote
from market_reporter.modules.dashboard.schemas import (
    DashboardIndexMetricView,
    DashboardSnapshotView,
    DashboardWatchlistMetricView,
    PaginationView,
)
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.watchlist.schemas import WatchlistItem
from market_reporter.modules.watchlist.service import WatchlistService


class DashboardService:
    def __init__(
        self,
        config: AppConfig,
        registry: ProviderRegistry,
        market_data_service: Optional[MarketDataService] = None,
        watchlist_service: Optional[WatchlistService] = None,
    ) -> None:
        self.config = config
        self.market_data_service = market_data_service or MarketDataService(
            config=config, registry=registry
        )
        self.watchlist_service = watchlist_service or WatchlistService(config=config)

    async def get_snapshot(
        self, page: int = 1, page_size: int = 10, enabled_only: bool = True
    ) -> DashboardSnapshotView:
        index_rows = self.config.dashboard.indices or []
        index_metrics = await asyncio.gather(
            *[
                self._build_index_metric(
                    symbol=item.symbol, market=item.market, alias=item.alias
                )
                for item in index_rows
            ]
        )

        watchlist_items = (
            self.watchlist_service.list_enabled_items()
            if enabled_only
            else self.watchlist_service.list_items()
        )
        total = len(watchlist_items)
        total_pages = (total + page_size - 1) // page_size if total else 0
        start = (page - 1) * page_size
        end = start + page_size
        page_items = watchlist_items[start:end]

        watchlist_metrics = await asyncio.gather(
            *[self._build_watchlist_metric(item) for item in page_items]
        )

        return DashboardSnapshotView(
            generated_at=datetime.now(timezone.utc),
            auto_refresh_enabled=self.config.dashboard.auto_refresh_enabled,
            auto_refresh_seconds=self.config.dashboard.auto_refresh_seconds,
            indices=index_metrics,
            watchlist=watchlist_metrics,
            pagination=PaginationView(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )

    async def _build_index_metric(
        self, symbol: str, market: str, alias: Optional[str]
    ) -> DashboardIndexMetricView:
        quote = await self._safe_quote(symbol=symbol, market=market)
        return DashboardIndexMetricView(
            symbol=quote.symbol,
            market=quote.market,
            alias=alias,
            ts=quote.ts,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            currency=quote.currency,
            source=quote.source,
        )

    async def _build_watchlist_metric(
        self, item: WatchlistItem
    ) -> DashboardWatchlistMetricView:
        quote = await self._safe_quote(symbol=item.symbol, market=item.market)
        return DashboardWatchlistMetricView(
            id=item.id,
            symbol=item.symbol,
            market=item.market,
            alias=item.alias,
            display_name=item.display_name,
            enabled=item.enabled,
            ts=quote.ts,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            currency=quote.currency,
            source=quote.source,
        )

    async def _safe_quote(self, symbol: str, market: str) -> Quote:
        cleaned_symbol = (symbol or "").strip()
        cleaned_market = (market or "").strip().upper()
        if not cleaned_symbol or cleaned_market not in {"CN", "HK", "US"}:
            return self._unavailable_quote(
                symbol=cleaned_symbol,
                market=cleaned_market or "US",
            )

        try:
            return await self.market_data_service.get_quote(
                symbol=cleaned_symbol, market=cleaned_market
            )
        except Exception:
            return self._unavailable_quote(
                symbol=cleaned_symbol, market=cleaned_market
            )

    @staticmethod
    def _unavailable_quote(symbol: str, market: str) -> Quote:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        currency = {
            "CN": "CNY",
            "HK": "HKD",
            "US": "USD",
        }.get(market.upper(), "")
        return Quote(
            symbol=symbol,
            market=market.upper(),
            ts=now,
            price=0.0,
            change=None,
            change_percent=None,
            volume=None,
            currency=currency,
            source="unavailable",
        )

