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
from market_reporter.modules.analysis.agent.tools import (
    ComputeTools,
    FilingsTools,
    FundamentalsTools,
    MacroTools,
    MarketTools,
    NewsTools,
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
        self.filings_tools = FilingsTools()
        self.news_tools = NewsTools(news_service=news_service, lb_config=lb_config)
        self.macro_tools = MacroTools(fund_flow_service=fund_flow_service)
        self.compute_tools = ComputeTools(fundamentals_tools=self.fundamentals_tools)
        self.guardrails = AgentGuardrails()
        self.formatter = AgentReportFormatter()

    async def run(
        self,
        request: AgentRunRequest,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        api_key: Optional[str],
        access_token: Optional[str],
    ) -> AgentRunResult:
        tool_results: Dict[str, Dict[str, Any]] = {}
        traces: List[ToolCallTrace] = []

        mode = request.mode
        question = self._resolve_question(request)
        ranges = self._resolve_ranges(request)

        # Mandatory data checklist.
        if mode == "stock":
            if not request.symbol or not request.market:
                raise ValueError("Stock mode requires symbol and market")
            symbol = request.symbol.strip().upper()
            market = request.market.strip().upper()

            resolved_timeframes = self._resolve_timeframes(request.timeframes)
            price_timeframes: Dict[str, Dict[str, Any]] = {}
            price_warnings: List[str] = []
            for timeframe in resolved_timeframes:
                price_result = await self.market_tools.get_price_history(
                    symbol=symbol,
                    market=market,
                    start=ranges["price_from"],
                    end=ranges["price_to"],
                    interval=timeframe,
                    adjusted=True,
                )
                payload = price_result.model_dump(mode="json")
                price_timeframes[timeframe] = payload
                warnings = payload.get("warnings")
                if isinstance(warnings, list):
                    price_warnings.extend([str(item) for item in warnings])
                traces.append(
                    self._trace(
                        "get_price_history",
                        {
                            "symbol": symbol,
                            "start": ranges["price_from"],
                            "end": ranges["price_to"],
                            "interval": timeframe,
                            "adjusted": True,
                        },
                        payload,
                    )
                )

            primary_tf = "1d" if "1d" in price_timeframes else resolved_timeframes[0]
            primary_price = price_timeframes.get(primary_tf) or {}
            tool_results["get_price_history"] = primary_price
            tool_results["get_price_history_timeframes"] = {
                "timeframes": price_timeframes,
                "as_of": str(primary_price.get("as_of") or ""),
                "source": str(primary_price.get("source") or "yfinance"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "warnings": list(dict.fromkeys(price_warnings)),
            }

            fundamentals_result = await self.fundamentals_tools.get_fundamentals(
                symbol=symbol,
                market=market,
            )
            tool_results["get_fundamentals"] = fundamentals_result.model_dump(
                mode="json"
            )
            traces.append(
                self._trace(
                    "get_fundamentals",
                    {"symbol": symbol},
                    tool_results["get_fundamentals"],
                )
            )

            news_result = await self.news_tools.search_news(
                query=symbol,
                from_date=ranges["news_from"],
                to_date=ranges["news_to"],
                limit=50,
                symbol=symbol,
                market=market,
            )
            tool_results["search_news"] = news_result.model_dump(mode="json")
            traces.append(
                self._trace(
                    "search_news",
                    {
                        "query": symbol,
                        "from": ranges["news_from"],
                        "to": ranges["news_to"],
                    },
                    tool_results["search_news"],
                )
            )

            indicators = request.indicators or ["RSI", "MACD", "MA", "ATR", "VOL"]
            timeframe_bars = {
                timeframe: payload.get("bars", [])
                for timeframe, payload in price_timeframes.items()
                if isinstance(payload, dict)
            }
            indicator_result = self.compute_tools.compute_indicators(
                price_df=timeframe_bars,
                indicators=indicators,
                symbol=symbol,
                indicator_profile=request.indicator_profile,
            )
            tool_results["compute_indicators"] = indicator_result.model_dump(
                mode="json"
            )
            traces.append(
                self._trace(
                    "compute_indicators",
                    {
                        "indicators": indicators,
                        "timeframes": resolved_timeframes,
                        "indicator_profile": request.indicator_profile,
                    },
                    tool_results["compute_indicators"],
                )
            )

            if market == "US":
                filings_result = await self.filings_tools.get_filings(
                    symbol_or_cik=symbol,
                    form_type="10-K",
                    from_date=ranges["filing_from"],
                    to_date=ranges["filing_to"],
                    market=market,
                )
                tool_results["get_filings"] = filings_result.model_dump(mode="json")
                traces.append(
                    self._trace(
                        "get_filings",
                        {
                            "symbol_or_cik": symbol,
                            "form_type": "10-K",
                            "from": ranges["filing_from"],
                            "to": ranges["filing_to"],
                        },
                        tool_results["get_filings"],
                    )
                )

            if request.peer_list:
                peer_result = await self.compute_tools.peer_compare(
                    symbol=symbol,
                    peer_list=request.peer_list,
                    metrics=None,
                    market=market,
                )
                tool_results["peer_compare"] = peer_result.model_dump(mode="json")
                traces.append(
                    self._trace(
                        "peer_compare",
                        {
                            "symbol": symbol,
                            "peer_list": request.peer_list,
                        },
                        tool_results["peer_compare"],
                    )
                )

        else:
            target_market = (request.market or "").strip().upper()
            market_query = (
                f"{target_market} market" if target_market else "macro market"
            )
            news_result = await self.news_tools.search_news(
                query=market_query,
                from_date=ranges["news_from"],
                to_date=ranges["news_to"],
                limit=80,
                market=target_market,
            )
            tool_results["search_news"] = news_result.model_dump(mode="json")
            traces.append(
                self._trace(
                    "search_news",
                    {
                        "query": market_query,
                        "market": target_market,
                        "from": ranges["news_from"],
                        "to": ranges["news_to"],
                    },
                    tool_results["search_news"],
                )
            )

            macro_result = await self.macro_tools.get_macro_data(
                periods=min(self.config.flow_periods, 20),
                market=target_market or None,
            )
            tool_results["get_macro_data"] = macro_result.model_dump(mode="json")
            traces.append(
                self._trace(
                    "get_macro_data",
                    {
                        "periods": min(self.config.flow_periods, 20),
                        "market": target_market,
                    },
                    tool_results["get_macro_data"],
                )
            )

        runtime_context = {
            "question": question,
            "mode": mode,
            "market": request.market,
            "tool_results": tool_results,
        }

        tool_specs = self._tool_specs(mode=mode)

        async def executor(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            result = await self._execute_tool(
                tool=tool,
                arguments=arguments,
                request=request,
                ranges=ranges,
                fallback_symbol=request.symbol or "",
                fallback_market=request.market or "US",
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
        issues = self.guardrails.validate(
            tool_results=tool_results,
            conclusions=runtime_draft.conclusions,
            evidence_map=evidence,
            consistency_tolerance=self.config.agent.consistency_tolerance,
        )
        adjusted_confidence = self.guardrails.apply_confidence_penalty(
            base_confidence=runtime_draft.confidence,
            issues=issues,
        )
        runtime_draft = runtime_draft.model_copy(
            update={"confidence": adjusted_confidence}
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
        if name == "get_fundamentals":
            result = await self.fundamentals_tools.get_fundamentals(
                symbol=str(arguments.get("symbol") or fallback_symbol),
                market=str(arguments.get("market") or fallback_market),
            )
            return result.model_dump(mode="json")
        if name == "get_filings":
            result = await self.filings_tools.get_filings(
                symbol_or_cik=str(arguments.get("symbol_or_cik") or fallback_symbol),
                form_type=str(arguments.get("form_type") or "10-K"),
                from_date=str(arguments.get("from") or ranges["filing_from"]),
                to_date=str(arguments.get("to") or ranges["filing_to"]),
                market=str(arguments.get("market") or fallback_market),
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
            if requested_market is None and request.mode == "market":
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
        if tool_name == "get_fundamentals":
            return "财务核心字段（营收/利润/现金流/资产负债）"
        if tool_name == "search_news":
            items = payload.get("items")
            count = len(items) if isinstance(items, list) else 0
            return f"新闻样本 {count} 条"
        if tool_name == "get_filings":
            filings = payload.get("filings")
            count = len(filings) if isinstance(filings, list) else 0
            return f"公司文档样本 {count} 条"
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
        for key in ("bars", "items", "points", "rows", "filings"):
            value = preview.get(key)
            if isinstance(value, list) and len(value) > 3:
                preview[key] = value[:3]
                preview[f"{key}_count"] = len(value)
        return ToolCallTrace(tool=tool, arguments=arguments, result_preview=preview)

    def _resolve_question(self, request: AgentRunRequest) -> str:
        if request.question.strip():
            return request.question.strip()
        if request.mode == "stock":
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

    @staticmethod
    def _resolve_timeframes(raw_timeframes: List[str]) -> List[str]:
        allowed = {"1d", "5m", "1m"}
        cleaned = [
            str(item).strip().lower()
            for item in raw_timeframes
            if str(item).strip().lower() in allowed
        ]
        dedup = list(dict.fromkeys(cleaned))
        if not dedup:
            return ["1d", "5m"]
        if "1d" not in dedup:
            dedup.append("1d")
        if "5m" not in dedup:
            dedup.append("5m")
        return dedup

    @staticmethod
    def _tool_specs(mode: str) -> List[Dict[str, Any]]:
        base: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "get_price_history",
                    "description": "Get historical OHLCV data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "market": {"type": "string"},
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                            "interval": {"type": "string"},
                            "adjusted": {"type": "boolean"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_fundamentals",
                    "description": "Get fundamentals for one symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "market": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_filings",
                    "description": "Get US filings",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol_or_cik": {"type": "string"},
                            "market": {"type": "string"},
                            "form_type": {"type": "string"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_news",
                    "description": "Search and deduplicate news",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "symbol": {"type": "string"},
                            "market": {"type": "string"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compute_indicators",
                    "description": "Compute technical indicators",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "price_df": {"type": "object"},
                            "indicators": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "indicator_profile": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "peer_compare",
                    "description": "Compare peer metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "market": {"type": "string"},
                            "peer_list": {"type": "array", "items": {"type": "string"}},
                            "metrics": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_macro_data",
                    "description": "Get macro series from FRED/eastmoney",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "periods": {"type": "integer"},
                            "market": {"type": "string"},
                        },
                    },
                },
            },
        ]
        if mode == "market":
            return [
                item
                for item in base
                if item.get("function", {}).get("name")
                in {"search_news", "get_macro_data"}
            ]
        return base
