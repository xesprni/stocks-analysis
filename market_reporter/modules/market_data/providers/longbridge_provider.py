"""Longbridge OpenAPI market data provider.

Wraps the synchronous ``longbridge`` SDK with ``asyncio.to_thread`` to
keep the async interface consistent with other providers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from market_reporter.config import LongbridgeConfig
from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_longbridge_symbol,
)

logger = logging.getLogger(__name__)


class LongbridgeMarketDataProvider:
    provider_id = "longbridge"

    def __init__(self, lb_config: LongbridgeConfig) -> None:
        self._lb_config = lb_config
        self._ctx: Optional[object] = None

    # ------------------------------------------------------------------
    # Lazy context – created once per provider instance.
    # ------------------------------------------------------------------

    def _ensure_ctx(self):
        """Create a QuoteContext on first use (must be called in a thread)."""
        if self._ctx is not None:
            return self._ctx
        from longbridge.openapi import Config, QuoteContext

        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        self._ctx = QuoteContext(config)
        return self._ctx

    # ------------------------------------------------------------------
    # Public async interface (MarketDataProvider protocol)
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str, market: str) -> Quote:
        return await asyncio.to_thread(self._get_quote_sync, symbol, market)

    async def get_kline(
        self, symbol: str, market: str, interval: str, limit: int
    ) -> List[KLineBar]:
        return await asyncio.to_thread(
            self._get_kline_sync, symbol, market, interval, limit
        )

    async def get_curve(
        self, symbol: str, market: str, window: str
    ) -> List[CurvePoint]:
        return await asyncio.to_thread(self._get_curve_sync, symbol, market, window)

    # ------------------------------------------------------------------
    # Sync implementations
    # ------------------------------------------------------------------

    def _get_quote_sync(self, symbol: str, market: str) -> Quote:
        ctx = self._ensure_ctx()
        lb_symbol = to_longbridge_symbol(symbol, market)
        normalized = normalize_symbol(symbol, market)

        quotes = ctx.quote([lb_symbol])
        if not quotes:
            raise ValueError(f"No quote returned for {lb_symbol}")

        q = quotes[0]
        price = float(q.last_done)
        prev_close = float(q.prev_close) if q.prev_close else None
        change = None
        pct = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            pct = change / prev_close * 100

        ts = (
            q.timestamp.isoformat(timespec="seconds")
            if q.timestamp
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

        return Quote(
            symbol=normalized,
            market=market.upper(),
            ts=ts,
            price=price,
            change=change,
            change_percent=pct,
            volume=float(q.volume) if q.volume is not None else None,
            currency=self._currency_by_market(market),
            source=self.provider_id,
        )

    def _get_kline_sync(
        self, symbol: str, market: str, interval: str, limit: int
    ) -> List[KLineBar]:
        from longbridge.openapi import AdjustType, Period

        ctx = self._ensure_ctx()
        lb_symbol = to_longbridge_symbol(symbol, market)
        normalized = normalize_symbol(symbol, market)

        period = self._map_period(interval)
        if period is None:
            raise ValueError(f"Unsupported interval for Longbridge: {interval}")

        candlesticks = ctx.candlesticks(
            lb_symbol, period, limit, AdjustType.ForwardAdjust
        )

        bars: List[KLineBar] = []
        for c in candlesticks:
            ts = c.timestamp.isoformat(timespec="seconds") if c.timestamp else ""
            bars.append(
                KLineBar(
                    symbol=normalized,
                    market=market.upper(),
                    interval=interval,
                    ts=ts,
                    open=float(c.open),
                    high=float(c.high),
                    low=float(c.low),
                    close=float(c.close),
                    volume=float(c.volume) if c.volume is not None else None,
                    source=self.provider_id,
                )
            )
        return bars

    def _get_curve_sync(
        self, symbol: str, market: str, window: str
    ) -> List[CurvePoint]:
        ctx = self._ensure_ctx()
        lb_symbol = to_longbridge_symbol(symbol, market)
        normalized = normalize_symbol(symbol, market)

        intraday = ctx.intraday(lb_symbol)

        points: List[CurvePoint] = []
        for line in intraday:
            ts = line.timestamp.isoformat(timespec="seconds") if line.timestamp else ""
            points.append(
                CurvePoint(
                    symbol=normalized,
                    market=market.upper(),
                    ts=ts,
                    price=float(line.price),
                    volume=float(line.volume) if line.volume is not None else None,
                    source=self.provider_id,
                )
            )
        return points

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_period(interval: str):
        """Map internal interval string to Longbridge Period enum."""
        from longbridge.openapi import Period

        mapping = {
            "1m": Period.Min_1,
            "5m": Period.Min_5,
            "15m": Period.Min_15,
            "30m": Period.Min_30,
            "60m": Period.Min_60,
            "1d": Period.Day,
            "1w": Period.Week,
            "1M": Period.Month,
        }
        return mapping.get(interval)

    @staticmethod
    def _currency_by_market(market: str) -> str:
        return {
            "CN": "CNY",
            "HK": "HKD",
            "US": "USD",
        }.get(market.upper(), "")
