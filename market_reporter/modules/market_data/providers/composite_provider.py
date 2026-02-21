from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import (
    looks_like_index_symbol,
    normalize_symbol,
)

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
            except Exception as exc:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s failed for quote %s:%s – %s: %s",
                    pid,
                    market,
                    symbol,
                    type(exc).__name__,
                    exc,
                )
                continue
        raise ValueError(f"No available quote provider for {market}:{symbol}")

    async def get_quotes(self, items: List[tuple]) -> List[Quote]:
        """Batch quote fetch.  Groups items by preferred provider to minimise
        individual HTTP requests (e.g. yfinance ``download`` handles batches
        in a single round-trip).
        """
        if not items:
            return []

        # Group items by first-choice provider that supports get_quotes.
        provider_batches: Dict[str, List[tuple]] = {}
        individual_items: List[tuple] = []

        for symbol, market in items:
            ordered = self._ordered(market=market, symbol=symbol)
            batched = False
            for provider in ordered:
                if hasattr(provider, "get_quotes"):
                    pid = getattr(provider, "provider_id", type(provider).__name__)
                    provider_batches.setdefault(pid, []).append((symbol, market))
                    batched = True
                    break
            if not batched:
                individual_items.append((symbol, market))

        results: List[Quote] = []

        # Batch calls per provider.
        for pid, batch_items in provider_batches.items():
            provider = next(
                (
                    p
                    for p in self.providers.values()
                    if getattr(p, "provider_id", None) == pid
                ),
                None,
            )
            if provider is None:
                individual_items.extend(batch_items)
                continue
            try:
                rows = await asyncio.wait_for(
                    provider.get_quotes(batch_items),
                    timeout=self._timeout * max(1, len(batch_items)),
                )
                if rows:
                    fetched_keys = {
                        (normalize_symbol(q.symbol, q.market), q.market.upper())
                        for q in rows
                    }
                    results.extend(rows)
                    # Any items not returned by the batch call fall back to
                    # individual fetch.
                    for sym, mkt in batch_items:
                        key = (normalize_symbol(sym, mkt), mkt.upper())
                        if key not in fetched_keys:
                            individual_items.append((sym, mkt))
                else:
                    individual_items.extend(batch_items)
            except Exception as exc:
                logger.warning(
                    "Provider %s batch get_quotes failed – %s: %s",
                    pid,
                    type(exc).__name__,
                    exc,
                )
                individual_items.extend(batch_items)

        # Fall back to one-by-one for remaining items.
        for symbol, market in individual_items:
            try:
                quote = await self.get_quote(symbol=symbol, market=market)
                results.append(quote)
            except Exception:
                pass

        return results

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
            except Exception as exc:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s failed for kline %s:%s – %s: %s",
                    pid,
                    market,
                    symbol,
                    type(exc).__name__,
                    exc,
                )
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
            except Exception as exc:
                pid = getattr(provider, "provider_id", type(provider).__name__)
                logger.warning(
                    "Provider %s failed for curve %s:%s – %s: %s",
                    pid,
                    market,
                    symbol,
                    type(exc).__name__,
                    exc,
                )
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
