from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from market_reporter.modules.agent.schemas import FundamentalsResult
from market_reporter.modules.agent.tools.market_tools import infer_market_from_symbol
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, to_yfinance_symbol


class FundamentalsTools:
    async def get_fundamentals(
        self,
        symbol: str,
        market: Optional[str] = None,
    ) -> FundamentalsResult:
        return await asyncio.to_thread(self._get_fundamentals_sync, symbol, market)

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
            "total_liabilities": self._pick_number(info, ["totalLiab", "totalLiabilities"]),
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
                cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"]
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
