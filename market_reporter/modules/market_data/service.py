from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.infra.db.repos import MarketDataRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.market_data.providers.akshare_provider import AkshareMarketDataProvider
from market_reporter.modules.market_data.providers.composite_provider import CompositeMarketDataProvider
from market_reporter.modules.market_data.providers.yfinance_provider import YahooFinanceMarketDataProvider
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol


class MarketDataService:
    MODULE_NAME = "market_data"

    def __init__(self, config: AppConfig, registry: ProviderRegistry) -> None:
        self.config = config
        self.registry = registry
        self.registry.register(self.MODULE_NAME, "yfinance", self._build_yfinance)
        self.registry.register(self.MODULE_NAME, "akshare", self._build_akshare)
        self.registry.register(self.MODULE_NAME, "composite", self._build_composite)

    def _build_yfinance(self):
        return YahooFinanceMarketDataProvider()

    def _build_akshare(self):
        return AkshareMarketDataProvider()

    def _build_composite(self):
        return CompositeMarketDataProvider(
            providers={
                "yfinance": self._build_yfinance(),
                "akshare": self._build_akshare(),
            }
        )

    def _provider(self, provider_id: Optional[str] = None):
        target = provider_id or self.config.modules.market_data.default_provider
        return self.registry.resolve(self.MODULE_NAME, target)

    async def get_quote(self, symbol: str, market: str, provider_id: Optional[str] = None) -> Quote:
        normalized_symbol = normalize_symbol(symbol, market)
        provider = self._provider(provider_id=provider_id)
        resolved_market = market.upper()
        try:
            quote = await provider.get_quote(symbol=normalized_symbol, market=resolved_market)
            return quote
        except Exception:
            cached = self._quote_from_cache(symbol=normalized_symbol, market=resolved_market)
            if cached is not None:
                return cached
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
        provider = self._provider(provider_id=provider_id)
        try:
            rows = await provider.get_kline(
                symbol=normalized_symbol,
                market=market.upper(),
                interval=interval,
                limit=limit,
            )
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                repo.upsert_kline(rows)
            return rows
        except Exception:
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                cached = repo.list_kline(normalized_symbol, market.upper(), interval, limit=limit)
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
        provider = self._provider(provider_id=provider_id)
        try:
            rows = await provider.get_curve(symbol=normalized_symbol, market=market.upper(), window=window)
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                repo.save_curve_points(rows)
            return rows
        except Exception:
            with session_scope(self.config.database.url) as session:
                repo = MarketDataRepo(session)
                cached = repo.list_curve_points(normalized_symbol, market.upper(), limit=500)
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

            for interval in ("1m", "5m", "1d"):
                bars = repo.list_kline(symbol=symbol, market=market, interval=interval, limit=2)
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
