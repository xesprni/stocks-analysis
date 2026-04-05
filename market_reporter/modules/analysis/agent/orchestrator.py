from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.modules.analysis.agent.core.tool_registry import ToolRegistry
from market_reporter.modules.analysis.agent.guardrails import AgentGuardrails
from market_reporter.modules.analysis.agent.report_formatter import AgentReportFormatter
from market_reporter.modules.analysis.agent.runtime.openai_tool_runtime import (
    OpenAIToolRuntime,
)
from market_reporter.modules.analysis.agent.schemas import (
    AgentEvidence,
    AgentFinalReport,
    AgentRunRequest,
    AgentRunResult,
    GuardrailIssue,
    RuntimeDraft,
    ToolCallTrace,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Lightweight orchestrator that delegates tool execution to ToolRegistry."""

    def __init__(
        self,
        config: AppConfig,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.tool_registry = tool_registry
        self.guardrails = AgentGuardrails()
        self.formatter = AgentReportFormatter()

    async def run(
        self,
        request: AgentRunRequest,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        api_key: Optional[str],
    ) -> AgentRunResult:
        question = self._resolve_question(request)
        context = self._build_context(request)
        tool_specs = self.tool_registry.get_tool_specs()

        traces: List[ToolCallTrace] = []
        tool_results: Dict[str, Dict[str, Any]] = {}

        async def executor(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            result = await self._execute_tool(tool, arguments)
            tool_name = tool.strip().lower()
            tool_results[tool_name] = result
            return result

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key=api_key or "")
        runtime_draft, runtime_traces = await runtime.run(
            model=model,
            question=question,
            mode=context.get("mode", "stock"),
            context=context,
            tool_specs=tool_specs,
            tool_executor=executor,
            max_steps=self.config.agent.max_steps,
            max_tool_calls=self.config.agent.max_tool_calls,
        )
        traces.extend(runtime_traces)

        # Merge runtime traces into tool_results
        for call in runtime_traces:
            tool_name = (call.tool or "").strip().lower()
            if tool_name and call.result_preview and tool_name not in tool_results:
                tool_results[tool_name] = call.result_preview

        evidence = self._build_evidence(tool_results)
        conclusions = self.formatter._build_conclusions(
            runtime_draft=runtime_draft,
            evidence_map=evidence,
        )

        issues = self.guardrails.validate(
            tool_results=tool_results,
            conclusions=conclusions,
            evidence_map=evidence,
            consistency_tolerance=self.config.agent.consistency_tolerance,
        )
        adjusted_confidence = self.guardrails.apply_confidence_penalty(
            base_confidence=runtime_draft.confidence,
            issues=issues,
        )
        runtime_draft = runtime_draft.model_copy(
            update={"confidence": adjusted_confidence, "conclusions": conclusions},
        )

        final_report = self.formatter.format_report(
            mode=request.mode,
            question=question,
            runtime_draft=runtime_draft,
            tool_results=tool_results,
            evidence_map=evidence,
            guardrail_issues=issues,
            confidence=adjusted_confidence,
        )

        return AgentRunResult(
            analysis_input={
                "question": question,
                "symbol": request.symbol,
                "market": request.market,
                "tool_results": tool_results,
            },
            runtime_draft=runtime_draft,
            final_report=final_report,
            tool_calls=traces,
            guardrail_issues=issues,
            evidence_map=evidence,
        )

    async def _execute_tool(
        self, tool: str, arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = tool.strip()
        lowered = name.lower()
        if not self.tool_registry.has(lowered):
            return {"error": f"Unknown tool: {name}", "source": "orchestrator"}

        try:
            return await self.tool_registry.execute(lowered, arguments)
        except Exception as exc:
            logger.exception("Tool %s execution failed", name)
            return {"error": str(exc), "source": "tool_executor", "tool": name}

    def _resolve_question(self, request: AgentRunRequest) -> str:
        if request.question.strip():
            return request.question.strip()
        symbol = request.symbol or ""
        market = request.market or ""
        if symbol:
            return f"请分析 {symbol}（{market}市场）的投资价值与风险。"
        if market:
            return f"请总结 {market} 市场当前的主要风险收益特征。"
        return "请总结当前市场的主要风险收益特征。"

    @staticmethod
    def _build_context(request: AgentRunRequest) -> Dict[str, Any]:
        return {
            "question": request.question,
            "mode": request.mode,
            "symbol": (request.symbol or "").strip().upper(),
            "market": (request.market or "").strip().upper() or "US",
        }

    def _build_evidence(
        self, tool_results: Dict[str, Dict[str, Any]],
    ) -> List[AgentEvidence]:
        evidence: List[AgentEvidence] = []
        cursor = 1
        for tool_name, payload in tool_results.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("error"):
                continue
            source = str(payload.get("source") or "unknown")
            as_of = str(payload.get("as_of") or "")
            statement = self._statement_for_tool(tool_name, payload)
            evidence.append(
                AgentEvidence(
                    evidence_id=f"E{cursor}",
                    statement=statement,
                    source=source,
                    as_of=as_of,
                    pointer=tool_name,
                )
            )
            cursor += 1
        return evidence

    @staticmethod
    def _statement_for_tool(tool_name: str, payload: Dict[str, Any]) -> str:
        if tool_name == "get_metrics":
            action = payload.get("action", "")
            if action == "candlesticks":
                bars = payload.get("bars")
                count = len(bars) if isinstance(bars, list) else 0
                return f"行情历史样本 {count} 条"
            if action == "calc_indexes":
                return "计算指标（PE/PB/市值/换手率等）"
            if action == "static_info":
                return "公司基本信息"
            if action == "quote":
                price = payload.get("price")
                return f"实时报价 {price}"
            if action == "intraday":
                points = payload.get("points")
                count = len(points) if isinstance(points, list) else 0
                return f"分时数据 {count} 条"
            return f"指标数据 ({action})"

        if tool_name == "search_news":
            items = payload.get("items")
            count = len(items) if isinstance(items, list) else 0
            web_count = len(payload.get("web_results", []))
            return f"新闻样本 {count} 条, 网页结果 {web_count} 条"

        return tool_name
