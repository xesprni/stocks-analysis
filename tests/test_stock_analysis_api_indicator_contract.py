from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import (
    AnalysisConfig,
    AnalysisProviderConfig,
    AppConfig,
    DatabaseConfig,
)
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.analysis.agent.schemas import (
    AgentFinalReport,
    AgentRunResult,
    RuntimeDraft,
)
from market_reporter.modules.analysis.agent.service import AgentService


class _DummyNewsService:
    async def collect(self, limit: int):
        del limit
        return [], []


class _DummyFundFlowService:
    async def collect(self, periods: int):
        del periods
        return {}, []


class StockAnalysisIndicatorContractTest(unittest.TestCase):
    def test_output_raw_contains_technical_analysis_contract(self):
        original_run = AgentService.run

        async def fake_run(self, request, provider_cfg, model, api_key, access_token):
            del self, provider_cfg, model, api_key, access_token
            markdown = "# Agent 分析报告\n\n## 结论摘要（3–6条）\n\n- 结论一 [E1]\n"
            return AgentRunResult(
                analysis_input={
                    "tool_results": {
                        "get_price_history": {
                            "as_of": "2026-02-13T00:00:00",
                            "source": "yfinance",
                            "bars": [],
                            "interval": "1d",
                        },
                        "compute_indicators": {
                            "as_of": "2026-02-13T00:00:00",
                            "source": "pandas-ta/computed",
                            "values": {"close": 200.0, "rsi_14": 61.2},
                            "trend": {"primary": {"ma": {"state": "bullish"}}},
                            "momentum": {
                                "primary": {"rsi": {"value": 61.2, "status": "neutral"}}
                            },
                            "volume_price": {"primary": {"volume_ratio": 1.45}},
                            "patterns": {"primary": {"recent": []}},
                            "support_resistance": {
                                "primary": {
                                    "supports": [
                                        {"level": "S1", "price": 188.0, "touches": 3}
                                    ],
                                    "resistances": [
                                        {"level": "R1", "price": 212.0, "touches": 2}
                                    ],
                                }
                            },
                            "strategy": {
                                "score": 72.5,
                                "stance": "bullish",
                                "position_size": 72,
                                "entry_zone": {"low": 187.0, "high": 189.0},
                                "stop_loss": 181.0,
                                "take_profit": 212.0,
                            },
                            "signal_timeline": [
                                {
                                    "ts": "2026-02-13T00:00:00",
                                    "timeframe": "5m",
                                    "signal": "macd_cross",
                                    "direction": "bullish",
                                    "strength": "high",
                                }
                            ],
                            "timeframes": {
                                "1d": {"as_of": "2026-02-13T00:00:00"},
                                "5m": {"as_of": "2026-02-13T00:00:00"},
                            },
                        },
                    }
                },
                runtime_draft=RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    confidence=0.7,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown=markdown,
                    raw={},
                ),
                final_report=AgentFinalReport(
                    mode=request.mode,
                    question=request.question,
                    conclusions=["结论一 [E1]", "结论二 [E2]", "结论三 [E3]"],
                    market_technical="x",
                    fundamentals="x",
                    catalysts_risks="x",
                    valuation_scenarios="x",
                    data_sources=[],
                    guardrail_issues=[],
                    confidence=0.7,
                    markdown=markdown,
                    raw={},
                ),
                tool_calls=[],
                guardrail_issues=[],
                evidence_map=[],
            )

        AgentService.run = fake_run  # type: ignore[method-assign]

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                db_path = root / "market_reporter.db"
                output_root = root / "output"
                output_root.mkdir(parents=True, exist_ok=True)
                init_db(f"sqlite:///{db_path}")

                config = AppConfig(
                    output_root=output_root,
                    config_file=root / "config" / "settings.yaml",
                    database=DatabaseConfig(url=f"sqlite:///{db_path}"),
                    analysis=AnalysisConfig(
                        default_provider="mock",
                        default_model="market-default",
                        providers=[
                            AnalysisProviderConfig(
                                provider_id="mock",
                                type="mock",
                                base_url="",
                                models=["market-default"],
                                timeout=5,
                                enabled=True,
                                auth_mode="none",
                            )
                        ],
                    ),
                )

                service = AnalysisService(
                    config=config,
                    registry=ProviderRegistry(),
                    news_service=_DummyNewsService(),
                    fund_flow_service=_DummyFundFlowService(),
                )

                result = asyncio.run(
                    service.run_stock_analysis(
                        symbol="AAPL",
                        market="US",
                        question="技术面如何？",
                        peer_list=["MSFT", "GOOGL"],
                        timeframes=["1d", "5m"],
                        indicator_profile="balanced",
                    )
                )

                raw = result.output.raw
                self.assertIn("technical_analysis", raw)
                self.assertIn("strategy", raw)
                self.assertIn("signal_timeline", raw)
                self.assertEqual(
                    raw["technical_analysis"].get("source"), "pandas-ta/computed"
                )
                self.assertEqual(
                    raw["technical_analysis"].get("as_of"), "2026-02-13T00:00:00"
                )
                self.assertEqual(raw["strategy"].get("stance"), "bullish")
                self.assertTrue(isinstance(raw["signal_timeline"], list))
        finally:
            AgentService.run = original_run  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
