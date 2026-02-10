from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from market_reporter.config import AppConfig, EASTMONEY_FLOW_URL
from market_reporter.core.types import FlowPoint
from market_reporter.infra.http.client import HttpClient


class EastMoneyFundFlowProvider:
    provider_id = "eastmoney"

    def __init__(self, config: AppConfig, client: HttpClient) -> None:
        self.config = config
        self.client = client

    async def collect(self, periods: int) -> Dict[str, List[FlowPoint]]:
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
        northbound = self._parse_series(data.get("s2n", []))
        southbound = self._parse_series(data.get("n2s", []))
        if not northbound:
            # Compatibility fallback for payload variants that split northbound channels.
            northbound = self._merge(data.get("hk2sh", []), data.get("hk2sz", []))

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

    @staticmethod
    def _parse_series(raw_points: Iterable[str]) -> List[Tuple[str, float]]:
        parsed: List[Tuple[str, float]] = []
        for row in raw_points:
            if not isinstance(row, str):
                continue
            parts = [part.strip() for part in row.split(",")]
            if len(parts) < 2:
                continue
            value = EastMoneyFundFlowProvider._parse_float(parts[1])
            if value is None:
                continue
            parsed.append((parts[0], value))
        return parsed

    @staticmethod
    def _merge(series_a: Iterable[str], series_b: Iterable[str]) -> List[Tuple[str, float]]:
        merged: Dict[str, float] = {}
        for series in (series_a, series_b):
            for date, value in EastMoneyFundFlowProvider._parse_series(series):
                # Same date from multiple sub-series is accumulated.
                merged[date] = merged.get(date, 0.0) + value
        return sorted(merged.items(), key=lambda x: x[0])

    @staticmethod
    def _parse_float(raw: str):
        cleaned = raw.replace(",", "").strip()
        if cleaned in {"", ".", "-", "--", "null"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
