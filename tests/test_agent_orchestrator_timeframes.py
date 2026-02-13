from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.agent.orchestrator import AgentOrchestrator
from market_reporter.modules.agent.schemas import (
    AgentRunRequest,
    FilingsResult,
    FundamentalsResult,
    IndicatorsResult,
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


class AgentOrchestratorTimeframesTest(unittest.TestCase):
    def test_stock_mode_collects_default_1d_and_5m(self):
        orchestrator = AgentOrchestrator(
            config=AppConfig(),
            registry=ProviderRegistry(),
            news_service=_DummyNewsService(),
            fund_flow_service=_DummyFundFlowService(),
        )

        interval_calls: list[str] = []
        seen_price_df: dict = {}

        async def fake_price(**kwargs):
            interval = str(kwargs.get("interval") or "1d")
            interval_calls.append(interval)
            base_time = datetime(2026, 2, 10)
            bars = [
                PriceBar(
                    ts=(base_time + timedelta(minutes=i)).isoformat(timespec="seconds"),
                    open=100 + i * 0.1,
                    high=101 + i * 0.1,
                    low=99 + i * 0.1,
                    close=100 + i * 0.12,
                    volume=1000 + i,
                )
                for i in range(80)
            ]
            return PriceHistoryResult(
                symbol="AAPL",
                market="US",
                interval=interval,
                adjusted=True,
                bars=bars,
                as_of=bars[-1].ts,
                source="yfinance",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=[],
            )

        async def fake_fundamentals(**kwargs):
            del kwargs
            return FundamentalsResult(
                symbol="AAPL",
                market="US",
                metrics={"market_cap": 1000.0, "net_income": 50.0, "trailing_pe": 20.0},
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
                source="sec",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=["no_filings_found"],
            )

        def fake_compute(price_df, indicators, symbol, indicator_profile):
            del indicators, symbol, indicator_profile
            if isinstance(price_df, dict):
                seen_price_df.update(price_df)
            return IndicatorsResult(
                symbol="AAPL",
                values={"close": 110.0},
                trend={"primary": {"ma": {"state": "bullish"}}},
                momentum={"primary": {}},
                volume_price={"primary": {}},
                patterns={"primary": {}},
                support_resistance={"primary": {"supports": [], "resistances": []}},
                strategy={"score": 70, "stance": "bullish", "position_size": 70},
                signal_timeline=[
                    {
                        "ts": "2026-02-12T00:00:00",
                        "timeframe": "5m",
                        "signal": "macd_cross",
                        "direction": "bullish",
                        "strength": "high",
                    }
                ],
                timeframes={},
                as_of="2026-02-12T00:00:00",
                source="pandas-ta/computed",
                retrieved_at="2026-02-13T00:00:00+00:00",
                warnings=[],
            )

        async def fake_runtime(**kwargs):
            del kwargs
            return (
                RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.8,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown="m",
                ),
                [],
            )

        orchestrator.market_tools.get_price_history = fake_price  # type: ignore[method-assign]
        orchestrator.fundamentals_tools.get_fundamentals = fake_fundamentals  # type: ignore[method-assign]
        orchestrator.news_tools.search_news = fake_news  # type: ignore[method-assign]
        orchestrator.filings_tools.get_filings = fake_filings  # type: ignore[method-assign]
        orchestrator.compute_tools.compute_indicators = fake_compute  # type: ignore[method-assign]
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
        self.assertIn("1d", interval_calls)
        self.assertIn("5m", interval_calls)
        self.assertIn("1d", seen_price_df)
        self.assertIn("5m", seen_price_df)

        tool_results = result.analysis_input.get("tool_results", {})
        self.assertIn("get_price_history_timeframes", tool_results)
        self.assertIn("compute_indicators", tool_results)


if __name__ == "__main__":
    unittest.main()
