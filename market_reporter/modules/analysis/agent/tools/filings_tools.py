from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Optional

from market_reporter.modules.agent.schemas import FilingItem, FilingsResult
from market_reporter.modules.agent.tools.market_tools import infer_market_from_symbol
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, to_yfinance_symbol


class FilingsTools:
    SUPPORTED_FORMS = {"10-K", "10-Q", "8-K"}

    async def get_filings(
        self,
        symbol_or_cik: str,
        form_type: str,
        from_date: str,
        to_date: str,
        market: Optional[str] = None,
    ) -> FilingsResult:
        return await asyncio.to_thread(
            self._get_filings_sync,
            symbol_or_cik,
            form_type,
            from_date,
            to_date,
            market,
        )

    def _get_filings_sync(
        self,
        symbol_or_cik: str,
        form_type: str,
        from_date: str,
        to_date: str,
        market: Optional[str],
    ) -> FilingsResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol_or_cik, fallback=market or "US")
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if resolved_market != "US":
            return FilingsResult(
                symbol_or_cik=symbol_or_cik,
                form_type=form_type,
                filings=[],
                as_of=retrieved_at,
                source="yfinance",
                retrieved_at=retrieved_at,
                warnings=["coverage_not_supported_non_us"],
            )

        normalized_symbol = normalize_symbol(symbol_or_cik, "US")
        yf_symbol = to_yfinance_symbol(normalized_symbol, "US")
        ticker = yf.Ticker(yf_symbol)

        from_dt = self._parse_date(from_date)
        to_dt = self._parse_date(to_date)
        wanted_form = (form_type or "ALL").upper().strip()

        raw_filings = ticker.sec_filings
        filings = self._normalize_filings(raw_filings)

        selected: List[FilingItem] = []
        for row in filings:
            row_form = (str(row.get("type") or "") or "").upper()
            row_date = str(row.get("date") or row.get("filingDate") or "")
            row_dt = self._parse_date(row_date)
            if wanted_form != "ALL":
                if wanted_form in self.SUPPORTED_FORMS and row_form != wanted_form:
                    continue
            if row_dt is not None and from_dt is not None and row_dt < from_dt:
                continue
            if row_dt is not None and to_dt is not None and row_dt > to_dt:
                continue
            selected.append(
                FilingItem(
                    form_type=row_form or wanted_form,
                    filed_at=row_date,
                    title=str(row.get("title") or row_form or ""),
                    link=str(
                        row.get("edgarUrl")
                        or row.get("link")
                        or row.get("url")
                        or ""
                    ),
                    content=str(row.get("text") or ""),
                )
            )
            if len(selected) >= 30:
                break

        warnings: List[str] = []
        if wanted_form != "ALL" and wanted_form not in self.SUPPORTED_FORMS:
            warnings.append("unsupported_form_type_requested")
        if not selected:
            warnings.append("no_filings_found")
        as_of = selected[0].filed_at if selected else retrieved_at
        return FilingsResult(
            symbol_or_cik=normalized_symbol,
            form_type=wanted_form,
            filings=selected,
            as_of=as_of,
            source="yfinance",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )

    @staticmethod
    def _normalize_filings(raw: Any) -> list[dict]:
        try:
            if raw is None:
                return []
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
            if hasattr(raw, "to_dict"):
                records = raw.to_dict(orient="records")
                if isinstance(records, list):
                    return [item for item in records if isinstance(item, dict)]
        except Exception:
            return []
        return []

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt)
            except Exception:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
