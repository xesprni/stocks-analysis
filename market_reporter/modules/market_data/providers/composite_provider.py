from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import looks_like_index_symbol

logger = logging.getLogger(__name__)

# Per-provider timeout in seconds.  If a single provider takes longer than
# this, we skip it and try the next one in the failover chain.
_PROVIDER_TIMEOUT = 8


class CompositeMarketDataProvider:
    provider_id = "composite"

    def __init__(
        self,
        providers: Dict[str, object],
        *,
        provider_timeout: float = _PROVIDER_TIMEOUT,
    ) -> None:
        self.providers = providers
        self._timeout = provider_timeout

    async def get_quote(self, symbol: str, market: str) -> Quote:
        # First successful provider wins; errors are intentionally swallowed for failover.
        for provider in self._ordered(market=market, symbol=symbol):
            try:
                return await asyncio.wait_for(
                    provider.get_quote(symbol=symbol, market=market),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s timed out (%.1fs) for quote %s:%s",
                    pid,
                    self._timeout,
                    market,
                    symbol,
                )
                continue
            except Exception:
                continue
        raise ValueError(f"No available quote provider for {market}:{symbol}")

    async def get_kline(
        self, symbol: str, market: str, interval: str, limit: int
    ) -> List[KLineBar]:
        for provider in self._ordered(market=market, symbol=symbol):
            try:
                rows = await asyncio.wait_for(
                    provider.get_kline(
                        symbol=symbol, market=market, interval=interval, limit=limit
                    ),
                    timeout=self._timeout,
                )
                if rows:
                    return rows
            except asyncio.TimeoutError:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s timed out (%.1fs) for kline %s:%s",
                    pid,
                    self._timeout,
                    market,
                    symbol,
                )
                continue
            except Exception:
                continue
        raise ValueError(
            f"No available kline provider for {market}:{symbol}, interval={interval}"
        )

    async def get_curve(
        self, symbol: str, market: str, window: str
    ) -> List[CurvePoint]:
        for provider in self._ordered(market=market, symbol=symbol):
            try:
                rows = await asyncio.wait_for(
                    provider.get_curve(symbol=symbol, market=market, window=window),
                    timeout=self._timeout,
                )
                if rows:
                    return rows
            except asyncio.TimeoutError:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s timed out (%.1fs) for curve %s:%s",
                    pid,
                    self._timeout,
                    market,
                    symbol,
                )
                continue
            except Exception:
                continue
        raise ValueError(f"No available curve provider for {market}:{symbol}")

    def _ordered(self, market: str, symbol: str = ""):
        market = market.upper()
        lb = self.providers.get("longbridge")
        is_index = looks_like_index_symbol(symbol=symbol, market=market)
        if market in {"CN", "HK"}:
            # Prefer Longbridge for CN/HK when available, then yfinance, finally akshare.
            # For index-like symbols, skip akshare because its spot APIs are equity-focused.
            order = [self.providers["yfinance"]]
            if not is_index:
                order.append(self.providers["akshare"])
            if lb is not None:
                order.insert(0, lb)
            return order
        # US: prefer yfinance, then Longbridge. Only use akshare for non-index symbols.
        order = [self.providers["yfinance"]]
        if lb is not None:
            order.insert(1, lb)
        if not is_index:
            order.append(self.providers["akshare"])
        return order
