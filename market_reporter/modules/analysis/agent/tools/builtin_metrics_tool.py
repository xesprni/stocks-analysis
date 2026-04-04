from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from statistics import pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

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
                "Data action to perform. "
                "price_history: historical OHLCV candlesticks. "
                "quote: real-time quote. "
                "fundamentals: PE/PB/EPS/market cap. "
                "financial_reports: income/balance/cashflow statements. "
                "static_info: company name/shares/dividend. "
                "technical_indicators: RSI/MACD/MA/ATR/BOLL etc."
            ),
            "enum": [
                "price_history",
                "quote",
                "fundamentals",
                "financial_reports",
                "static_info",
                "technical_indicators",
            ],
        },
        "symbol": {"type": "string", "description": "Stock ticker symbol."},
        "market": {"type": "string", "description": "Market: CN, HK, US."},
        "interval": {
            "type": "string",
            "description": "Candlestick interval: 1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo.",
        },
        "start": {"type": "string", "description": "Start date (YYYY-MM-DD) for price history."},
        "end": {"type": "string", "description": "End date (YYYY-MM-DD) for price history."},
        "limit": {"type": "integer", "description": "Number of results (for candlesticks or reports)."},
        "indicators": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Technical indicator names: RSI, MACD, MA, EMA, ATR, VOL, BOLL, etc.",
        },
        "indicator_profile": {
            "type": "string",
            "description": "Indicator profile: balanced, trend, momentum.",
            "enum": ["balanced", "trend", "momentum"],
        },
    },
    "required": ["action", "symbol"],
}


def get_definition() -> ToolDefinition:
    return ToolDefinition(
        name=_NAME,
        description=(
            "Get stock market metrics and data via Longbridge SDK. "
            "Supports price history, real-time quotes, fundamentals, financial reports, "
            "company info, and technical indicator computation."
        ),
        parameters=_SPEC,
        source="builtin",
    )


