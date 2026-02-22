from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.analysis.agent.schemas import PriceBar, PriceHistoryResult
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_longbridge_symbol,
)

logger = logging.getLogger(__name__)


def infer_market_from_symbol(symbol: str, fallback: str = "US") -> str:
    raw = (symbol or "").strip().upper()
    if raw.endswith(".HK"):
        return "HK"
    if raw.endswith(".SH") or raw.endswith(".SZ") or raw.endswith(".BJ"):
        return "CN"
    return fallback.upper() if fallback else "US"


class MarketTools:
    def __init__(self, lb_config: Optional[LongbridgeConfig] = None) -> None:
        self._lb_config = lb_config
        self._use_longbridge = bool(
            lb_config
            and lb_config.enabled
            and lb_config.app_key
            and lb_config.app_secret
            and lb_config.access_token
        )

    async def get_price_history(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str,
        adjusted: bool,
        market: Optional[str] = None,
    ) -> PriceHistoryResult:
        if self._use_longbridge:
            try:
                return await asyncio.to_thread(
                    self._get_price_history_longbridge,
                    symbol,
                    start,
                    end,
                    interval,
                    adjusted,
                    market,
                )
            except Exception:
                fallback = await asyncio.to_thread(
                    self._get_price_history_sync,
                    symbol,
                    start,
                    end,
                    interval,
                    adjusted,
                    market,
                )
                fallback.warnings.append("longbridge_failed_fallback_yfinance")
                return fallback

        return await asyncio.to_thread(
            self._get_price_history_sync,
            symbol,
            start,
            end,
            interval,
            adjusted,
            market,
        )

    # ------------------------------------------------------------------
    # Longbridge implementation
    # ------------------------------------------------------------------

    def _get_price_history_longbridge(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str,
        adjusted: bool,
        market: Optional[str],
    ) -> PriceHistoryResult:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        lb_symbol = to_longbridge_symbol(normalized_symbol, resolved_market)

        period_map = {
            "1m": Period.Min_1,
            "5m": Period.Min_5,
            "15m": Period.Min_15,
            "30m": Period.Min_30,
            "60m": Period.Min_60,
            "1d": Period.Day,
            "1wk": Period.Week,
            "1mo": Period.Month,
        }
        period = period_map.get(interval, Period.Day)
        adjust = AdjustType.ForwardAdjust if adjusted else AdjustType.NoAdjust

        assert self._lb_config is not None
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        try:
            from datetime import date as date_cls

            start_date = date_cls.fromisoformat(start[:10]) if start else None
            end_date = date_cls.fromisoformat(end[:10]) if end else None
            candlesticks = ctx.history_candlesticks_by_date(
                lb_symbol,
                period,
                adjust,
                start=start_date,
                end=end_date,
            )
        except Exception:
            # Fallback to count-based candlesticks if date-range method fails.
            candlesticks = ctx.candlesticks(lb_symbol, period, 500, adjust)

        bars = []
        for c in candlesticks:
            ts = c.timestamp.isoformat(timespec="seconds") if c.timestamp else ""
            bars.append(
                PriceBar(
                    ts=ts,
                    open=float(c.open),
                    high=float(c.high),
                    low=float(c.low),
                    close=float(c.close),
                    volume=float(c.volume) if c.volume is not None else None,
                )
            )

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = bars[-1].ts if bars else retrieved_at
        return PriceHistoryResult(
            symbol=normalized_symbol,
            market=resolved_market,
            interval=interval,
            adjusted=bool(adjusted),
            bars=bars,
            as_of=as_of,
            source="longbridge",
            retrieved_at=retrieved_at,
            warnings=[] if bars else ["empty_price_history"],
        )

    # ------------------------------------------------------------------
    # yfinance fallback implementation
    # ------------------------------------------------------------------

    def _get_price_history_sync(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str,
        adjusted: bool,
        market: Optional[str],
    ) -> PriceHistoryResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: list[str] = []

        bars: list[PriceBar] = []
        try:
            ticker = yf.Ticker(normalized_symbol)
            history = ticker.history(
                start=start or None,
                end=end or None,
                interval=interval or "1d",
                auto_adjust=bool(adjusted),
            )
            for idx, row in history.iterrows():
                ts = idx.to_pydatetime().isoformat(timespec="seconds")
                bars.append(
                    PriceBar(
                        ts=ts,
                        open=float(row.get("Open") or 0.0),
                        high=float(row.get("High") or 0.0),
                        low=float(row.get("Low") or 0.0),
                        close=float(row.get("Close") or 0.0),
                        volume=float(row.get("Volume"))
                        if row.get("Volume") is not None
                        else None,
                    )
                )
        except Exception as exc:
            warnings.append(f"yfinance_price_history_failed:{exc}")

        if not bars:
            warnings.append("empty_price_history")
        as_of = bars[-1].ts if bars else retrieved_at
        return PriceHistoryResult(
            symbol=normalized_symbol,
            market=resolved_market,
            interval=interval or "1d",
            adjusted=bool(adjusted),
            bars=bars,
            as_of=as_of,
            source="yfinance",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )
