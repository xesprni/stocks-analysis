"""Thin wrapper exposing Longbridge SDK data capabilities as a tool.

The model decides what data to request; this tool only fetches and returns
raw results from the Longbridge OpenAPI.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.analysis.agent.core.tool_protocol import ToolDefinition
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_longbridge_symbol,
)

logger = logging.getLogger(__name__)

_NAME = "get_metrics"

_SPEC = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": (
                "Data type to fetch from Longbridge. "
                "candlesticks: historical OHLCV bars. "
                "quote: real-time price quote. "
                "static_info: company name, shares, listing date, EPS, BPS, dividend. "
                "calc_indexes: PE, PB, market cap, turnover, volume ratio. "
                "intraday: intraday minute-level price curve."
            ),
            "enum": [
                "candlesticks",
                "quote",
                "static_info",
                "calc_indexes",
                "intraday",
            ],
        },
        "symbol": {"type": "string", "description": "Stock ticker symbol."},
        "market": {
            "type": "string",
            "description": "Market: CN, HK, US. Inferred from symbol suffix if omitted.",
        },
        "interval": {
            "type": "string",
            "description": (
                "Candlestick interval (for candlesticks action): "
                "1m, 5m, 15m, 30m, 60m, 1d, 1w, 1M. Default: 1d."
            ),
        },
        "count": {
            "type": "integer",
            "description": "Number of data points to return (default 200, max 500).",
        },
        "start": {
            "type": "string",
            "description": "Start date YYYY-MM-DD (for candlesticks, optional).",
        },
        "end": {
            "type": "string",
            "description": "End date YYYY-MM-DD (for candlesticks, optional).",
        },
    },
    "required": ["action", "symbol"],
}


def get_definition() -> ToolDefinition:
    return ToolDefinition(
        name=_NAME,
        description=(
            "Fetch stock data via Longbridge OpenAPI. "
            "Returns raw candlesticks, quotes, company info, calc indexes, "
            "or intraday curves. The model decides which data types to request."
        ),
        parameters=_SPEC,
        source="builtin",
    )


class BuiltinMetricsTool:
    """Thin wrapper around Longbridge SDK — no computation, no fallback."""

    def __init__(self, lb_config: Optional[LongbridgeConfig] = None) -> None:
        self._lb_config = lb_config
        self._enabled = bool(
            lb_config
            and lb_config.enabled
            and lb_config.app_key
            and lb_config.app_secret
            and lb_config.access_token
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        if not self._enabled:
            return self._error("Longbridge is not configured or credentials missing")

        action = str(kwargs.get("action") or "").strip().lower()
        symbol = str(kwargs.get("symbol") or "").strip()
        market = str(kwargs.get("market") or "").strip().upper()

        if not action or not symbol:
            return self._error("action and symbol are required")

        resolved_market = _infer_market(symbol, fallback=market or "US")
        normalized = normalize_symbol(symbol, resolved_market)

        dispatch = {
            "candlesticks": self._candlesticks,
            "quote": self._quote,
            "static_info": self._static_info,
            "calc_indexes": self._calc_indexes,
            "intraday": self._intraday,
        }
        handler = dispatch.get(action)
        if handler is None:
            return self._error(f"Unknown action: {action}")

        try:
            return await handler(symbol=normalized, market=resolved_market, kwargs=kwargs)
        except Exception as exc:
            logger.exception("get_metrics action=%s failed for %s", action, normalized)
            return self._error(str(exc), action=action, symbol=normalized, market=resolved_market)

    # ------------------------------------------------------------------
    # candlesticks
    # ------------------------------------------------------------------

    async def _candlesticks(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        interval = str(kwargs.get("interval") or "1d").strip()
        count = min(int(kwargs.get("count") or 200), 500)
        start = str(kwargs.get("start") or "").strip()
        end = str(kwargs.get("end") or "").strip()
        return await asyncio.to_thread(
            self._candlesticks_sync, symbol, market, interval, count, start, end,
        )

    def _candlesticks_sync(
        self,
        symbol: str,
        market: str,
        interval: str,
        count: int,
        start: str,
        end: str,
    ) -> Dict[str, Any]:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        period = _map_period(interval)
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
                lb_symbol, period, AdjustType.ForwardAdjust,
                start=start_date, end=end_date,
            )
        except Exception:
            candlesticks = ctx.candlesticks(
                lb_symbol, period, count, AdjustType.ForwardAdjust,
            )

        bars = []
        for c in candlesticks:
            ts = c.timestamp.isoformat(timespec="seconds") if c.timestamp else ""
            bars.append({
                "ts": ts,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume) if c.volume is not None else None,
            })

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = bars[-1]["ts"] if bars else retrieved_at
        return {
            "action": "candlesticks",
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "adjusted": True,
            "bars": bars,
            "as_of": as_of,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": [] if bars else ["empty_candlesticks"],
        }

    # ------------------------------------------------------------------
    # quote
    # ------------------------------------------------------------------

    async def _quote(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._quote_sync, symbol, market)

    def _quote_sync(self, symbol: str, market: str) -> Dict[str, Any]:
        from longbridge.openapi import Config, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)
        quote_rows = ctx.quote([lb_symbol])
        if not quote_rows:
            return self._empty("quote", symbol, market, ["no_quote_data"])

        row = quote_rows[0]
        price = float(getattr(row, "last_done", 0.0) or 0.0)
        prev_close_raw = getattr(row, "prev_close", None)
        prev_close = float(prev_close_raw) if prev_close_raw else None
        change = None
        change_percent = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            change_percent = change / prev_close * 100

        ts_raw = getattr(row, "timestamp", None)
        ts = (
            ts_raw.isoformat(timespec="seconds")
            if ts_raw
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        volume_raw = getattr(row, "volume", None)
        volume = float(volume_raw) if volume_raw is not None else None

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": "quote",
            "symbol": symbol,
            "market": market,
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_percent": change_percent,
            "volume": volume,
            "as_of": ts,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": [],
        }

    # ------------------------------------------------------------------
    # static_info
    # ------------------------------------------------------------------

    async def _static_info(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._static_info_sync, symbol, market)

    def _static_info_sync(self, symbol: str, market: str) -> Dict[str, Any]:
        from longbridge.openapi import Config, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: List[str] = []
        info: Dict[str, Any] = {"symbol": symbol, "market": market}

        static_list = ctx.static_info([lb_symbol])
        if static_list:
            si = static_list[0]
            info["name_cn"] = str(getattr(si, "name_cn", "") or "")
            info["name_en"] = str(getattr(si, "name_en", "") or "")
            info["name_hk"] = str(getattr(si, "name_hk", "") or "")
            info["listing_date"] = str(getattr(si, "listing_date", "") or "")
            info["total_shares"] = _safe_float(getattr(si, "total_shares", None))
            info["circulating_shares"] = _safe_float(getattr(si, "circulating_shares", None))
            info["eps_ttm"] = _safe_float(getattr(si, "eps_ttm", None))
            info["bps"] = _safe_float(getattr(si, "bps", None))
            info["dividend_yield"] = _safe_float(getattr(si, "dividend_yield", None))
        else:
            warnings.append("empty_static_info")

        return {
            "action": "static_info",
            "symbol": symbol,
            "market": market,
            "info": info,
            "as_of": retrieved_at,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # calc_indexes
    # ------------------------------------------------------------------

    async def _calc_indexes(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._calc_indexes_sync, symbol, market)

    def _calc_indexes_sync(self, symbol: str, market: str) -> Dict[str, Any]:
        from longbridge.openapi import CalcIndex, Config, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: List[str] = []
        metrics: Dict[str, Optional[float]] = {}

        try:
            calc_indexes = [
                CalcIndex.PeTtmRatio,
                CalcIndex.PbRatio,
                CalcIndex.TotalMarketValue,
                CalcIndex.DividendRatioTtm,
                CalcIndex.TurnoverRate,
                CalcIndex.VolumeRatio,
            ]
            calc_list = ctx.calc_indexes([lb_symbol], calc_indexes)
            if calc_list:
                ci = calc_list[0]
                metrics["trailing_pe"] = _safe_float(getattr(ci, "pe_ttm_ratio", None))
                metrics["pb_ratio"] = _safe_float(getattr(ci, "pb_ratio", None))
                metrics["market_cap"] = _safe_float(getattr(ci, "total_market_value", None))
                metrics["dividend_ratio_ttm"] = _safe_float(getattr(ci, "dividend_ratio_ttm", None))
                metrics["turnover_rate"] = _safe_float(getattr(ci, "turnover_rate", None))
                metrics["volume_ratio"] = _safe_float(getattr(ci, "volume_ratio", None))
        except Exception as exc:
            warnings.append(f"calc_indexes_failed:{exc}")

        if not any(v is not None for v in metrics.values()):
            warnings.append("empty_calc_indexes")

        return {
            "action": "calc_indexes",
            "symbol": symbol,
            "market": market,
            "metrics": metrics,
            "as_of": retrieved_at,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # intraday
    # ------------------------------------------------------------------

    async def _intraday(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._intraday_sync, symbol, market)

    def _intraday_sync(self, symbol: str, market: str) -> Dict[str, Any]:
        from longbridge.openapi import Config, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        intraday = ctx.intraday(lb_symbol)
        points: List[Dict[str, Any]] = []
        for line in intraday:
            ts = line.timestamp.isoformat(timespec="seconds") if line.timestamp else ""
            points.append({
                "ts": ts,
                "price": float(line.price),
                "volume": float(line.volume) if line.volume is not None else None,
            })

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": "intraday",
            "symbol": symbol,
            "market": market,
            "points": points,
            "as_of": retrieved_at,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": [] if points else ["empty_intraday"],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _error(
        self,
        message: str,
        action: str = "",
        symbol: str = "",
        market: str = "",
    ) -> Dict[str, Any]:
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": action,
            "symbol": symbol,
            "market": market,
            "as_of": retrieved_at,
            "source": "error",
            "retrieved_at": retrieved_at,
            "warnings": [f"error:{message}"],
        }

    @staticmethod
    def _empty(
        action: str, symbol: str, market: str, warnings: List[str],
    ) -> Dict[str, Any]:
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": action,
            "symbol": symbol,
            "market": market,
            "as_of": retrieved_at,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _map_period(interval: str):
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
    return mapping.get(interval, Period.Day)


def _infer_market(symbol: str, fallback: str = "US") -> str:
    raw = (symbol or "").strip().upper()
    if raw.endswith(".HK"):
        return "HK"
    if raw.endswith((".SH", ".SZ", ".BJ")):
        return "CN"
    return fallback.upper() if fallback else "US"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None