class BuiltinMetricsTool:
    """Unified metrics builtin tool backed by Longbridge SDK."""

    def __init__(self, lb_config: Optional[LongbridgeConfig] = None) -> None:
        self._lb_config = lb_config
        self._use_longbridge = bool(
            lb_config
            and lb_config.enabled
            and lb_config.app_key
            and lb_config.app_secret
            and lb_config.access_token
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        action = str(kwargs.get("action") or "").strip().lower()
        symbol = str(kwargs.get("symbol") or "").strip()
        market = str(kwargs.get("market") or "").strip().upper()
        if not action or not symbol:
            return self._error_result("action and symbol are required", action, symbol, market)

        resolved_market = self._infer_market(symbol, fallback=market or "US")
        normalized = normalize_symbol(symbol, resolved_market)

        dispatch = {
            "price_history": self._price_history,
            "quote": self._quote,
            "fundamentals": self._fundamentals,
            "financial_reports": self._financial_reports,
            "static_info": self._static_info,
            "technical_indicators": self._technical_indicators,
        }
        handler = dispatch.get(action)
        if handler is None:
            return self._error_result(
                f"Unknown action: {action}", action, normalized, resolved_market,
            )
        try:
            return await handler(
                symbol=normalized,
                market=resolved_market,
                kwargs=kwargs,
            )
        except Exception as exc:
            logger.exception("get_metrics action=%s failed for %s", action, normalized)
            return self._error_result(str(exc), action, normalized, resolved_market)

    # ------------------------------------------------------------------
    # price_history
    # ------------------------------------------------------------------

    async def _price_history(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        start = str(kwargs.get("start") or "").strip()
        end = str(kwargs.get("end") or "").strip()
        interval = str(kwargs.get("interval") or "1d").strip()
        limit = int(kwargs.get("limit") or 500)

        if self._use_longbridge:
            try:
                return await asyncio.to_thread(
                    self._price_history_longbridge, symbol, market, start, end, interval, limit,
                )
            except Exception:
                result = await asyncio.to_thread(
                    self._price_history_yfinance, symbol, market, start, end, interval, limit,
                )
                result["warnings"].append("longbridge_failed_fallback_yfinance")
                return result

        return await asyncio.to_thread(
            self._price_history_yfinance, symbol, market, start, end, interval, limit,
        )

    def _price_history_longbridge(
        self, symbol: str, market: str, start: str, end: str, interval: str, limit: int,
    ) -> Dict[str, Any]:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        period_map = {
            "1m": Period.Min_1, "5m": Period.Min_5, "15m": Period.Min_15,
            "30m": Period.Min_30, "60m": Period.Min_60, "1d": Period.Day,
            "1wk": Period.Week, "1mo": Period.Month,
        }
        period = period_map.get(interval, Period.Day)
        adjust = AdjustType.ForwardAdjust
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
                lb_symbol, period, adjust, start=start_date, end=end_date,
            )
        except Exception:
            candlesticks = ctx.candlesticks(lb_symbol, period, limit, adjust)

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
            "action": "price_history",
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "adjusted": True,
            "bars": bars,
            "as_of": as_of,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": [] if bars else ["empty_price_history"],
        }

    def _price_history_yfinance(
        self, symbol: str, market: str, start: str, end: str, interval: str, limit: int,
    ) -> Dict[str, Any]:
        import yfinance as yf

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: List[str] = []
        bars: List[Dict[str, Any]] = []
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(
                start=start or None, end=end or None,
                interval=interval or "1d", auto_adjust=True,
            )
            for idx, row in history.iterrows():
                ts = idx.to_pydatetime().isoformat(timespec="seconds")
                bars.append({
                    "ts": ts,
                    "open": float(row.get("Open") or 0.0),
                    "high": float(row.get("High") or 0.0),
                    "low": float(row.get("Low") or 0.0),
                    "close": float(row.get("Close") or 0.0),
                    "volume": float(row["Volume"]) if row.get("Volume") is not None else None,
                })
        except Exception as exc:
            warnings.append(f"yfinance_price_history_failed:{exc}")

        if not bars:
            warnings.append("empty_price_history")
        as_of = bars[-1]["ts"] if bars else retrieved_at
        return {
            "action": "price_history",
            "symbol": symbol,
            "market": market,
            "interval": interval or "1d",
            "adjusted": True,
            "bars": bars,
            "as_of": as_of,
            "source": "yfinance",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # quote
    # ------------------------------------------------------------------

    async def _quote(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self._use_longbridge:
            return await asyncio.to_thread(self._quote_yfinance, symbol, market)
        try:
            return await asyncio.to_thread(self._quote_longbridge, symbol, market)
        except Exception:
            result = await asyncio.to_thread(self._quote_yfinance, symbol, market)
            result["warnings"].append("longbridge_failed_fallback_yfinance")
            return result

    def _quote_longbridge(self, symbol: str, market: str) -> Dict[str, Any]:
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
            return self._empty_result("quote", symbol, market, warnings=["no_quote_data"])

        row = quote_rows[0]
        price = float(getattr(row, "last_done", 0.0) or 0.0)
        prev_close = float(getattr(row, "prev_close", 0)) if getattr(row, "prev_close", None) else None
        change = None
        pct = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            pct = change / prev_close * 100

        ts_raw = getattr(row, "timestamp", None)
        ts = ts_raw.isoformat(timespec="seconds") if ts_raw else datetime.now(timezone.utc).isoformat(timespec="seconds")
        volume = float(getattr(row, "volume", 0)) if getattr(row, "volume", None) is not None else None

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": "quote",
            "symbol": symbol,
            "market": market,
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_percent": pct,
            "volume": volume,
            "as_of": ts,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": [],
        }

    def _quote_yfinance(self, symbol: str, market: str) -> Dict[str, Any]:
        import yfinance as yf

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, "info", {}) or {}
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            prev_close = self._safe_float(info.get("previousClose"))
            change = None
            pct = None
            if prev_close and prev_close != 0:
                change = price - prev_close
                pct = change / prev_close * 100
            return {
                "action": "quote",
                "symbol": symbol,
                "market": market,
                "price": price,
                "prev_close": prev_close,
                "change": change,
                "change_percent": pct,
                "volume": self._safe_float(info.get("volume")),
                "as_of": retrieved_at,
                "source": "yfinance",
                "retrieved_at": retrieved_at,
                "warnings": [],
            }
        except Exception as exc:
            return self._empty_result("quote", symbol, market, warnings=[f"yfinance_quote_failed:{exc}"])

    # ------------------------------------------------------------------
    # fundamentals
    # ------------------------------------------------------------------

    async def _fundamentals(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._use_longbridge:
            try:
                return await asyncio.to_thread(self._fundamentals_longbridge, symbol, market)
            except Exception:
                result = await asyncio.to_thread(self._fundamentals_yfinance, symbol, market)
                result["warnings"].append("longbridge_failed_fallback_yfinance")
                return result
        return await asyncio.to_thread(self._fundamentals_yfinance, symbol, market)

    def _fundamentals_longbridge(self, symbol: str, market: str) -> Dict[str, Any]:
        from longbridge.openapi import CalcIndex, Config, QuoteContext

        lb_symbol = to_longbridge_symbol(symbol, market)
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        metrics: Dict[str, Optional[float]] = {}
        warnings: List[str] = []

        try:
            static_list = ctx.static_info([lb_symbol])
            if static_list:
                si = static_list[0]
                metrics["eps_ttm"] = self._safe_float(getattr(si, "eps_ttm", None))
                metrics["bps"] = self._safe_float(getattr(si, "bps", None))
                metrics["total_shares"] = self._safe_float(getattr(si, "total_shares", None))
                metrics["circulating_shares"] = self._safe_float(getattr(si, "circulating_shares", None))
                metrics["dividend_yield"] = self._safe_float(getattr(si, "dividend_yield", None))
        except Exception:
            warnings.append("longbridge_static_info_failed")

        try:
            calc_indexes = [
                CalcIndex.PeTtmRatio, CalcIndex.PbRatio, CalcIndex.TotalMarketValue,
                CalcIndex.DividendRatioTtm, CalcIndex.TurnoverRate, CalcIndex.VolumeRatio,
            ]
            calc_list = ctx.calc_indexes([lb_symbol], calc_indexes)
            if calc_list:
                ci = calc_list[0]
                metrics["trailing_pe"] = self._safe_float(getattr(ci, "pe_ttm_ratio", None))
                metrics["pb_ratio"] = self._safe_float(getattr(ci, "pb_ratio", None))
                metrics["market_cap"] = self._safe_float(getattr(ci, "total_market_value", None))
                metrics["dividend_ratio_ttm"] = self._safe_float(getattr(ci, "dividend_ratio_ttm", None))
                metrics["turnover_rate"] = self._safe_float(getattr(ci, "turnover_rate", None))
                metrics["volume_ratio"] = self._safe_float(getattr(ci, "volume_ratio", None))
        except Exception:
            warnings.append("longbridge_calc_indexes_failed")

        if not any(v is not None for v in metrics.values()):
            warnings.append("empty_fundamentals")

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "action": "fundamentals",
            "symbol": symbol,
            "market": market,
            "metrics": metrics,
            "as_of": retrieved_at,
            "source": "longbridge",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    def _fundamentals_yfinance(self, symbol: str, market: str) -> Dict[str, Any]:
        import yfinance as yf

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        metrics: Dict[str, Optional[float]] = {}
        warnings: List[str] = []

        try:
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, "info", {}) or {}
            metrics["trailing_pe"] = self._safe_float(info.get("trailingPE"))
            metrics["pb_ratio"] = self._safe_float(info.get("priceToBook"))
            metrics["market_cap"] = self._safe_float(info.get("marketCap"))
            metrics["dividend_yield"] = self._safe_float(info.get("dividendYield"))
            metrics["eps_ttm"] = self._safe_float(info.get("trailingEps"))
            metrics["revenue"] = self._safe_float(info.get("totalRevenue"))
            metrics["net_income"] = self._safe_float(info.get("netIncomeToCommon"))

            cashflow = getattr(ticker, "cashflow", None)
            if hasattr(cashflow, "columns") and len(getattr(cashflow, "columns", [])):
                latest_col = cashflow.columns[0]
                metrics["operating_cash_flow"] = self._pick_metric(
                    cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], latest_col,
                )
                metrics["free_cash_flow"] = self._pick_metric(cashflow, ["Free Cash Flow"], latest_col)

            balance = getattr(ticker, "balance_sheet", None)
            if hasattr(balance, "columns") and len(getattr(balance, "columns", [])):
                latest_col = balance.columns[0]
                metrics["total_assets"] = self._pick_metric(balance, ["Total Assets"], latest_col)
                metrics["total_liabilities"] = self._pick_metric(
                    balance, ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"], latest_col,
                )
                metrics["shareholder_equity"] = self._pick_metric(
                    balance, ["Stockholders Equity", "Total Stockholder Equity"], latest_col,
                )
        except Exception as exc:
            warnings.append(f"yfinance_fundamentals_failed:{exc}")

        if not any(v is not None for v in metrics.values()):
            warnings.append("empty_fundamentals")

        return {
            "action": "fundamentals",
            "symbol": symbol,
            "market": market,
            "metrics": metrics,
            "as_of": retrieved_at,
            "source": "yfinance",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # financial_reports
    # ------------------------------------------------------------------

    async def _financial_reports(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        limit = int(kwargs.get("limit") or 6)
        return await asyncio.to_thread(self._financial_reports_sync, symbol, market, limit)

    def _financial_reports_sync(self, symbol: str, market: str, limit: int) -> Dict[str, Any]:
        import yfinance as yf

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: List[str] = []
        reports: List[Dict[str, Any]] = []

        try:
            ticker = yf.Ticker(symbol)
            datasets = [
                ("income", "annual", getattr(ticker, "financials", None)),
                ("balance", "annual", getattr(ticker, "balance_sheet", None)),
                ("cashflow", "annual", getattr(ticker, "cashflow", None)),
                ("income", "quarterly", getattr(ticker, "quarterly_financials", None)),
                ("balance", "quarterly", getattr(ticker, "quarterly_balance_sheet", None)),
                ("cashflow", "quarterly", getattr(ticker, "quarterly_cashflow", None)),
            ]
            all_rows: List[Dict[str, Any]] = []
            for statement_type, period_type, frame in datasets:
                if frame is None or not hasattr(frame, "columns") or not hasattr(frame, "index"):
                    continue
                columns = list(getattr(frame, "columns", []))
                if not columns:
                    continue
                for column in columns[: max(limit, 1)]:
                    item_metrics: Dict[str, Optional[float]] = {}
                    metric_candidates = {
                        "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
                        "net_income": ["Net Income", "Net Income Common Stockholders"],
                        "operating_cash_flow": ["Operating Cash Flow", "Total Cash From Operating Activities"],
                        "free_cash_flow": ["Free Cash Flow"],
                        "total_assets": ["Total Assets"],
                        "total_liabilities": ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"],
                        "shareholder_equity": ["Stockholders Equity", "Total Stockholder Equity"],
                        "gross_profit": ["Gross Profit"],
                        "operating_income": ["Operating Income"],
                    }
                    for key, candidates in metric_candidates.items():
                        item_metrics[key] = self._pick_metric(frame, candidates, column)
                    if not any(v is not None for v in item_metrics.values()):
                        continue
                    report_date = self._format_date(column)
                    all_rows.append({
                        "report_date": report_date,
                        "statement_type": statement_type,
                        "period_type": period_type,
                        "metrics": item_metrics,
                    })

            all_rows.sort(key=lambda r: r["report_date"], reverse=True)
            seen: set[str] = set()
            for row in all_rows:
                key = f"{row['report_date']}:{row['statement_type']}:{row['period_type']}"
                if key in seen:
                    continue
                seen.add(key)
                reports.append(row)
                if len(reports) >= max(limit, 1):
                    break

        except Exception as exc:
            warnings.append(f"financial_reports_failed:{exc}")

        if not reports:
            warnings.append("empty_financial_reports")

        latest_metrics = dict(reports[0]["metrics"]) if reports else {}
        as_of = reports[0]["report_date"] if reports else retrieved_at
        return {
            "action": "financial_reports",
            "symbol": symbol,
            "market": market,
            "reports": reports,
            "latest_metrics": latest_metrics,
            "as_of": as_of,
            "source": "yfinance",
            "retrieved_at": retrieved_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # static_info
    # ------------------------------------------------------------------

    async def _static_info(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self._use_longbridge:
            return self._empty_result("static_info", symbol, market, warnings=["longbridge_not_configured"])
        return await asyncio.to_thread(self._static_info_longbridge, symbol, market)

    def _static_info_longbridge(self, symbol: str, market: str) -> Dict[str, Any]:
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

        try:
            static_list = ctx.static_info([lb_symbol])
            if static_list:
                si = static_list[0]
                info["name_cn"] = str(getattr(si, "name_cn", "") or "")
                info["name_en"] = str(getattr(si, "name_en", "") or "")
                info["name_hk"] = str(getattr(si, "name_hk", "") or "")
                info["listing_date"] = str(getattr(si, "listing_date", "") or "")
                info["total_shares"] = self._safe_float(getattr(si, "total_shares", None))
                info["circulating_shares"] = self._safe_float(getattr(si, "circulating_shares", None))
                info["eps_ttm"] = self._safe_float(getattr(si, "eps_ttm", None))
                info["bps"] = self._safe_float(getattr(si, "bps", None))
                info["dividend_yield"] = self._safe_float(getattr(si, "dividend_yield", None))
        except Exception as exc:
            warnings.append(f"static_info_failed:{exc}")

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
    # technical_indicators
    # ------------------------------------------------------------------

    async def _technical_indicators(
        self, symbol: str, market: str, kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        indicators = kwargs.get("indicators")
        if isinstance(indicators, list):
            wanted = [str(i).strip().upper() for i in indicators if str(i).strip()]
        else:
            wanted = ["RSI", "MACD", "MA", "ATR", "VOL"]
        indicator_profile = str(kwargs.get("indicator_profile") or "balanced")

        # Fetch price data first
        interval = str(kwargs.get("interval") or "1d").strip()
        start = str(kwargs.get("start") or "").strip()
        end = str(kwargs.get("end") or "").strip()

        price_result = await self._price_history(
            symbol, market,
            {"start": start, "end": end, "interval": interval, "limit": 500},
        )
        bars = price_result.get("bars", [])
        if not bars:
            retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return {
                "action": "technical_indicators",
                "symbol": symbol,
                "market": market,
                "values": {},
                "trend": {},
                "momentum": {},
                "volume_price": {},
                "patterns": {},
                "support_resistance": {},
                "strategy": {},
                "signal_timeline": [],
                "as_of": retrieved_at,
                "source": "computed",
                "retrieved_at": retrieved_at,
                "warnings": ["empty_price_data"],
            }

        result = self._compute_indicators(
            bars=bars,
            wanted=wanted,
            symbol=symbol,
            indicator_profile=indicator_profile,
        )
        result["action"] = "technical_indicators"
        result["symbol"] = symbol
        result["market"] = market
        return result

    def _compute_indicators(
        self,
        bars: List[Dict[str, Any]],
        wanted: List[str],
        symbol: str,
        indicator_profile: str,
    ) -> Dict[str, Any]:
        closes = [float(b.get("close", 0)) for b in bars]
        highs = [float(b.get("high", 0)) for b in bars]
        lows = [float(b.get("low", 0)) for b in bars]
        volumes = [float(b.get("volume") or 0) for b in bars]

        values: Dict[str, Optional[float]] = {}
        trend: Dict[str, Any] = {}
        momentum: Dict[str, Any] = {}
        volume_price: Dict[str, Any] = {}
        support_resistance: Dict[str, Any] = {}

        n = len(closes)
        if n < 2:
            return {"values": values, "trend": trend, "momentum": momentum,
                    "volume_price": volume_price, "patterns": {},
                    "support_resistance": support_resistance, "strategy": {},
                    "signal_timeline": [], "warnings": ["insufficient_data"]}

        # MA
        if any(k in w for w in wanted for k in ("MA", "SMA", "EMA")):
            for period in [5, 10, 20, 60]:
                if n >= period:
                    sma = sum(closes[-period:]) / period
                    values[f"sma{period}"] = round(sma, 4)
            if n >= 12:
                ema12 = self._ema(closes, 12)
                values["ema12"] = round(ema12, 4) if ema12 is not None else None
            if n >= 26:
                ema26 = self._ema(closes, 26)
                values["ema26"] = round(ema26, 4) if ema26 is not None else None

            # Trend direction
            if n >= 20:
                sma5 = values.get("sma5")
                sma20 = values.get("sma20")
                if sma5 is not None and sma20 is not None:
                    trend["primary"] = {
                        "direction": "up" if sma5 > sma20 else "down" if sma5 < sma20 else "flat",
                        "ma_state": "bullish" if sma5 > sma20 else "bearish",
                    }

        # RSI
        if "RSI" in wanted and n >= 15:
            rsi_val = self._rsi(closes, 14)
            values["rsi_14"] = round(rsi_val, 2) if rsi_val is not None else None
            momentum["rsi"] = {
                "value": values.get("rsi_14"),
                "zone": "overbought" if (values.get("rsi_14") or 50) > 70
                else "oversold" if (values.get("rsi_14") or 50) < 30 else "neutral",
            }

        # MACD
        if "MACD" in wanted and n >= 26:
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            if ema12 is not None and ema26 is not None:
                macd_line = ema12 - ema26
                values["macd"] = round(macd_line, 4)
                momentum["macd"] = {"macd_line": round(macd_line, 4)}

        # ATR
        if "ATR" in wanted and n >= 15:
            atr_val = self._atr(highs, lows, closes, 14)
            values["atr_14"] = round(atr_val, 4) if atr_val is not None else None

        # BOLL
        if "BOLL" in wanted and n >= 20:
            sma20 = values.get("sma20") or (sum(closes[-20:]) / 20 if n >= 20 else None)
            if sma20 is not None:
                std = pstdev(closes[-20:]) if n >= 20 else 0
                values["boll_upper"] = round(sma20 + 2 * std, 4)
                values["boll_mid"] = round(sma20, 4)
                values["boll_lower"] = round(sma20 - 2 * std, 4)

        # VOL
        if "VOL" in wanted and n >= 5:
            vol_ma5 = sum(volumes[-5:]) / 5
            vol_latest = volumes[-1] if volumes else 0
            volume_price["volume_ratio"] = round(vol_latest / vol_ma5, 2) if vol_ma5 else None
            values["vol_ma5"] = round(vol_ma5, 0)

        # Support/Resistance
        if n >= 10:
            recent_high = max(highs[-20:]) if n >= 20 else max(highs)
            recent_low = min(lows[-20:]) if n >= 20 else min(lows)
            support_resistance = {
                "resistance": round(recent_high, 4),
                "support": round(recent_low, 4),
            }

        # Strategy
        score = 50
        stance = "neutral"
        if values.get("rsi_14") is not None:
            rsi = values["rsi_14"]
            if rsi < 30:
                score += 15
            elif rsi > 70:
                score -= 15
        if trend.get("primary", {}).get("direction") == "up":
            score += 10
        elif trend.get("primary", {}).get("direction") == "down":
            score -= 10
        if values.get("macd") is not None:
            if values["macd"] > 0:
                score += 5
            else:
                score -= 5
        score = max(0, min(100, score))
        stance = "bullish" if score >= 60 else "bearish" if score <= 40 else "neutral"

        strategy = {
            "score": score,
            "stance": stance,
            "profile": indicator_profile,
        }

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "values": values,
            "trend": trend,
            "momentum": momentum,
            "volume_price": volume_price,
            "patterns": {},
            "support_resistance": support_resistance,
            "strategy": strategy,
            "signal_timeline": [],
            "as_of": retrieved_at,
            "source": "computed",
            "retrieved_at": retrieved_at,
            "warnings": [],
        }

    # ------------------------------------------------------------------
    # Technical computation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(data: List[float], period: int) -> Optional[float]:
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def _rsi(data: List[float], period: int = 14) -> Optional[float]:
        if len(data) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(1, min(len(data), period + 1)):
            delta = data[i] - data[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        for i in range(period + 1, len(data)):
            delta = data[i] - data[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(delta, 0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-delta, 0)) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        true_ranges = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)
        if len(true_ranges) < period:
            return None
        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_market(symbol: str, fallback: str = "US") -> str:
        raw = (symbol or "").strip().upper()
        if raw.endswith(".HK"):
            return "HK"
        if raw.endswith(".SH") or raw.endswith(".SZ") or raw.endswith(".BJ"):
            return "CN"
        return fallback.upper() if fallback else "US"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            return f if f == f else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pick_metric(frame: Any, candidates: List[str], column: Any) -> Optional[float]:
        for name in candidates:
            try:
                if name not in frame.index:
                    continue
                return BuiltinMetricsTool._safe_float(frame.at[name, column])
            except Exception:
                continue
        return None

    @staticmethod
    def _format_date(value: Any) -> str:
        if hasattr(value, "strftime"):
            try:
                return value.strftime("%Y-%m-%d")
            except Exception:
                pass
        text = str(value or "").strip()
        return text[:10] if len(text) >= 10 else text

    def _empty_result(
        self, action: str, symbol: str, market: str, warnings: List[str],
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

    def _error_result(
        self, message: str, action: str, symbol: str, market: str,
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
