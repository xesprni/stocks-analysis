import asyncio
import unittest

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.analysis.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    MacroResult,
    NewsSearchResult,
    RuntimeDraft,
    WebSearchResult,
)


class _DummyNewsService:
    async def collect(self, limit: int):
        del limit
        return [], []


class _DummyFundFlowService:
    async def collect(self, periods: int):
        del periods
        return {}, []


class AgentOrchestratorMarketModeTest(unittest.TestCase):
    def test_market_mode_respects_requested_market(self):
        orchestrator = AgentOrchestrator(
            config=AppConfig(),
            registry=ProviderRegistry(),
            news_service=_DummyNewsService(),
            fund_flow_service=_DummyFundFlowService(),
        )

        captured: dict = {}

        async def fake_news(**kwargs):
            captured["news"] = dict(kwargs)
            return NewsSearchResult(
                query=str(kwargs.get("query") or ""),
                items=[],
                as_of="2026-02-21",
                source="rss",
                retrieved_at="2026-02-21T00:00:00+00:00",
                warnings=[],
            )

        async def fake_macro(periods: int = 12, market=None):
            captured["macro"] = {"periods": periods, "market": market}
            return MacroResult(
                points=[],
                as_of="2026-02-21",
                source="mock",
                retrieved_at="2026-02-21T00:00:00+00:00",
                warnings=[],
            )

        async def fake_web_search(**kwargs):
            captured["web"] = dict(kwargs)
            return WebSearchResult(
                query=str(kwargs.get("query") or ""),
                items=[],
                as_of="2026-02-21",
                source="bing_rss",
                retrieved_at="2026-02-21T00:00:00+00:00",
                warnings=[],
            )

        async def fake_runtime(**kwargs):
            captured["runtime"] = {
                "question": kwargs.get("question"),
                "context": kwargs.get("context"),
            }
            return (
                RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.6,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown="m",
                ),
                [],
            )

        orchestrator.news_tools.search_news = fake_news  # type: ignore[method-assign]
        orchestrator.macro_tools.get_macro_data = fake_macro  # type: ignore[method-assign]
        orchestrator.web_search_tools.search_web = fake_web_search  # type: ignore[method-assign]
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
        request = AgentRunRequest(mode="market", market="HK")

        async def scenario():
            return await orchestrator.run(
                request=request,
                provider_cfg=provider_cfg,
                model="m",
                api_key=None,
                access_token=None,
            )

        result = asyncio.run(scenario())
        self.assertEqual(captured.get("news", {}).get("market"), "HK")
        self.assertEqual(captured.get("macro", {}).get("market"), "HK")
        self.assertIn("HK", str(captured.get("runtime", {}).get("question") or ""))
        self.assertEqual(result.analysis_input.get("market"), "HK")
        tool_results = result.analysis_input.get("tool_results", {})
        self.assertIn("search_news", tool_results)
        self.assertIn("search_web", tool_results)
        self.assertIn("get_macro_data", tool_results)


if __name__ == "__main__":
    unittest.main()
