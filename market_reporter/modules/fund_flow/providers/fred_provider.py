from __future__ import annotations

import csv
import io
from typing import Dict, List

from market_reporter.config import AppConfig, FRED_CSV_URL, FRED_SERIES
from market_reporter.core.types import FlowPoint
from market_reporter.infra.http.client import HttpClient


class FredFundFlowProvider:
    provider_id = "fred"

    def __init__(self, config: AppConfig, client: HttpClient) -> None:
        self.config = config
        self.client = client

    async def collect(self, periods: int) -> Dict[str, List[FlowPoint]]:
        output: Dict[str, List[FlowPoint]] = {}
        for series in FRED_SERIES:
            csv_text = await self.client.get_text(FRED_CSV_URL, params={"id": series.series_id})
            reader = csv.DictReader(io.StringIO(csv_text))
            points: List[FlowPoint] = []
            for row in reader:
                date = (row.get("DATE") or "").strip()
                value = self._parse_float((row.get(series.series_id) or "").strip())
                if not date or value is None:
                    continue
                points.append(
                    FlowPoint(
                        market=series.market,
                        series_key=series.key,
                        series_name=series.display_name,
                        date=date,
                        value=value,
                        unit=series.unit,
                    )
                )
            output[series.key] = points[-periods:]
        return output

    @staticmethod
    def _parse_float(raw: str):
        cleaned = raw.replace(",", "").strip()
        if cleaned in {"", ".", "-", "--", "null"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
