from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from market_reporter.modules.analysis.agent.schemas import (
    FinancialReportItem,
    FinancialReportsResult,
)
from market_reporter.modules.analysis.agent.tools.market_tools import (
    infer_market_from_symbol,
)
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol


class FinancialReportsTools:
    async def get_financial_reports(
        self,
        symbol: str,
        market: Optional[str] = None,
        limit: int = 6,
    ) -> FinancialReportsResult:
        return await asyncio.to_thread(
            self._get_financial_reports_sync,
            symbol,
            market,
            limit,
        )

    def _get_financial_reports_sync(
        self,
        symbol: str,
        market: Optional[str],
        limit: int,
    ) -> FinancialReportsResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        warnings: List[str] = []
        reports: List[FinancialReportItem] = []
        latest_metrics: Dict[str, Optional[float]] = {}

        try:
            ticker = yf.Ticker(normalized_symbol)
            reports = self._collect_reports_from_ticker(ticker=ticker, limit=limit)
        except Exception as exc:
            warnings.append(f"financial_reports_failed:{exc}")

        if not reports:
            warnings.append("empty_financial_reports")
        else:
            latest_metrics = dict(reports[0].metrics)

        as_of = reports[0].report_date if reports else retrieved_at
        return FinancialReportsResult(
            symbol=normalized_symbol,
            market=resolved_market,
            reports=reports,
            latest_metrics=latest_metrics,
            as_of=as_of,
            source="yfinance",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )

    def _collect_reports_from_ticker(
        self,
        ticker: Any,
        limit: int,
    ) -> List[FinancialReportItem]:
        datasets = [
            ("income", "annual", getattr(ticker, "financials", None)),
            ("balance", "annual", getattr(ticker, "balance_sheet", None)),
            ("cashflow", "annual", getattr(ticker, "cashflow", None)),
            ("income", "quarterly", getattr(ticker, "quarterly_financials", None)),
            (
                "balance",
                "quarterly",
                getattr(ticker, "quarterly_balance_sheet", None),
            ),
            ("cashflow", "quarterly", getattr(ticker, "quarterly_cashflow", None)),
        ]

        rows: List[FinancialReportItem] = []
        for statement_type, period_type, frame in datasets:
            rows.extend(
                self._rows_from_dataframe(
                    statement_type=statement_type,
                    period_type=period_type,
                    frame=frame,
                    limit=limit,
                )
            )

        rows.sort(key=lambda item: item.report_date, reverse=True)
        dedup: List[FinancialReportItem] = []
        seen: set[str] = set()
        for row in rows:
            key = f"{row.report_date}:{row.statement_type}:{row.period_type}"
            if key in seen:
                continue
            seen.add(key)
            dedup.append(row)
            if len(dedup) >= max(limit, 1):
                break
        return dedup

    def _rows_from_dataframe(
        self,
        statement_type: str,
        period_type: str,
        frame: Any,
        limit: int,
    ) -> List[FinancialReportItem]:
        if frame is None:
            return []
        if not hasattr(frame, "columns") or not hasattr(frame, "index"):
            return []

        columns = list(getattr(frame, "columns", []))
        if not columns:
            return []

        rows: List[FinancialReportItem] = []
        for column in columns[: max(limit, 1)]:
            metrics = {
                "revenue": self._pick_metric(
                    frame,
                    ["Total Revenue", "Operating Revenue", "Revenue"],
                    column,
                ),
                "net_income": self._pick_metric(
                    frame,
                    ["Net Income", "Net Income Common Stockholders"],
                    column,
                ),
                "operating_cash_flow": self._pick_metric(
                    frame,
                    [
                        "Operating Cash Flow",
                        "Total Cash From Operating Activities",
                    ],
                    column,
                ),
                "free_cash_flow": self._pick_metric(
                    frame,
                    ["Free Cash Flow"],
                    column,
                ),
                "total_assets": self._pick_metric(
                    frame,
                    ["Total Assets"],
                    column,
                ),
                "total_liabilities": self._pick_metric(
                    frame,
                    [
                        "Total Liabilities Net Minority Interest",
                        "Total Liab",
                        "Total Liabilities",
                    ],
                    column,
                ),
                "shareholder_equity": self._pick_metric(
                    frame,
                    ["Stockholders Equity", "Total Stockholder Equity"],
                    column,
                ),
                "gross_profit": self._pick_metric(
                    frame,
                    ["Gross Profit"],
                    column,
                ),
                "operating_income": self._pick_metric(
                    frame,
                    ["Operating Income"],
                    column,
                ),
            }
            if not any(value is not None for value in metrics.values()):
                continue

            report_date = self._format_date(column)
            rows.append(
                FinancialReportItem(
                    report_date=report_date,
                    statement_type=statement_type,
                    period_type=period_type,
                    metrics=metrics,
                )
            )
        return rows

    @staticmethod
    def _pick_metric(frame: Any, candidates: List[str], column: Any) -> Optional[float]:
        for name in candidates:
            try:
                if name not in frame.index:
                    continue
                value = frame.at[name, column]
                return FinancialReportsTools._safe_float(value)
            except Exception:
                continue
        return None

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            return f if f == f else None
        except Exception:
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
