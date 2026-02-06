from __future__ import annotations

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
        quote = await provider.get_quote(symbol=normalized_symbol, market=market.upper())
        return quote

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
