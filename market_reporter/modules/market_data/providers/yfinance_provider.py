from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Optional

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_yfinance_symbol,
)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_iso_seconds(raw: Any) -> str:
    if hasattr(raw, "to_pydatetime"):
        return raw.to_pydatetime().isoformat(timespec="seconds")
    if isinstance(raw, datetime):
        return raw.isoformat(timespec="seconds")
    return str(raw)


class YahooFinanceMarketDataProvider:
    provider_id = "yfinance"

    async def get_quote(self, symbol: str, market: str) -> Quote:
        # yfinance SDK is sync; run in thread to avoid blocking event loop.
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
        # Curve is derived from minute bars to keep one data source contract.
        bars = await self.get_kline(
            symbol=symbol, market=market, interval="1m", limit=300
        )
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
                    quote_from_history = self._quote_from_history(
                        ticker=ticker,
                        symbol=symbol,
                        market=market,
                        currency=str(info.get("currency") or ""),
                    )
                    if quote_from_history is not None:
                        return quote_from_history
                    raise ValueError(f"No quote data for symbol: {yf_symbol}")
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                price = _as_float(
                    info.get("last_price") or info.get("regular_market_price")
                )
                if price is None:
                    raise ValueError(f"No quote data for symbol: {yf_symbol}")
                prev = _as_float(
                    info.get("previous_close")
                    or info.get("regular_market_previous_close")
                )
                change = None
                pct = None
                if prev:
                    change = price - prev
                    if prev != 0:
                        pct = change / prev * 100
                volume = _as_float(info.get("last_volume"))
                return Quote(
                    symbol=normalize_symbol(symbol, market),
                    market=market.upper(),
                    ts=now,
                    price=price,
                    change=change,
                    change_percent=pct,
                    volume=volume,
                    currency=str(info.get("currency") or ""),
                    source=self.provider_id,
                )
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise ValueError("Unable to resolve yfinance symbol for quote.")

    def _quote_from_history(
        self,
        ticker,
        symbol: str,
        market: str,
        currency: str,
    ) -> Quote | None:
        hist = ticker.history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        latest_close = _as_float(closes.iloc[-1])
        if latest_close is None:
            return None
        prev_close = _as_float(closes.iloc[-2]) if len(closes) >= 2 else None
        change = None
        pct = None
        if prev_close and prev_close != 0:
            change = latest_close - prev_close
            pct = change / prev_close * 100

        latest_row = hist.iloc[-1]
        ts_raw = closes.index[-1]
        ts = _to_iso_seconds(ts_raw)
        volume_value = latest_row.get("Volume") if hasattr(latest_row, "get") else None
        volume = _as_float(volume_value)

        return Quote(
            symbol=normalize_symbol(symbol, market),
            market=market.upper(),
            ts=ts,
            price=latest_close,
            change=change,
            change_percent=pct,
            volume=volume,
            currency=currency,
            source=self.provider_id,
        )

    def _get_kline_sync(
        self, symbol: str, market: str, interval: str, limit: int
    ) -> List[KLineBar]:
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
                open_value = _as_float(row.get("Open") if hasattr(row, "get") else None)
                high_value = _as_float(row.get("High") if hasattr(row, "get") else None)
                low_value = _as_float(row.get("Low") if hasattr(row, "get") else None)
                close_value = _as_float(
                    row.get("Close") if hasattr(row, "get") else None
                )
                if (
                    open_value is None
                    or high_value is None
                    or low_value is None
                    or close_value is None
                ):
                    continue
                ts = _to_iso_seconds(idx)
                rows.append(
                    KLineBar(
                        symbol=normalized,
                        market=market.upper(),
                        interval=interval,
                        ts=ts,
                        open=open_value,
                        high=high_value,
                        low=low_value,
                        close=close_value,
                        volume=_as_float(
                            row.get("Volume") if hasattr(row, "get") else None
                        ),
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
