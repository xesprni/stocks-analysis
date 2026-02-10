from __future__ import annotations

from typing import Dict, List

from market_reporter.core.types import CurvePoint, KLineBar, Quote


class CompositeMarketDataProvider:
    provider_id = "composite"

    def __init__(self, providers: Dict[str, object]) -> None:
        self.providers = providers

    async def get_quote(self, symbol: str, market: str) -> Quote:
        # First successful provider wins; errors are intentionally swallowed for failover.
        for provider in self._ordered(market=market):
            try:
                return await provider.get_quote(symbol=symbol, market=market)
            except Exception:
                continue
        raise ValueError(f"No available quote provider for {market}:{symbol}")

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        for provider in self._ordered(market=market):
            try:
                rows = await provider.get_kline(symbol=symbol, market=market, interval=interval, limit=limit)
                if rows:
                    return rows
            except Exception:
                continue
        raise ValueError(f"No available kline provider for {market}:{symbol}, interval={interval}")

    async def get_curve(self, symbol: str, market: str, window: str) -> List[CurvePoint]:
        for provider in self._ordered(market=market):
            try:
                rows = await provider.get_curve(symbol=symbol, market=market, window=window)
                if rows:
                    return rows
            except Exception:
                continue
        raise ValueError(f"No available curve provider for {market}:{symbol}")

    def _ordered(self, market: str):
        market = market.upper()
        if market in {"CN", "HK"}:
            # Prefer akshare for CN/HK where local endpoints are usually richer.
            return [self.providers["akshare"], self.providers["yfinance"]]
        # Prefer yfinance for US markets.
        return [self.providers["yfinance"], self.providers["akshare"]]
