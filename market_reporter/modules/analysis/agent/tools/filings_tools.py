from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from market_reporter.modules.analysis.agent.schemas import FilingsResult


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
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return FilingsResult(
            symbol_or_cik=symbol_or_cik,
            form_type=(form_type or "ALL").upper().strip(),
            filings=[],
            as_of=retrieved_at,
            source="disabled",
            retrieved_at=retrieved_at,
            warnings=["longbridge_not_supported_sec_filings"],
        )
