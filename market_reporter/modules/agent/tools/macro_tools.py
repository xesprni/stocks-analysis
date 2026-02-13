from __future__ import annotations

from datetime import datetime, timezone

from market_reporter.modules.agent.schemas import MacroResult, MacroSeriesItem
from market_reporter.modules.fund_flow.service import FundFlowService


class MacroTools:
    def __init__(self, fund_flow_service: FundFlowService) -> None:
        self.fund_flow_service = fund_flow_service

    async def get_macro_data(self, periods: int = 12) -> MacroResult:
        flow_series, warnings = await self.fund_flow_service.collect(periods=periods)
        points: list[MacroSeriesItem] = []
        for rows in flow_series.values():
            for row in rows:
                points.append(
                    MacroSeriesItem(
                        series_key=row.series_key,
                        series_name=row.series_name,
                        date=row.date,
                        value=row.value,
                        unit=row.unit,
                        market=row.market,
                    )
                )
        points.sort(key=lambda item: item.date, reverse=True)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = points[0].date if points else retrieved_at
        extra_warnings = list(warnings)
        if not points:
            extra_warnings.append("empty_macro_series")
        return MacroResult(
            points=points,
            as_of=as_of,
            source="fred/eastmoney",
            retrieved_at=retrieved_at,
            warnings=extra_warnings,
        )
