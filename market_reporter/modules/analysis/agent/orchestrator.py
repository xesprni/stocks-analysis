from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.analysis.agent.guardrails import AgentGuardrails
from market_reporter.modules.analysis.agent.report_formatter import AgentReportFormatter
from market_reporter.modules.analysis.agent.runtime.factory import AgentRuntimeFactory
from market_reporter.modules.analysis.agent.schemas import (
    AgentEvidence,
    AgentRunRequest,
    AgentRunResult,
    RuntimeDraft,
    ToolCallTrace,
)
from market_reporter.modules.analysis.agent.skills import (
    AgentSkillRegistry,
    MarketOverviewSkill,
    StockAnalysisSkill,
)
from market_reporter.modules.analysis.agent.tools import (
    ComputeTools,
    FinancialReportsTools,
    FundamentalsTools,
    MacroTools,
    MarketTools,
    NewsTools,
    WebSearchTools,
)
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.news.service import NewsService


class AgentOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        registry: ProviderRegistry,
        news_service: NewsService,
        fund_flow_service: FundFlowService,
    ) -> None:
        self.config = config
        self.registry = registry
        lb_config = config.longbridge
        self.market_tools = MarketTools(lb_config=lb_config)
        self.fundamentals_tools = FundamentalsTools(lb_config=lb_config)
        self.financial_reports_tools = FinancialReportsTools()
        self.news_tools = NewsTools(news_service=news_service, lb_config=lb_config)
        self.web_search_tools = WebSearchTools()
        self.macro_tools = MacroTools(fund_flow_service=fund_flow_service)
        self.compute_tools = ComputeTools(fundamentals_tools=self.fundamentals_tools)
        self.guardrails = AgentGuardrails()
        self.formatter = AgentReportFormatter()
        self.skill_registry = AgentSkillRegistry(
            skills=[
                StockAnalysisSkill(
                    market_tools=self.market_tools,
                    fundamentals_tools=self.fundamentals_tools,
                    financial_reports_tools=self.financial_reports_tools,
                    news_tools=self.news_tools,
                    web_search_tools=self.web_search_tools,
                    compute_tools=self.compute_tools,
                ),
                MarketOverviewSkill(
                    config=self.config,
                    news_tools=self.news_tools,
                    macro_tools=self.macro_tools,
                    web_search_tools=self.web_search_tools,
                ),
            ]
        )

    async def run(
        self,
        request: AgentRunRequest,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        api_key: Optional[str],
        access_token: Optional[str],
    ) -> AgentRunResult:
        resolved_skill = self.skill_registry.resolve(
            skill_id=request.skill_id,
            mode=request.mode,
        )
        mode = resolved_skill.mode
        question = self._resolve_question(request=request, mode=mode)
        ranges = self._resolve_ranges(request)
        prepared = await resolved_skill.prepare(
            request=request,
            ranges=ranges,
            trace_builder=self._trace,
        )
        tool_results = dict(prepared.tool_results)
        traces = list(prepared.traces)

        runtime_context = {
            "question": question,
            "mode": mode,
            "market": request.market,
            "tool_results": tool_results,
        }

        tool_specs = prepared.tool_specs

        async def executor(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            result = await self._execute_tool(
                tool=tool,
                arguments=arguments,
                request=request,
                ranges=ranges,
                fallback_symbol=prepared.fallback_symbol,
                fallback_market=prepared.fallback_market,
                resolved_mode=mode,
            )
            return result

        runtime_draft, runtime_traces = await self._run_runtime(
            provider_cfg=provider_cfg,
            model=model,
            question=question,
            mode=mode,
            context=runtime_context,
            tool_specs=tool_specs,
            tool_executor=executor,
            api_key=api_key,
            access_token=access_token,
        )
        traces.extend(runtime_traces)

        # Merge runtime-called tool outputs into the canonical result map.
        for call in runtime_traces:
            if call.tool and call.result_preview and call.tool not in tool_results:
                tool_results[call.tool] = call.result_preview

        evidence = self._build_evidence(tool_results)
        normalized_conclusions = self.formatter._build_conclusions(
            runtime_draft=runtime_draft,
            evidence_map=evidence,
        )
        issues = self.guardrails.validate(
            tool_results=tool_results,
            conclusions=normalized_conclusions,
            evidence_map=evidence,
            consistency_tolerance=self.config.agent.consistency_tolerance,
        )
        adjusted_confidence = self.guardrails.apply_confidence_penalty(
            base_confidence=runtime_draft.confidence,
            issues=issues,
        )
        runtime_draft = runtime_draft.model_copy(
            update={
                "confidence": adjusted_confidence,
                "conclusions": normalized_conclusions,
            }
        )

        final_report = self.formatter.format_report(
            mode=mode,
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
                "mode": mode,
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

    async def _run_runtime(
        self,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        question: str,
        mode: str,
        context: Dict[str, Any],
        tool_specs: List[Dict[str, Any]],
        tool_executor,
        api_key: Optional[str],
        access_token: Optional[str],
    ) -> Tuple[RuntimeDraft, List[ToolCallTrace]]:
        try:
            runtime = AgentRuntimeFactory.create_runtime(
                provider_cfg=provider_cfg,
                registry=self.registry,
                api_key=api_key,
                access_token=access_token,
            )
            return await runtime.run(
                model=model,
                question=question,
                mode=mode,
                context=context,
                tool_specs=tool_specs,
                tool_executor=tool_executor,
                max_steps=self.config.agent.max_steps,
                max_tool_calls=self.config.agent.max_tool_calls,
            )
        except NotImplementedError:
            raise
        except Exception as exc:
            return (
                RuntimeDraft(
                    summary=f"运行时失败，已回退到本地结构化输出: {exc}",
                    sentiment="neutral",
                    key_levels=[],
                    risks=["运行时不可用"],
                    action_items=["检查 provider 配置与鉴权状态"],
                    confidence=0.4,
                    conclusions=["本次报告基于工具结果生成，模型总结回退。"],
                    scenario_assumptions={
                        "base": "维持当前趋势",
                        "bull": "数据改善并扩张估值",
                        "bear": "数据恶化并压缩估值",
                    },
                    markdown=json.dumps(context, ensure_ascii=False)[:1500],
                    raw={"runtime_error": str(exc)},
                ),
                [],
            )

    async def _execute_tool(
        self,
        tool: str,
        arguments: Dict[str, Any],
        request: AgentRunRequest,
        ranges: Dict[str, str],
        fallback_symbol: str,
        fallback_market: str,
        resolved_mode: str,
    ) -> Dict[str, Any]:
        name = (tool or "").strip()
        if name == "get_price_history":
            result = await self.market_tools.get_price_history(
                symbol=str(arguments.get("symbol") or fallback_symbol),
                market=str(arguments.get("market") or fallback_market),
                start=str(arguments.get("start") or ranges["price_from"]),
                end=str(arguments.get("end") or ranges["price_to"]),
                interval=str(arguments.get("interval") or "1d"),
                adjusted=bool(arguments.get("adjusted", True)),
            )
            return result.model_dump(mode="json")
        if name in {"get_fundamentals_info", "get_fundamentals"}:
            result = await self.fundamentals_tools.get_fundamentals_info(
                symbol=str(arguments.get("symbol") or fallback_symbol),
                market=str(arguments.get("market") or fallback_market),
            )
            return result.model_dump(mode="json")
        if name == "get_financial_reports":
            result = await self.financial_reports_tools.get_financial_reports(
                symbol=str(arguments.get("symbol") or fallback_symbol),
                market=str(arguments.get("market") or fallback_market),
                limit=int(arguments.get("limit") or 6),
            )
            return result.model_dump(mode="json")
        if name == "search_news":
            resolved_symbol = str(arguments.get("symbol") or fallback_symbol)
            resolved_market = str(arguments.get("market") or fallback_market)
            result = await self.news_tools.search_news(
                query=str(
                    arguments.get("query") or request.question or fallback_symbol
                ),
                from_date=str(arguments.get("from") or ranges["news_from"]),
                to_date=str(arguments.get("to") or ranges["news_to"]),
                limit=int(arguments.get("limit") or 50),
                symbol=resolved_symbol,
                market=resolved_market,
            )
            return result.model_dump(mode="json")
        if name == "search_web":
            result = await self.web_search_tools.search_web(
                query=str(
                    arguments.get("query") or request.question or fallback_symbol
                ),
                limit=int(arguments.get("limit") or 10),
                from_date=str(arguments.get("from") or ranges["news_from"]),
                to_date=str(arguments.get("to") or ranges["news_to"]),
            )
            return result.model_dump(mode="json")
        if name == "compute_indicators":
            payload = arguments.get("price_df")
            if not isinstance(payload, (list, dict)):
                payload = []
            result = self.compute_tools.compute_indicators(
                price_df=payload,
                indicators=arguments.get("indicators")
                if isinstance(arguments.get("indicators"), list)
                else None,
                symbol=str(arguments.get("symbol") or fallback_symbol),
                indicator_profile=str(
                    arguments.get("indicator_profile")
                    or request.indicator_profile
                    or "balanced"
                ),
            )
            return result.model_dump(mode="json")
        if name == "peer_compare":
            peer_list = arguments.get("peer_list")
            result = await self.compute_tools.peer_compare(
                symbol=str(arguments.get("symbol") or fallback_symbol),
                peer_list=peer_list if isinstance(peer_list, list) else [],
                metrics=arguments.get("metrics")
                if isinstance(arguments.get("metrics"), list)
                else None,
                market=str(arguments.get("market") or fallback_market),
            )
            return result.model_dump(mode="json")
        if name == "get_macro_data":
            requested_market = arguments.get("market")
            if requested_market is None and resolved_mode == "market":
                requested_market = request.market
            result = await self.macro_tools.get_macro_data(
                periods=int(
                    arguments.get("periods") or min(self.config.flow_periods, 20)
                ),
                market=str(requested_market).strip().upper()
                if requested_market
                else None,
            )
            return result.model_dump(mode="json")
        raise ValueError(f"Unsupported tool: {name}")

    def _build_evidence(
        self, tool_results: Dict[str, Dict[str, Any]]
    ) -> List[AgentEvidence]:
        evidence: List[AgentEvidence] = []
        cursor = 1
        for tool_name, payload in tool_results.items():
            if not isinstance(payload, dict):
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

        indicator_payload = tool_results.get("compute_indicators")
        if isinstance(indicator_payload, dict):
            strategy = indicator_payload.get("strategy")
            if isinstance(strategy, dict):
                score = strategy.get("score")
                stance = strategy.get("stance")
                evidence.append(
                    AgentEvidence(
                        evidence_id=f"E{cursor}",
                        statement=f"策略评分 {score}，方向 {stance}",
                        source=str(indicator_payload.get("source") or "computed"),
                        as_of=str(indicator_payload.get("as_of") or ""),
                        pointer="compute_indicators.strategy",
                    )
                )
                cursor += 1

            timeline = indicator_payload.get("signal_timeline")
            if isinstance(timeline, list):
                for index, item in enumerate(timeline[:5]):
                    if not isinstance(item, dict):
                        continue
                    signal = str(item.get("signal") or "signal")
                    direction = str(item.get("direction") or "neutral")
                    timeframe = str(item.get("timeframe") or "")
                    statement = f"关键信号 {signal} ({timeframe}) -> {direction}"
                    evidence.append(
                        AgentEvidence(
                            evidence_id=f"E{cursor}",
                            statement=statement,
                            source=str(indicator_payload.get("source") or "computed"),
                            as_of=str(
                                item.get("ts") or indicator_payload.get("as_of") or ""
                            ),
                            pointer=f"compute_indicators.signal_timeline[{index}]",
                        )
                    )
                    cursor += 1
        return evidence

    @staticmethod
    def _statement_for_tool(tool_name: str, payload: Dict[str, Any]) -> str:
        if tool_name == "get_price_history":
            bars = payload.get("bars")
            count = len(bars) if isinstance(bars, list) else 0
            return f"行情历史样本 {count} 条"
        if tool_name == "get_price_history_timeframes":
            timeframes = payload.get("timeframes")
            if not isinstance(timeframes, dict):
                return "多周期行情样本"
            parts = []
            for key, item in timeframes.items():
                bars = item.get("bars") if isinstance(item, dict) else None
                count = len(bars) if isinstance(bars, list) else 0
                parts.append(f"{key}:{count}")
            joined = ", ".join(parts) if parts else "N/A"
            return f"多周期行情样本 {joined}"
        if tool_name in {"get_fundamentals_info", "get_fundamentals"}:
            return "财务核心字段（营收/利润/现金流/资产负债）"
        if tool_name == "get_financial_reports":
            reports = payload.get("reports")
            count = len(reports) if isinstance(reports, list) else 0
            return f"财报样本 {count} 条"
        if tool_name == "search_news":
            items = payload.get("items")
            count = len(items) if isinstance(items, list) else 0
            return f"新闻样本 {count} 条"
        if tool_name == "search_web":
            items = payload.get("items")
            count = len(items) if isinstance(items, list) else 0
            return f"联网检索样本 {count} 条"
        if tool_name == "compute_indicators":
            strategy = payload.get("strategy")
            if isinstance(strategy, dict):
                return (
                    "技术指标计算结果 "
                    f"(score={strategy.get('score')}, stance={strategy.get('stance')})"
                )
            return "技术指标计算结果"
        if tool_name == "peer_compare":
            rows = payload.get("rows")
            count = len(rows) if isinstance(rows, list) else 0
            return f"同行对比样本 {count} 条"
        if tool_name == "get_macro_data":
            points = payload.get("points")
            count = len(points) if isinstance(points, list) else 0
            return f"宏观序列样本 {count} 条"
        return tool_name

    @staticmethod
    def _trace(
        tool: str, arguments: Dict[str, Any], result: Dict[str, Any]
    ) -> ToolCallTrace:
        preview = dict(result)
        for key in ("bars", "items", "points", "rows", "reports"):
            value = preview.get(key)
            if isinstance(value, list) and len(value) > 3:
                preview[key] = value[:3]
                preview[f"{key}_count"] = len(value)
        return ToolCallTrace(tool=tool, arguments=arguments, result_preview=preview)

    def _resolve_question(self, request: AgentRunRequest, mode: str) -> str:
        if request.question.strip():
            return request.question.strip()
        if mode == "stock":
            return f"请分析 {request.symbol or ''} 的投资价值与风险。"
        if request.market:
            return f"请总结 {request.market} 市场当前的主要风险收益特征。"
        return "请总结当前市场的主要风险收益特征。"

    def _resolve_ranges(self, request: AgentRunRequest) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        news_to = request.news_to or now.strftime("%Y-%m-%d")
        filing_to = request.filing_to or now.strftime("%Y-%m-%d")
        price_to = now.strftime("%Y-%m-%d")

        news_from = request.news_from or (
            now - timedelta(days=self.config.agent.default_news_window_days)
        ).strftime("%Y-%m-%d")
        filing_from = request.filing_from or (
            now - timedelta(days=self.config.agent.default_filing_window_days)
        ).strftime("%Y-%m-%d")
        price_from = (
            now - timedelta(days=self.config.agent.default_price_window_days)
        ).strftime("%Y-%m-%d")

        return {
            "news_from": news_from,
            "news_to": news_to,
            "filing_from": filing_from,
            "filing_to": filing_to,
            "price_from": price_from,
            "price_to": price_to,
        }
