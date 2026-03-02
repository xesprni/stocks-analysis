from __future__ import annotations

import asyncio
import unittest
from typing import Any, Awaitable, Callable, Dict, cast

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.analysis.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    MacroResult,
    NewsSearchResult,
    RuntimeDraft,
    ToolCallTrace,
)


class _DummyNewsService:
    async def collect(self, limit: int):
        del limit
        return [], []


class _DummyFundFlowService:
    async def collect(self, periods: int):
        del periods
        return {}, []


class AgentOrchestratorSkillToolTest(unittest.TestCase):
    def test_skill_tool_is_lazy_loaded_and_not_stored_as_evidence_input(self):
        orchestrator = AgentOrchestrator(
            config=AppConfig(),
            registry=ProviderRegistry(),
            news_service=_DummyNewsService(),
            fund_flow_service=_DummyFundFlowService(),
        )

        async def fake_news(**kwargs):
            del kwargs
            return NewsSearchResult(
                query="market",
                items=[],
                as_of="2026-03-02",
                source="rss",
                retrieved_at="2026-03-02T00:00:00+00:00",
                warnings=[],
            )

        async def fake_runtime(**kwargs):
            executor = kwargs.get("tool_executor")
            traces = []
            if callable(executor):
                typed_executor = cast(
                    Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
                    executor,
                )
                skill_result = await typed_executor("skill", {"name": "git-release"})
                traces.append(
                    ToolCallTrace(
                        tool="skill",
                        arguments={"name": "git-release"},
                        result_preview=skill_result,
                    )
                )
                news_result = await typed_executor("search_news", {"query": "market"})
                traces.append(
                    ToolCallTrace(
                        tool="search_news",
                        arguments={"query": "market"},
                        result_preview=news_result,
                    )
                )
            return (
                RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.6,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown="m",
                ),
                traces,
            )

        orchestrator.news_tools.search_news = fake_news  # type: ignore[method-assign]
        orchestrator._run_runtime = fake_runtime  # type: ignore[method-assign]

        provider_cfg = AnalysisProviderConfig(
            provider_id="mock",
            type="mock",
            base_url="",
            models=["m"],
            timeout=5,
            enabled=True,
            auth_mode="none",
        )

        async def scenario():
            return await orchestrator.run(
                request=AgentRunRequest(mode="market", market="US"),
                provider_cfg=provider_cfg,
                model="m",
                api_key=None,
                access_token=None,
            )

        result = asyncio.run(scenario())
        tool_results = result.analysis_input.get("tool_results", {})
        self.assertIn("search_news", tool_results)
        self.assertNotIn("skill", tool_results)

    def test_skill_only_runtime_triggers_minimum_evidence_hydration(self):
        orchestrator = AgentOrchestrator(
            config=AppConfig(),
            registry=ProviderRegistry(),
            news_service=_DummyNewsService(),
            fund_flow_service=_DummyFundFlowService(),
        )

        async def fake_news(**kwargs):
            del kwargs
            return NewsSearchResult(
                query="market",
                items=[],
                as_of="2026-03-02",
                source="rss",
                retrieved_at="2026-03-02T00:00:00+00:00",
                warnings=[],
            )

        async def fake_macro(**kwargs):
            del kwargs
            return MacroResult(
                points=[],
                as_of="2026-03-02",
                source="eastmoney/fund_flow",
                retrieved_at="2026-03-02T00:00:00+00:00",
                warnings=[],
            )

        async def fake_runtime(**kwargs):
            executor = kwargs.get("tool_executor")
            traces = []
            if callable(executor):
                typed_executor = cast(
                    Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
                    executor,
                )
                skill_result = await typed_executor("skill", {"name": "market-brief"})
                traces.append(
                    ToolCallTrace(
                        tool="skill",
                        arguments={"name": "market-brief"},
                        result_preview=skill_result,
                    )
                )
            return (
                RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.6,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown="m",
                ),
                traces,
            )

        orchestrator.news_tools.search_news = fake_news  # type: ignore[method-assign]
        orchestrator.macro_tools.get_macro_data = fake_macro  # type: ignore[method-assign]
        orchestrator._run_runtime = fake_runtime  # type: ignore[method-assign]

        provider_cfg = AnalysisProviderConfig(
            provider_id="mock",
            type="mock",
            base_url="",
            models=["m"],
            timeout=5,
            enabled=True,
            auth_mode="none",
        )

        async def scenario():
            return await orchestrator.run(
                request=AgentRunRequest(
                    mode="market",
                    market="US",
                    question="请使用 market-brief skill 总结今日市场",
                ),
                provider_cfg=provider_cfg,
                model="m",
                api_key=None,
                access_token=None,
            )

        result = asyncio.run(scenario())
        codes = {issue.code for issue in result.guardrail_issues}
        self.assertNotIn("evidence_missing", codes)
        tool_results = result.analysis_input.get("tool_results", {})
        self.assertTrue(
            "search_news" in tool_results or "get_macro_data" in tool_results
        )


if __name__ == "__main__":
    unittest.main()
