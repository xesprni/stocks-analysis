from __future__ import annotations

import asyncio
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
    to_yfinance_symbol,
)


class FundamentalsTools:
    def __init__(self, lb_config: Optional[LongbridgeConfig] = None) -> None:
        self._lb_config = lb_config

    @property
    def _use_longbridge(self) -> bool:
        return (
            self._lb_config is not None
            and self._lb_config.enabled
            and bool(self._lb_config.app_key)
            and bool(self._lb_config.access_token)
        )

    async def get_fundamentals(
        self,
        symbol: str,
        market: Optional[str] = None,
    ) -> FundamentalsResult:
        if self._use_longbridge:
            return await asyncio.to_thread(
                self._get_fundamentals_longbridge, symbol, market
            )
        return await asyncio.to_thread(self._get_fundamentals_sync, symbol, market)

    # ------------------------------------------------------------------
    # yfinance implementation (original)
    # ------------------------------------------------------------------

    def _get_fundamentals_sync(
        self,
        symbol: str,
        market: Optional[str],
    ) -> FundamentalsResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        yf_symbol = to_yfinance_symbol(normalized_symbol, resolved_market)
        ticker = yf.Ticker(yf_symbol)

        info = ticker.info or {}
        financials = ticker.financials
        cashflow = ticker.cashflow
        balance_sheet = ticker.balance_sheet

        metrics: Dict[str, Optional[float]] = {
            "revenue": self._pick_number(info, ["totalRevenue", "revenuePerShare"]),
            "net_income": self._pick_number(info, ["netIncomeToCommon", "netIncome"]),
            "operating_cash_flow": self._pick_number(info, ["operatingCashflow"]),
            "free_cash_flow": self._pick_number(info, ["freeCashflow"]),
            "total_assets": self._pick_number(info, ["totalAssets"]),
            "total_liabilities": self._pick_number(
                info, ["totalLiab", "totalLiabilities"]
            ),
            "shareholder_equity": self._pick_number(info, ["totalStockholderEquity"]),
            "market_cap": self._pick_number(info, ["marketCap"]),
            "trailing_pe": self._pick_number(info, ["trailingPE"]),
            "forward_pe": self._pick_number(info, ["forwardPE"]),
        }

        if metrics["revenue"] is None:
            metrics["revenue"] = self._frame_value(financials, ["Total Revenue"])
        if metrics["net_income"] is None:
            metrics["net_income"] = self._frame_value(financials, ["Net Income"])
        if metrics["operating_cash_flow"] is None:
            metrics["operating_cash_flow"] = self._frame_value(
                cashflow,
                ["Operating Cash Flow", "Total Cash From Operating Activities"],
            )
        if metrics["free_cash_flow"] is None:
            metrics["free_cash_flow"] = self._frame_value(cashflow, ["Free Cash Flow"])
        if metrics["total_assets"] is None:
            metrics["total_assets"] = self._frame_value(balance_sheet, ["Total Assets"])
        if metrics["total_liabilities"] is None:
            metrics["total_liabilities"] = self._frame_value(
                balance_sheet,
                ["Total Liabilities Net Minority Interest", "Total Liab"],
            )
        if metrics["shareholder_equity"] is None:
            metrics["shareholder_equity"] = self._frame_value(
                balance_sheet,
                ["Stockholders Equity", "Total Stockholder Equity"],
            )

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings = []
        if not any(v is not None for v in metrics.values()):
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
    # Longbridge implementation
    # ------------------------------------------------------------------

    def _get_fundamentals_longbridge(
        self,
        symbol: str,
        market: Optional[str],
    ) -> FundamentalsResult:
        from longbridge.openapi import CalcIndex, Config, QuoteContext

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
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
    def _pick_number(info: Dict[str, Any], keys: list[str]) -> Optional[float]:
        for key in keys:
            value = info.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None

    @staticmethod
    def _frame_value(frame: Any, row_names: list[str]) -> Optional[float]:
        if frame is None:
            return None
        try:
            if frame.empty:
                return None
            for row_name in row_names:
                if row_name in frame.index:
                    row = frame.loc[row_name]
                    if hasattr(row, "iloc"):
                        value = row.iloc[0]
                    else:
                        value = row
                    if value is None:
                        continue
                    return float(value)
        except Exception:
            return None
        return None
