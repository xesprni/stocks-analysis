from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_yfinance_symbol,
)
from market_reporter.modules.market_data.yf_throttle import (
    YF_MAX_RETRIES as _MAX_RETRIES,
    YF_RETRY_BASE_DELAY as _RETRY_BASE_DELAY,
    YF_SEMAPHORE as _YF_SEMAPHORE,
    yf_throttle as _yf_throttle,
)

logger = logging.getLogger(__name__)


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

    async def get_quotes(self, items: List[Tuple[str, str]]) -> List[Quote]:
        """Batch fetch quotes using ``yf.download`` (single HTTP round-trip)."""
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

    # ------------------------------------------------------------------
    # Batch quote via yf.download
    # ------------------------------------------------------------------

    def _get_quotes_sync(self, items: List[Tuple[str, str]]) -> List[Quote]:
        if not items:
            return []
        import yfinance as yf

        # Build mapping: yf_symbol -> (original_symbol, market)
        yf_to_orig: dict[str, Tuple[str, str]] = {}
        for symbol, market in items:
            yf_symbol = to_yfinance_symbol(symbol, market)
            yf_to_orig[yf_symbol] = (symbol, market)

        yf_symbols = list(yf_to_orig.keys())

        data = self._download_with_retry(yf_symbols, period="5d", interval="1d")
        if data is None or data.empty:
            return []

        quotes: List[Quote] = []
        multi_ticker = len(yf_symbols) > 1

        for yf_sym, (orig_symbol, orig_market) in yf_to_orig.items():
            try:
                if multi_ticker:
                    if yf_sym not in data.columns.get_level_values(0):
                        continue
                    closes = data[yf_sym]["Close"].dropna()
                    volumes_series = data[yf_sym].get("Volume")
                else:
                    closes = data["Close"].dropna()
                    volumes_series = data.get("Volume")

                if closes.empty:
                    continue

                latest_close = _as_float(closes.iloc[-1])
                if latest_close is None:
                    continue
                prev_close = _as_float(closes.iloc[-2]) if len(closes) >= 2 else None
                change = None
                pct = None
                if prev_close and prev_close != 0:
                    change = latest_close - prev_close
                    pct = change / prev_close * 100

                ts = _to_iso_seconds(closes.index[-1])
                volume = None
                if volumes_series is not None:
                    vol_clean = volumes_series.dropna()
                    if not vol_clean.empty:
                        volume = _as_float(vol_clean.iloc[-1])

                quotes.append(
                    Quote(
                        symbol=normalize_symbol(orig_symbol, orig_market),
                        market=orig_market.upper(),
                        ts=ts,
                        price=latest_close,
                        change=change,
                        change_percent=pct,
                        volume=volume,
                        currency="USD" if orig_market.upper() == "US" else "",
                        source=self.provider_id,
                    )
                )
            except Exception as exc:
                logger.debug("yf.download parse failed for %s: %s", yf_sym, exc)
                continue

        return quotes

    def _download_with_retry(
        self,
        symbols: List[str],
        period: str,
        interval: str,
    ):
        """Call ``yf.download`` with throttling and retry on rate-limit."""
        import yfinance as yf

        for attempt in range(1, _MAX_RETRIES + 1):
            _YF_SEMAPHORE.acquire()
            try:
                _yf_throttle()
                data = yf.download(
                    symbols,
                    period=period,
                    interval=interval,
                    group_by="ticker" if len(symbols) > 1 else "column",
                    progress=False,
                    threads=False,
                )
                if data is not None and not data.empty:
                    return data
                return data
            except Exception as exc:
                if "rate" in str(exc).lower() or "too many" in str(exc).lower():
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "yf.download rate-limited (attempt %d/%d), "
                        "retrying in %.1fs: %s",
                        attempt,
                        _MAX_RETRIES,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    continue
                raise
            finally:
                _YF_SEMAPHORE.release()
        return None

    # ------------------------------------------------------------------
    # Single quote
    # ------------------------------------------------------------------

    def _get_quote_sync(self, symbol: str, market: str) -> Quote:
        import yfinance as yf

        last_error: Exception | None = None
        for yf_symbol in self._yfinance_symbol_candidates(symbol=symbol, market=market):
            for attempt in range(1, _MAX_RETRIES + 1):
                _YF_SEMAPHORE.acquire()
                try:
                    _yf_throttle()
                    quote = self._fetch_single_quote(yf, yf_symbol, symbol, market)
                    return quote
                except Exception as exc:
                    is_rate_limit = (
                        "rate" in str(exc).lower() or "too many" in str(exc).lower()
                    )
                    if is_rate_limit and attempt < _MAX_RETRIES:
                        delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            "yfinance rate-limited for %s (attempt %d/%d), "
                            "retrying in %.1fs",
                            yf_symbol,
                            attempt,
                            _MAX_RETRIES,
                            delay,
                        )
                        _YF_SEMAPHORE.release()
                        time.sleep(delay)
                        continue
                    last_error = exc
                    break
                finally:
                    # release only when not already released in the retry path
                    try:
                        _YF_SEMAPHORE.release()
                    except ValueError:
                        pass

        if last_error is not None:
            raise last_error
        raise ValueError("Unable to resolve yfinance symbol for quote.")

    def _fetch_single_quote(
        self, yf: Any, yf_symbol: str, symbol: str, market: str
    ) -> Quote:
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
        price = _as_float(info.get("last_price") or info.get("regular_market_price"))
        if price is None:
            raise ValueError(f"No quote data for symbol: {yf_symbol}")
        prev = _as_float(
            info.get("previous_close") or info.get("regular_market_previous_close")
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
            _YF_SEMAPHORE.acquire()
            try:
                _yf_throttle()
                ticker = yf.Ticker(yf_symbol)
                hist = ticker.history(period=yf_period, interval=yf_interval)
            finally:
                _YF_SEMAPHORE.release()
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
