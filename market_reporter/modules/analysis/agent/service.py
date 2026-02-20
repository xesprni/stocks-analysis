from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import (
    AnalysisInput,
    AnalysisOutput,
    FlowPoint,
    KLineBar,
    NewsItem,
)
from market_reporter.modules.analysis.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    AgentRunResult,
)
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.news.service import NewsService


class AgentService:
    def __init__(
        self,
        config: AppConfig,
        registry: ProviderRegistry,
        news_service: NewsService,
        fund_flow_service: FundFlowService,
    ) -> None:
        self.config = config
        self.registry = registry
        self.orchestrator = AgentOrchestrator(
            config=config,
            registry=registry,
            news_service=news_service,
            fund_flow_service=fund_flow_service,
        )

    async def run(
        self,
        request: AgentRunRequest,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        api_key: Optional[str],
        access_token: Optional[str],
    ) -> AgentRunResult:
        return await self.orchestrator.run(
            request=request,
            provider_cfg=provider_cfg,
            model=model,
            api_key=api_key,
            access_token=access_token,
        )

    def to_analysis_payload(
        self,
        request: AgentRunRequest,
        run_result: AgentRunResult,
    ) -> Tuple[AnalysisInput, AnalysisOutput]:
        tool_results = run_result.analysis_input.get("tool_results", {})
        kline_rows = self._to_kline(tool_results.get("get_price_history"), request)
        news_rows = self._to_news(tool_results.get("search_news"))
        flow_rows = self._to_flow(tool_results.get("get_macro_data"))

        payload = AnalysisInput(
            symbol=request.symbol or "MARKET",
            market=request.market or "GLOBAL",
            quote=None,
            kline=kline_rows,
            curve=[],
            news=news_rows,
            fund_flow=flow_rows,
            watch_meta={
                "mode": request.mode,
                "question": request.question,
            },
        )

        output = AnalysisOutput(
            summary=run_result.runtime_draft.summary,
            sentiment=run_result.runtime_draft.sentiment,
            key_levels=run_result.runtime_draft.key_levels,
            risks=run_result.runtime_draft.risks,
            action_items=run_result.runtime_draft.action_items,
            confidence=run_result.final_report.confidence,
            markdown=run_result.final_report.markdown,
            raw={
                "technical_analysis": tool_results.get("compute_indicators", {}),
                "strategy": (
                    tool_results.get("compute_indicators", {}).get("strategy", {})
                    if isinstance(tool_results.get("compute_indicators"), dict)
                    else {}
                ),
                "signal_timeline": (
                    tool_results.get("compute_indicators", {}).get(
                        "signal_timeline", []
                    )
                    if isinstance(tool_results.get("compute_indicators"), dict)
                    else []
                ),
                "tool_calls": [
                    item.model_dump(mode="json") for item in run_result.tool_calls
                ],
                "evidence_map": [
                    item.model_dump(mode="json") for item in run_result.evidence_map
                ],
                "guardrail_issues": [
                    item.model_dump(mode="json") for item in run_result.guardrail_issues
                ],
                "tool_results": tool_results,
                "agent_runtime": run_result.runtime_draft.raw,
            },
        )
        return payload, output

    @staticmethod
    def _to_kline(price_payload: Any, request: AgentRunRequest) -> list[KLineBar]:
        if not isinstance(price_payload, dict):
            return []
        bars = price_payload.get("bars")
        if not isinstance(bars, list):
            return []
        rows: list[KLineBar] = []
        for row in bars:
            if not isinstance(row, dict):
                continue
            try:
                rows.append(
                    KLineBar(
                        symbol=request.symbol or "",
                        market=request.market or "",
                        interval=str(price_payload.get("interval") or "1d"),
                        ts=str(row.get("ts") or ""),
                        open=float(row.get("open") or 0.0),
                        high=float(row.get("high") or 0.0),
                        low=float(row.get("low") or 0.0),
                        close=float(row.get("close") or 0.0),
                        volume=float(row.get("volume"))
                        if row.get("volume") is not None
                        else None,
                        source=str(price_payload.get("source") or ""),
                    )
                )
            except Exception:
                continue
        return rows

    @staticmethod
    def _to_news(news_payload: Any) -> list[NewsItem]:
        if not isinstance(news_payload, dict):
            return []
        items = news_payload.get("items")
        if not isinstance(items, list):
            return []
        rows: list[NewsItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                NewsItem(
                    source_id="",
                    category="news",
                    source=str(item.get("media") or ""),
                    title=str(item.get("title") or ""),
                    link=str(item.get("link") or ""),
                    published=str(item.get("published_at") or ""),
                    content=str(item.get("summary") or ""),
                )
            )
        return rows

    @staticmethod
    def _to_flow(macro_payload: Any) -> Dict[str, list[FlowPoint]]:
        if not isinstance(macro_payload, dict):
            return {}
        points = macro_payload.get("points")
        if not isinstance(points, list):
            return {}
        grouped: Dict[str, list[FlowPoint]] = {}
        for row in points:
            if not isinstance(row, dict):
                continue
            key = str(row.get("series_key") or "macro")
            grouped.setdefault(key, []).append(
                FlowPoint(
                    market=str(row.get("market") or "GLOBAL"),
                    series_key=key,
                    series_name=str(row.get("series_name") or key),
                    date=str(row.get("date") or ""),
                    value=float(row.get("value") or 0.0),
                    unit=str(row.get("unit") or ""),
                )
            )
        return grouped
