from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.infra.db.repos import MarketDataRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol


class MarketDataService:
    MODULE_NAME = "market_data"

    def __init__(self, config: AppConfig, registry: ProviderRegistry) -> None:
        self.config = config
        self.registry = registry
        self._provider_instances: dict[str, object] = {}
        self.registry.register(self.MODULE_NAME, "longbridge", self._build_longbridge)
        self.registry.register(self.MODULE_NAME, "composite", self._build_composite)

    def _build_longbridge(self):
        from market_reporter.modules.market_data.providers.longbridge_provider import (
            LongbridgeMarketDataProvider,
        )

        return LongbridgeMarketDataProvider(lb_config=self.config.longbridge)

    def _build_composite(self):
        # Longbridge-only mode: keep legacy provider_id compatibility.
        return self._build_longbridge()

    def _provider(self, provider_id: Optional[str] = None):
        target = (
            provider_id or self.config.modules.market_data.default_provider or ""
        ).strip() or "longbridge"
        resolved_target = target
        if not self.registry.has(self.MODULE_NAME, resolved_target):
            resolved_target = (
                "longbridge"
                if self.registry.has(self.MODULE_NAME, "longbridge")
                else "composite"
            )
        instance = self._provider_instances.get(resolved_target)
        if instance is not None:
            return instance
        try:
            instance = self.registry.resolve(self.MODULE_NAME, resolved_target)
        except Exception:
            # Provider fallback guarantees read APIs remain available with degraded data quality.
            if self.registry.has(self.MODULE_NAME, "longbridge"):
                resolved_target = "longbridge"
                instance = self.registry.resolve(self.MODULE_NAME, resolved_target)
            else:
                resolved_target = "composite"
                instance = self.registry.resolve(self.MODULE_NAME, resolved_target)
        self._provider_instances[resolved_target] = instance
        return instance

    async def get_quotes(
        self,
        items: List[tuple[str, str]],
        provider_id: Optional[str] = None,
    ) -> List[Quote]:
        if not items:
            return []

        normalized_items: List[tuple[str, str]] = [
            (normalize_symbol(symbol, market), market.upper())
            for symbol, market in items
            if str(symbol or "").strip()
            and str(market or "").strip().upper() in {"CN", "HK", "US"}
        ]
        if not normalized_items:
            return []

        provider = self._provider(provider_id=provider_id)
        quotes_by_key: dict[tuple[str, str], Quote] = {}

        if hasattr(provider, "get_quotes"):
            try:
                rows = await provider.get_quotes(normalized_items)
                for row in rows:
                    key = (normalize_symbol(row.symbol, row.market), row.market.upper())
                    quotes_by_key[key] = row
            except Exception:
                quotes_by_key = {}

        missing_items = [
            (symbol, market)
            for symbol, market in normalized_items
            if (symbol, market) not in quotes_by_key
        ]
        if missing_items:
            fallback_rows = await asyncio.gather(
                *[
                    self.get_quote(
                        symbol=symbol, market=market, provider_id=provider_id
                    )
                    for symbol, market in missing_items
                ]
            )
            for quote in fallback_rows:
                key = (
                    normalize_symbol(quote.symbol, quote.market),
                    quote.market.upper(),
                )
                quotes_by_key[key] = quote

        return [
            quotes_by_key[(symbol, market)]
            for symbol, market in normalized_items
            if (symbol, market) in quotes_by_key
        ]

    async def get_quote(
        self, symbol: str, market: str, provider_id: Optional[str] = None
    ) -> Quote:
        resolved_market = market.upper()
        normalized_symbol = normalize_symbol(symbol, market)
        requested_provider_id = (
            provider_id or self.config.modules.market_data.default_provider or ""
        ).strip() or "longbridge"
        try:
            provider = self._provider(provider_id=provider_id)
            quote = await provider.get_quote(
                symbol=normalized_symbol, market=resolved_market
            )
            return quote
        except Exception:
            if requested_provider_id != "composite":
                try:
                    fallback_provider = self._provider(provider_id="composite")
                    return await fallback_provider.get_quote(
                        symbol=normalized_symbol,
                        market=resolved_market,
                    )
                except Exception:
                    pass
            # On provider failure, first attempt to synthesize quote from cached market data.
            cached = self._quote_from_cache(
                symbol=normalized_symbol, market=resolved_market
            )
            if cached is not None:
                return cached
            # Last-resort placeholder keeps API response schema stable.
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return Quote(
                symbol=normalized_symbol,
                market=resolved_market,
                ts=now,
                price=0.0,
                change=None,
                change_percent=None,
                volume=None,
                currency=self._currency_by_market(resolved_market),
                source="unavailable",
            )

    async def get_kline(
        self,
        symbol: str,
        market: str,
        interval: str,
        limit: int,
        provider_id: Optional[str] = None,
    ) -> List[KLineBar]:
        normalized_symbol = normalize_symbol(symbol, market)
        requested_provider_id = (
            provider_id or self.config.modules.market_data.default_provider or ""
        ).strip() or "longbridge"
        try:
            provider = self._provider(provider_id=provider_id)
            rows = await provider.get_kline(
                symbol=normalized_symbol,
                market=market.upper(),
                interval=interval,
                limit=limit,
            )
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                # Write-through cache for downstream chart/quote fallback paths.
                repo.upsert_kline(rows)
            return rows
        except Exception:
            if requested_provider_id != "composite":
                try:
                    fallback_provider = self._provider(provider_id="composite")
                    rows = await fallback_provider.get_kline(
                        symbol=normalized_symbol,
                        market=market.upper(),
                        interval=interval,
                        limit=limit,
                    )
                    if rows:
                        with session_scope(self.config.database.url) as session:
                            repo = MarketDataRepo(session)
                            repo.upsert_kline(rows)
                        return rows
                except Exception:
                    pass
            # Degrade to historical cache when upstream provider is unavailable.
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                cached = repo.list_kline(
                    normalized_symbol, market.upper(), interval, limit=limit
                )
                return [
                    KLineBar(
                        symbol=row.symbol,
                        market=row.market,
                        interval=row.interval,
                        ts=row.ts,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                        source=row.source,
                    )
                    for row in cached
                ]

    async def get_curve(
        self,
        symbol: str,
        market: str,
        window: str,
        provider_id: Optional[str] = None,
    ) -> List[CurvePoint]:
        normalized_symbol = normalize_symbol(symbol, market)
        requested_provider_id = (
            provider_id or self.config.modules.market_data.default_provider or ""
        ).strip() or "longbridge"
        try:
            provider = self._provider(provider_id=provider_id)
            rows = await provider.get_curve(
                symbol=normalized_symbol, market=market.upper(), window=window
            )
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                # Persist latest intraday points for listener/report fallback.
                repo.save_curve_points(rows)
            return rows
        except Exception:
            if requested_provider_id != "composite":
                try:
                    fallback_provider = self._provider(provider_id="composite")
                    rows = await fallback_provider.get_curve(
                        symbol=normalized_symbol,
                        market=market.upper(),
                        window=window,
                    )
                    if rows:
                        with session_scope(self.config.database.url) as session:
                            repo = MarketDataRepo(session)
                            repo.save_curve_points(rows)
                        return rows
                except Exception:
                    pass
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                cached = repo.list_curve_points(
                    normalized_symbol, market.upper(), limit=500
                )
                return [
                    CurvePoint(
                        symbol=row.symbol,
                        market=row.market,
                        ts=row.ts,
                        price=row.price,
                        volume=row.volume,
                        source=row.source,
                    )
                    for row in cached
                ]

    def provider_ids(self) -> List[str]:
        return self.registry.list_ids(self.MODULE_NAME)

    def _quote_from_cache(self, symbol: str, market: str) -> Optional[Quote]:
        with session_scope(self.config.database.url) as session:
            repo = MarketDataRepo(session)
            # Prefer curve points because they usually represent the freshest price.
            points = repo.list_curve_points(symbol=symbol, market=market, limit=2)
            if points:
                latest = points[-1]
                previous = points[-2] if len(points) > 1 else None
                change = None
                change_percent = None
                if previous and previous.price != 0:
                    change = latest.price - previous.price
                    change_percent = change / previous.price * 100
                return Quote(
                    symbol=symbol,
                    market=market,
                    ts=latest.ts,
                    price=latest.price,
                    change=change,
                    change_percent=change_percent,
                    volume=latest.volume,
                    currency=self._currency_by_market(market),
                    source=f"cache:{latest.source}",
                )

            # Fallback to available kline intervals ordered by expected freshness.
            for interval in ("1m", "5m", "1d"):
                bars = repo.list_kline(
                    symbol=symbol, market=market, interval=interval, limit=2
                )
                if not bars:
                    continue
                latest_bar = bars[-1]
                previous_bar = bars[-2] if len(bars) > 1 else None
                change = None
                change_percent = None
                if previous_bar and previous_bar.close != 0:
                    change = latest_bar.close - previous_bar.close
                    change_percent = change / previous_bar.close * 100
                return Quote(
                    symbol=symbol,
                    market=market,
                    ts=latest_bar.ts,
                    price=latest_bar.close,
                    change=change,
                    change_percent=change_percent,
                    volume=latest_bar.volume,
                    currency=self._currency_by_market(market),
                    source=f"cache:{latest_bar.source}",
                )
        return None

    @staticmethod
    def _currency_by_market(market: str) -> str:
        return {
            "CN": "CNY",
            "HK": "HKD",
            "US": "USD",
        }.get(market.upper(), "")
