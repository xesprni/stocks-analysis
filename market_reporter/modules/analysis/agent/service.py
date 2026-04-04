from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.types import (
    AnalysisInput,
    AnalysisOutput,
    KLineBar,
    NewsItem,
)
from market_reporter.modules.analysis.agent.core.tool_registry import ToolRegistry
from market_reporter.modules.analysis.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    AgentRunResult,
)
from market_reporter.modules.analysis.agent.tools.builtin_metrics_tool import (
    BuiltinMetricsTool,
    get_definition as get_metrics_definition,
)
from market_reporter.modules.analysis.agent.tools.builtin_news_tool import (
    BuiltinNewsTool,
    get_definition as get_news_definition,
)


def _build_tool_registry(config: AppConfig) -> ToolRegistry:
    """Construct and populate the ToolRegistry with all builtin tools."""
    registry = ToolRegistry()

    metrics_tool = BuiltinMetricsTool(lb_config=config.longbridge)
    registry.register(
        definition=get_metrics_definition(),
        executor=metrics_tool.execute,
    )

    news_tool = BuiltinNewsTool(
        news_service=None,
        lb_config=config.longbridge,
    )
    registry.register(
        definition=get_news_definition(),
        executor=news_tool.execute,
    )

    return registry


class AgentService:
    def __init__(
        self,
        config: AppConfig,
    ) -> None:
        self.config = config
        self.tool_registry = _build_tool_registry(config)
        self.orchestrator = AgentOrchestrator(
            config=config,
            tool_registry=self.tool_registry,
        )

    async def run(
        self,
        request: AgentRunRequest,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        api_key: Optional[str],
    ) -> AgentRunResult:
        return await self.orchestrator.run(
            request=request,
            provider_cfg=provider_cfg,
            model=model,
            api_key=api_key,
        )

    def to_analysis_payload(
        self,
        request: AgentRunRequest,
        run_result: AgentRunResult,
    ) -> Tuple[AnalysisInput, AnalysisOutput]:
        tool_results = run_result.analysis_input.get("tool_results", {})

        # Extract price history from get_metrics action results
        metrics_payload = tool_results.get("get_metrics", {})
        kline_rows = self._to_kline(metrics_payload, request)
        news_rows = self._to_news(tool_results.get("search_news"))

        payload = AnalysisInput(
            symbol=request.symbol or "MARKET",
            market=request.market or "GLOBAL",
            quote=None,
            kline=kline_rows,
            curve=[],
            news=news_rows,
            fund_flow={},
            watch_meta={
                "mode": request.mode,
                "question": request.question,
            },
        )

        # Extract strategy/technical from get_metrics technical_indicators
        strategy = {}
        signal_timeline = []
        if isinstance(metrics_payload, dict):
            strategy = metrics_payload.get("strategy", {})
            signal_timeline = metrics_payload.get("signal_timeline", [])

        output = AnalysisOutput(
            summary=run_result.runtime_draft.summary,
            sentiment=run_result.runtime_draft.sentiment,
            key_levels=run_result.runtime_draft.key_levels,
            risks=run_result.runtime_draft.risks,
            action_items=run_result.runtime_draft.action_items,
            confidence=run_result.final_report.confidence,
            markdown=run_result.final_report.markdown,
            raw={
                "technical_analysis": metrics_payload,
                "strategy": strategy,
                "signal_timeline": signal_timeline,
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
    def _to_kline(metrics_payload: Any, request: AgentRunRequest) -> list[KLineBar]:
        if not isinstance(metrics_payload, dict):
            return []
        # Only process price_history action results
        action = metrics_payload.get("action", "")
        if action != "price_history":
            return []
        bars = metrics_payload.get("bars")
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
                        interval=str(metrics_payload.get("interval") or "1d"),
                        ts=str(row.get("ts") or ""),
                        open=float(row.get("open") or 0.0),
                        high=float(row.get("high") or 0.0),
                        low=float(row.get("low") or 0.0),
                        close=float(row.get("close") or 0.0),
                        volume=float(row.get("volume"))
                        if row.get("volume") is not None
                        else None,
                        source=str(metrics_payload.get("source") or ""),
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
