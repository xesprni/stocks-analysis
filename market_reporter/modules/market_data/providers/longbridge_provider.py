"""Longbridge OpenAPI market data provider.

Wraps the synchronous ``longbridge`` SDK with ``asyncio.to_thread`` to
keep the async interface consistent with other providers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

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
        self._ctx: Optional[Any] = None

    # ------------------------------------------------------------------
    # Lazy context – created once per provider instance.
    # ------------------------------------------------------------------

    def _ensure_ctx(self) -> Any:
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

    async def get_quotes(self, items: List[Tuple[str, str]]) -> List[Quote]:
        return await asyncio.to_thread(self._get_quotes_sync, items)

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
        rows = self._get_quotes_sync([(symbol, market)])
        if not rows:
            lb_symbol = to_longbridge_symbol(symbol, market)
            raise ValueError(f"No quote returned for {lb_symbol}")
        return rows[0]

    def _get_quotes_sync(self, items: List[Tuple[str, str]]) -> List[Quote]:
        if not items:
            return []

        ctx = cast(Any, self._ensure_ctx())
        prepared: List[Tuple[str, str, str]] = []
        for symbol, market in items:
            market_upper = market.upper()
            lb_symbol = to_longbridge_symbol(symbol, market_upper)
            normalized = normalize_symbol(symbol, market_upper)
            prepared.append((normalized, market_upper, lb_symbol))

        lb_symbols = [entry[2] for entry in prepared]
        quote_rows = ctx.quote(lb_symbols)
        ordered_rows = list(quote_rows)
        row_map: Dict[str, object] = {
            str(getattr(row, "symbol", "") or "").strip().upper(): row
            for row in quote_rows
            if str(getattr(row, "symbol", "") or "").strip()
        }

        quotes: List[Quote] = []
        for idx, (normalized, market_upper, lb_symbol) in enumerate(prepared):
            row = row_map.get(lb_symbol.upper())
            if row is None and len(ordered_rows) == len(prepared):
                row = ordered_rows[idx]
            if row is None:
                continue
            quotes.append(
                self._build_quote(
                    row=row,
                    normalized_symbol=normalized,
                    market=market_upper,
                )
            )
        return quotes

    def _get_kline_sync(
        self, symbol: str, market: str, interval: str, limit: int
    ) -> List[KLineBar]:
        from longbridge.openapi import AdjustType, Period

        ctx = cast(Any, self._ensure_ctx())
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
        ctx = cast(Any, self._ensure_ctx())
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

    def _build_quote(self, row: object, normalized_symbol: str, market: str) -> Quote:
        price = float(getattr(row, "last_done", 0.0) or 0.0)
        prev_close_raw = getattr(row, "prev_close", None)
        prev_close = float(prev_close_raw) if prev_close_raw else None
        change = None
        pct = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            pct = change / prev_close * 100

        ts_raw = getattr(row, "timestamp", None)
        ts = (
            ts_raw.isoformat(timespec="seconds")
            if ts_raw
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

        volume_raw = getattr(row, "volume", None)
        volume = float(volume_raw) if volume_raw is not None else None
        return Quote(
            symbol=normalized_symbol,
            market=market.upper(),
            ts=ts,
            price=price,
            change=change,
            change_percent=pct,
            volume=volume,
            currency=self._currency_by_market(market),
            source=self.provider_id,
        )
