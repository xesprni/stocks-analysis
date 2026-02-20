import asyncio
import unittest

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.analysis.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.analysis.agent.schemas import (
    AgentRunRequest,
    FilingsResult,
    FundamentalsResult,
    NewsSearchResult,
    PriceBar,
    PriceHistoryResult,
    RuntimeDraft,
)


class _DummyNewsService:
    async def collect(self, limit: int):
        del limit
        return [], []


class _DummyFundFlowService:
    async def collect(self, periods: int):
        del periods
        return {}, []


class AgentOrchestratorStockModeTest(unittest.TestCase):
    def test_stock_mode_minimum_tool_chain(self):
        orchestrator = AgentOrchestrator(
            config=AppConfig(),
            registry=ProviderRegistry(),
            news_service=_DummyNewsService(),
            fund_flow_service=_DummyFundFlowService(),
        )

        async def fake_price(**kwargs):
            del kwargs
            return PriceHistoryResult(
                symbol="AAPL",
                market="US",
                interval="1d",
                adjusted=True,
                bars=[
                    PriceBar(
                        ts="2026-02-12T00:00:00",
                        open=100.0,
                        high=110.0,
                        low=95.0,
                        close=108.0,
                        volume=1000.0,
                    )
                ],
                as_of="2026-02-12T00:00:00",
                source="yfinance",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=[],
            )

        async def fake_fundamentals(**kwargs):
            del kwargs
            return FundamentalsResult(
                symbol="AAPL",
                market="US",
                metrics={
                    "market_cap": 1000.0,
                    "net_income": 50.0,
                    "trailing_pe": 20.0,
                    "revenue": 300.0,
                },
                as_of="2026-02-12",
                source="yfinance",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=[],
            )

        async def fake_news(**kwargs):
            del kwargs
            return NewsSearchResult(
                query="AAPL",
                items=[],
                as_of="2026-02-12",
                source="rss",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=[],
            )

        async def fake_filings(**kwargs):
            del kwargs
            return FilingsResult(
                symbol_or_cik="AAPL",
                form_type="10-K",
                filings=[],
                as_of="2026-02-12",
                source="yfinance",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=["no_filings_found"],
            )

        async def fake_runtime(**kwargs):
            del kwargs
            return (
                RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.8,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={
                        "base": "b",
                        "bull": "u",
                        "bear": "d",
                    },
                    markdown="m",
                ),
                [],
            )

        orchestrator.market_tools.get_price_history = fake_price  # type: ignore[method-assign]
        orchestrator.fundamentals_tools.get_fundamentals = fake_fundamentals  # type: ignore[method-assign]
        orchestrator.news_tools.search_news = fake_news  # type: ignore[method-assign]
        orchestrator.filings_tools.get_filings = fake_filings  # type: ignore[method-assign]
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
        request = AgentRunRequest(mode="stock", symbol="AAPL", market="US")

        async def scenario():
            return await orchestrator.run(
                request=request,
                provider_cfg=provider_cfg,
                model="m",
                api_key=None,
                access_token=None,
            )

        result = asyncio.run(scenario())
        tool_keys = set(result.analysis_input.get("tool_results", {}).keys())
        self.assertIn("get_price_history", tool_keys)
        self.assertIn("get_fundamentals", tool_keys)
        self.assertIn("search_news", tool_keys)
        self.assertIn("compute_indicators", tool_keys)
        self.assertIn("get_filings", tool_keys)
        self.assertIn("## 结论摘要（3–6条）", result.final_report.markdown)


if __name__ == "__main__":
    unittest.main()
