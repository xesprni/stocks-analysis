from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, to_yfinance_symbol


class YahooFinanceMarketDataProvider:
    provider_id = "yfinance"

    async def get_quote(self, symbol: str, market: str) -> Quote:
        # yfinance SDK is sync; run in thread to avoid blocking event loop.
        return await asyncio.to_thread(self._get_quote_sync, symbol, market)

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        return await asyncio.to_thread(self._get_kline_sync, symbol, market, interval, limit)

    async def get_curve(self, symbol: str, market: str, window: str) -> List[CurvePoint]:
        # Curve is derived from minute bars to keep one data source contract.
        bars = await self.get_kline(symbol=symbol, market=market, interval="1m", limit=300)
        return [
            CurvePoint(
                symbol=bar.symbol,
                market=bar.market,
                ts=bar.ts,
                price=bar.close,
                volume=bar.volume,
                source=self.provider_id,
            )
            for bar in bars
        ]

    def _get_quote_sync(self, symbol: str, market: str) -> Quote:
        import yfinance as yf

        last_error: Exception | None = None
        for yf_symbol in self._yfinance_symbol_candidates(symbol=symbol, market=market):
            try:
                ticker = yf.Ticker(yf_symbol)
                info = ticker.fast_info
                has_price = (
                    info.get("last_price") is not None
                    or info.get("regular_market_price") is not None
                )
                if not has_price:
                    raise ValueError(f"No quote data for symbol: {yf_symbol}")
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                price = float(
                    info.get("last_price") or info.get("regular_market_price") or 0.0
                )
                prev = info.get("previous_close") or info.get(
                    "regular_market_previous_close"
                )
                change = None
                pct = None
                if prev:
                    change = price - float(prev)
                    if float(prev) != 0:
                        pct = change / float(prev) * 100
                return Quote(
                    symbol=normalize_symbol(symbol, market),
                    market=market.upper(),
                    ts=now,
                    price=price,
                    change=change,
                    change_percent=pct,
                    volume=float(info.get("last_volume"))
                    if info.get("last_volume") is not None
                    else None,
                    currency=str(info.get("currency") or ""),
                    source=self.provider_id,
                )
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise ValueError("Unable to resolve yfinance symbol for quote.")

    def _get_kline_sync(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        import yfinance as yf

        interval_map = {"1m": "1m", "5m": "5m", "1d": "1d"}
        period_map = {"1m": "5d", "5m": "1mo", "1d": "1y"}
        # Fetch a broader period and trim locally, improving compatibility across symbols.
        yf_interval = interval_map.get(interval, "1d")
        yf_period = period_map.get(interval, "1mo")
        normalized = normalize_symbol(symbol, market)
        for yf_symbol in self._yfinance_symbol_candidates(symbol=symbol, market=market):
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period=yf_period, interval=yf_interval)
            if hist is None or hist.empty:
                continue

            rows: List[KLineBar] = []
            for idx, row in hist.tail(limit).iterrows():
                ts = idx.to_pydatetime().isoformat(timespec="seconds")
                rows.append(
                    KLineBar(
                        symbol=normalized,
                        market=market.upper(),
                        interval=interval,
                        ts=ts,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row["Volume"])
                        if row.get("Volume") is not None
                        else None,
                        source=self.provider_id,
                    )
                )
            if rows:
                return rows
        return []

    @staticmethod
    def _yfinance_symbol_candidates(symbol: str, market: str) -> List[str]:
        primary = to_yfinance_symbol(symbol, market)
        candidates: List[str] = [primary]
        if market.upper() == "HK":
            # Some HK indices are available without "^" and with ".HK" suffix.
            base = primary.lstrip("^")
            if base and base not in candidates:
                candidates.append(base)
            if base and not base.endswith(".HK"):
                hk_variant = f"{base}.HK"
                if hk_variant not in candidates:
                    candidates.append(hk_variant)
        return candidates
