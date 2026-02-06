from __future__ import annotations

import asyncio
import csv
import io
from typing import Dict, Iterable, List, Tuple

from market_reporter.config import AppConfig, EASTMONEY_FLOW_URL, FRED_CSV_URL, FRED_SERIES, FredSeries
from market_reporter.models import FlowPoint

from .http_client import HttpClient


class FundFlowCollector:
    def __init__(self, config: AppConfig, client: HttpClient) -> None:
        self.config = config
        self.client = client

    async def collect(self, periods: int = 12) -> Tuple[Dict[str, List[FlowPoint]], List[str]]:
        flow_series: Dict[str, List[FlowPoint]] = {}
        errors: List[str] = []

        try:
            cn_series = await self._collect_cn_hk_flow(periods=periods)
            flow_series.update(cn_series)
        except Exception as exc:
            errors.append(f"A/H fund flow collection failed: {exc}")

        tasks = [self._collect_fred_series(item=fred, periods=periods) for fred in FRED_SERIES]
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        for fred, settled_item in zip(FRED_SERIES, settled):
            if isinstance(settled_item, Exception):
                errors.append(f"US flow collection failed [{fred.series_id}]: {settled_item}")
                continue
            flow_series[fred.key] = settled_item

        return flow_series, errors

    async def _collect_cn_hk_flow(self, periods: int) -> Dict[str, List[FlowPoint]]:
        payload = await self.client.get_json(
            EASTMONEY_FLOW_URL,
            params={
                "fields1": "f1,f3",
                "fields2": "f51,f52",
                "klt": "101",
                "lmt": str(max(periods, 60)),
            },
        )
        data = payload.get("data", {}) if isinstance(payload, dict) else {}

        northbound = self._parse_eastmoney_series(data.get("s2n", []))
        southbound = self._parse_eastmoney_series(data.get("n2s", []))
        if not northbound:
            northbound = self._merge_eastmoney_components(
                data.get("hk2sh", []),
                data.get("hk2sz", []),
            )

        return {
            "a_share_northbound_net_inflow": [
                FlowPoint(
                    market="A_SHARE",
                    series_key="a_share_northbound_net_inflow",
                    series_name="A股北向净流入（陆股通）",
                    date=date,
                    value=value,
                    unit="亿元人民币",
                )
                for date, value in northbound[-periods:]
            ],
            "hk_share_southbound_net_inflow": [
                FlowPoint(
                    market="HK_SHARE",
                    series_key="hk_share_southbound_net_inflow",
                    series_name="港股南向净流入（港股通）",
                    date=date,
                    value=value,
                    unit="亿元人民币",
                )
                for date, value in southbound[-periods:]
            ],
        }

    async def _collect_fred_series(self, item: FredSeries, periods: int) -> List[FlowPoint]:
        csv_text = await self.client.get_text(FRED_CSV_URL, params={"id": item.series_id})
        reader = csv.DictReader(io.StringIO(csv_text))

        points: List[FlowPoint] = []
        for row in reader:
            date = (row.get("DATE") or "").strip()
            value = self._parse_float((row.get(item.series_id) or "").strip())
            if not date or value is None:
                continue
            points.append(
                FlowPoint(
                    market=item.market,
                    series_key=item.key,
                    series_name=item.display_name,
                    date=date,
                    value=value,
                    unit=item.unit,
                )
            )

        return points[-periods:]

    @staticmethod
    def _parse_eastmoney_series(raw_points: Iterable[str]) -> List[Tuple[str, float]]:
        parsed: List[Tuple[str, float]] = []
        for row in raw_points:
            if not isinstance(row, str):
                continue
            parts = [part.strip() for part in row.split(",")]
            if len(parts) < 2:
                continue
            date = parts[0]
            value = FundFlowCollector._parse_float(parts[1])
            if not date or value is None:
                continue
            parsed.append((date, value))
        return parsed

    @staticmethod
    def _merge_eastmoney_components(series_a: Iterable[str], series_b: Iterable[str]) -> List[Tuple[str, float]]:
        by_date: Dict[str, float] = {}
        for series in (series_a, series_b):
            for date, value in FundFlowCollector._parse_eastmoney_series(series):
                by_date[date] = by_date.get(date, 0.0) + value
        return sorted(by_date.items(), key=lambda item: item[0])

    @staticmethod
    def _parse_float(raw: str):
        cleaned = raw.replace(",", "").strip()
        if cleaned in {"", ".", "-", "--", "null"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
