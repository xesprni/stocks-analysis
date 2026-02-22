from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.analysis.agent.schemas import FundamentalsResult
from market_reporter.modules.analysis.agent.tools.market_tools import (
    infer_market_from_symbol,
)
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_longbridge_symbol,
)

logger = logging.getLogger(__name__)


class FundamentalsTools:
    def __init__(self, lb_config: Optional[LongbridgeConfig] = None) -> None:
        self._lb_config = lb_config
        self._use_longbridge = bool(
            lb_config
            and lb_config.enabled
            and lb_config.app_key
            and lb_config.app_secret
            and lb_config.access_token
        )

    async def get_fundamentals_info(
        self,
        symbol: str,
        market: Optional[str] = None,
    ) -> FundamentalsResult:
        if self._use_longbridge:
            try:
                return await asyncio.to_thread(
                    self._get_fundamentals_longbridge,
                    symbol,
                    market,
                )
            except Exception:
                fallback = await asyncio.to_thread(
                    self._get_fundamentals_sync,
                    symbol,
                    market,
                )
                fallback.warnings.append("longbridge_failed_fallback_yfinance")
                return fallback
        return await asyncio.to_thread(
            self._get_fundamentals_sync,
            symbol,
            market,
        )

    async def get_fundamentals(
        self,
        symbol: str,
        market: Optional[str] = None,
    ) -> FundamentalsResult:
        return await self.get_fundamentals_info(symbol=symbol, market=market)

    # ------------------------------------------------------------------
    # Longbridge implementation
    # ------------------------------------------------------------------

    def _get_fundamentals_longbridge(
        self,
        symbol: str,
        market: Optional[str],
    ) -> FundamentalsResult:
        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        if not self._use_longbridge:
            return self._empty_result(
                symbol=normalized_symbol,
                market=resolved_market,
                warnings=["longbridge_not_configured"],
            )

        try:
            from longbridge.openapi import CalcIndex, Config, QuoteContext
        except Exception:
            return self._empty_result(
                symbol=normalized_symbol,
                market=resolved_market,
                warnings=["longbridge_sdk_unavailable"],
            )

        lb_symbol = to_longbridge_symbol(normalized_symbol, resolved_market)

        assert self._lb_config is not None
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        metrics: Dict[str, Optional[float]] = {}
        warnings: list[str] = []

        # static_info provides EPS, BPS, total_shares, etc.
        try:
            static_list = ctx.static_info([lb_symbol])
            if static_list:
                si = static_list[0]
                metrics["eps_ttm"] = self._safe_float(getattr(si, "eps_ttm", None))
                metrics["bps"] = self._safe_float(getattr(si, "bps", None))
                metrics["total_shares"] = self._safe_float(
                    getattr(si, "total_shares", None)
                )
                metrics["circulating_shares"] = self._safe_float(
                    getattr(si, "circulating_shares", None)
                )
                metrics["dividend_yield"] = self._safe_float(
                    getattr(si, "dividend_yield", None)
                )
        except Exception:
            warnings.append("longbridge_static_info_failed")

        # calc_indexes provides PE, PB, market cap, turnover, etc.
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
                metrics["trailing_pe"] = self._safe_float(
                    getattr(ci, "pe_ttm_ratio", None)
                )
                metrics["pb_ratio"] = self._safe_float(getattr(ci, "pb_ratio", None))
                metrics["market_cap"] = self._safe_float(
                    getattr(ci, "total_market_value", None)
                )
                metrics["dividend_ratio_ttm"] = self._safe_float(
                    getattr(ci, "dividend_ratio_ttm", None)
                )
                metrics["turnover_rate"] = self._safe_float(
                    getattr(ci, "turnover_rate", None)
                )
                metrics["volume_ratio"] = self._safe_float(
                    getattr(ci, "volume_ratio", None)
                )
        except Exception:
            warnings.append("longbridge_calc_indexes_failed")

        if not any(v is not None for v in metrics.values()):
            warnings.append("empty_fundamentals")

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return FundamentalsResult(
            symbol=normalized_symbol,
            market=resolved_market,
            metrics=metrics,
            as_of=retrieved_at,
            source="longbridge",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # yfinance fallback implementation
    # ------------------------------------------------------------------

    def _get_fundamentals_sync(
        self,
        symbol: str,
        market: Optional[str],
    ) -> FundamentalsResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: list[str] = []

        metrics: Dict[str, Optional[float]] = {}
        try:
            ticker = yf.Ticker(normalized_symbol)
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
                    cashflow,
                    [
                        "Operating Cash Flow",
                        "Total Cash From Operating Activities",
                    ],
                    latest_col,
                )
                metrics["free_cash_flow"] = self._pick_metric(
                    cashflow,
                    ["Free Cash Flow"],
                    latest_col,
                )

            balance = getattr(ticker, "balance_sheet", None)
            if hasattr(balance, "columns") and len(getattr(balance, "columns", [])):
                latest_col = balance.columns[0]
                metrics["total_assets"] = self._pick_metric(
                    balance,
                    ["Total Assets"],
                    latest_col,
                )
                metrics["total_liabilities"] = self._pick_metric(
                    balance,
                    [
                        "Total Liabilities Net Minority Interest",
                        "Total Liab",
                        "Total Liabilities",
                    ],
                    latest_col,
                )
                metrics["shareholder_equity"] = self._pick_metric(
                    balance,
                    ["Stockholders Equity", "Total Stockholder Equity"],
                    latest_col,
                )
        except Exception as exc:
            warnings.append(f"yfinance_fundamentals_failed:{exc}")

        if not any(value is not None for value in metrics.values()):
            warnings.append("empty_fundamentals")

        return FundamentalsResult(
            symbol=normalized_symbol,
            market=resolved_market,
            metrics=metrics,
            as_of=retrieved_at,
            source="yfinance",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            return f if f == f else None  # filter NaN
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pick_metric(frame: Any, candidates: list[str], column: Any) -> Optional[float]:
        for name in candidates:
            try:
                if name not in frame.index:
                    continue
                return FundamentalsTools._safe_float(frame.at[name, column])
            except Exception:
                continue
        return None

    def _empty_result(
        self,
        symbol: str,
        market: Optional[str],
        warnings: list[str],
    ) -> FundamentalsResult:
        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return FundamentalsResult(
            symbol=normalized_symbol,
            market=resolved_market,
            metrics={},
            as_of=retrieved_at,
            source="longbridge",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )
