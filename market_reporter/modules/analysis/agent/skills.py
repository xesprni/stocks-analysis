from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

from market_reporter.config import AppConfig
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    ToolCallTrace,
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

TraceBuilder = Callable[[str, Dict[str, Any], Dict[str, Any]], ToolCallTrace]


@dataclass
class PreparedAgentSkill:
    mode: str
    skill_id: str
    tool_results: Dict[str, Dict[str, Any]]
    traces: List[ToolCallTrace]
    tool_specs: List[Dict[str, Any]]
    fallback_symbol: str
    fallback_market: str


class AgentSkill(Protocol):
    skill_id: str
    mode: str
    aliases: Sequence[str]

    async def prepare(
        self,
        request: AgentRunRequest,
        ranges: Dict[str, str],
        trace_builder: TraceBuilder,
    ) -> PreparedAgentSkill: ...


class StockAnalysisSkill:
    skill_id = "stock_analysis"
    mode = "stock"
    aliases = ("stock",)

    def __init__(
        self,
        market_tools: MarketTools,
        fundamentals_tools: FundamentalsTools,
        financial_reports_tools: FinancialReportsTools,
        news_tools: NewsTools,
        web_search_tools: WebSearchTools,
        compute_tools: ComputeTools,
    ) -> None:
        self.market_tools = market_tools
        self.fundamentals_tools = fundamentals_tools
        self.financial_reports_tools = financial_reports_tools
        self.news_tools = news_tools
        self.web_search_tools = web_search_tools
        self.compute_tools = compute_tools

    async def prepare(
        self,
        request: AgentRunRequest,
        ranges: Dict[str, str],
        trace_builder: TraceBuilder,
    ) -> PreparedAgentSkill:
        if not request.symbol or not request.market:
            raise ValueError("Stock mode requires symbol and market")
        symbol = request.symbol.strip().upper()
        market = request.market.strip().upper()

        tool_results: Dict[str, Dict[str, Any]] = {}
        traces: List[ToolCallTrace] = []

        resolved_timeframes = _resolve_timeframes(request.timeframes)
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
                trace_builder(
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
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warnings": list(dict.fromkeys(price_warnings)),
        }

        fundamentals_result = await self.fundamentals_tools.get_fundamentals_info(
            symbol=symbol,
            market=market,
        )
        tool_results["get_fundamentals_info"] = fundamentals_result.model_dump(
            mode="json"
        )
        traces.append(
            trace_builder(
                "get_fundamentals_info",
                {"symbol": symbol},
                tool_results["get_fundamentals_info"],
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
            trace_builder(
                "search_news",
                {
                    "query": symbol,
                    "from": ranges["news_from"],
                    "to": ranges["news_to"],
                },
                tool_results["search_news"],
            )
        )

        web_query = f"{symbol} {request.question}".strip()
        web_result = await self.web_search_tools.search_web(
            query=web_query,
            limit=12,
            from_date=ranges["news_from"],
            to_date=ranges["news_to"],
        )
        tool_results["search_web"] = web_result.model_dump(mode="json")
        traces.append(
            trace_builder(
                "search_web",
                {
                    "query": web_query,
                    "limit": 12,
                    "from": ranges["news_from"],
                    "to": ranges["news_to"],
                },
                tool_results["search_web"],
            )
        )

        financial_reports = await self.financial_reports_tools.get_financial_reports(
            symbol=symbol,
            market=market,
            limit=6,
        )
        tool_results["get_financial_reports"] = financial_reports.model_dump(
            mode="json"
        )
        traces.append(
            trace_builder(
                "get_financial_reports",
                {
                    "symbol": symbol,
                    "market": market,
                    "limit": 6,
                },
                tool_results["get_financial_reports"],
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
        tool_results["compute_indicators"] = indicator_result.model_dump(mode="json")
        traces.append(
            trace_builder(
                "compute_indicators",
                {
                    "indicators": indicators,
                    "timeframes": resolved_timeframes,
                    "indicator_profile": request.indicator_profile,
                },
                tool_results["compute_indicators"],
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
                trace_builder(
                    "peer_compare",
                    {
                        "symbol": symbol,
                        "peer_list": request.peer_list,
                    },
                    tool_results["peer_compare"],
                )
            )

        return PreparedAgentSkill(
            mode=self.mode,
            skill_id=self.skill_id,
            tool_results=tool_results,
            traces=traces,
            tool_specs=_stock_tool_specs(),
            fallback_symbol=symbol,
            fallback_market=market,
        )


class MarketOverviewSkill:
    skill_id = "market_overview"
    mode = "market"
    aliases = ("market",)

    def __init__(
        self,
        config: AppConfig,
        news_tools: NewsTools,
        macro_tools: MacroTools,
        web_search_tools: WebSearchTools,
    ):
        self.config = config
        self.news_tools = news_tools
        self.macro_tools = macro_tools
        self.web_search_tools = web_search_tools

    async def prepare(
        self,
        request: AgentRunRequest,
        ranges: Dict[str, str],
        trace_builder: TraceBuilder,
    ) -> PreparedAgentSkill:
        target_market = (request.market or "").strip().upper()
        market_query = f"{target_market} market" if target_market else "macro market"

        tool_results: Dict[str, Dict[str, Any]] = {}
        traces: List[ToolCallTrace] = []

        news_result = await self.news_tools.search_news(
            query=market_query,
            from_date=ranges["news_from"],
            to_date=ranges["news_to"],
            limit=80,
            market=target_market,
        )
        tool_results["search_news"] = news_result.model_dump(mode="json")
        traces.append(
            trace_builder(
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

        web_result = await self.web_search_tools.search_web(
            query=market_query,
            limit=12,
            from_date=ranges["news_from"],
            to_date=ranges["news_to"],
        )
        tool_results["search_web"] = web_result.model_dump(mode="json")
        traces.append(
            trace_builder(
                "search_web",
                {
                    "query": market_query,
                    "limit": 12,
                    "from": ranges["news_from"],
                    "to": ranges["news_to"],
                },
                tool_results["search_web"],
            )
        )

        periods = min(self.config.flow_periods, 20)
        macro_result = await self.macro_tools.get_macro_data(
            periods=periods,
            market=target_market or None,
        )
        tool_results["get_macro_data"] = macro_result.model_dump(mode="json")
        traces.append(
            trace_builder(
                "get_macro_data",
                {
                    "periods": periods,
                    "market": target_market,
                },
                tool_results["get_macro_data"],
            )
        )

        return PreparedAgentSkill(
            mode=self.mode,
            skill_id=self.skill_id,
            tool_results=tool_results,
            traces=traces,
            tool_specs=_market_tool_specs(),
            fallback_symbol="",
            fallback_market=target_market or "US",
        )


class AgentSkillRegistry:
    def __init__(self, skills: List[Any]) -> None:
        self._skills_by_alias: Dict[str, AgentSkill] = {}
        for skill in skills:
            self._register_alias(skill.skill_id, skill)
            self._register_alias(skill.mode, skill)
            for alias in skill.aliases:
                self._register_alias(alias, skill)

    def resolve(self, skill_id: Optional[str], mode: str) -> AgentSkill:
        requested = (skill_id or "").strip().lower()
        if requested:
            skill = self._skills_by_alias.get(requested)
            if skill is not None:
                return skill
            raise ValueError(f"Unknown agent skill: {skill_id}")

        fallback = (mode or "").strip().lower()
        skill = self._skills_by_alias.get(fallback)
        if skill is not None:
            return skill
        raise ValueError(f"Unsupported agent mode: {mode}")

    def _register_alias(self, raw_alias: str, skill: AgentSkill) -> None:
        alias = (raw_alias or "").strip().lower()
        if not alias:
            return
        existing = self._skills_by_alias.get(alias)
        if existing is not None and existing.skill_id != skill.skill_id:
            raise ValueError(f"Agent skill alias conflict: {alias}")
        self._skills_by_alias[alias] = skill


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


def _stock_tool_specs() -> List[Dict[str, Any]]:
    return [item for item in _base_tool_specs()]


def _market_tool_specs() -> List[Dict[str, Any]]:
    return [
        item
        for item in _base_tool_specs()
        if item.get("function", {}).get("name")
        in {"search_news", "search_web", "get_macro_data"}
    ]


def _base_tool_specs() -> List[Dict[str, Any]]:
    return [
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
                "name": "get_fundamentals_info",
                "description": "Get company fundamentals via Longbridge SDK",
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
                "name": "get_financial_reports",
                "description": "Get company financial statements",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "market": {"type": "string"},
                        "limit": {"type": "integer"},
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
                "name": "search_web",
                "description": "Search web results from internet sources",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                        "from": {"type": "string"},
                        "to": {"type": "string"},
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
