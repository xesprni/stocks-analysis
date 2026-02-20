import asyncio
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.modules.analysis.agent.schemas import (
    AgentFinalReport,
    AgentRunResult,
    RuntimeDraft,
)
from market_reporter.modules.analysis.agent.service import AgentService
from market_reporter.schemas import RunRequest
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.report_service import ReportService


class ReportServiceAgentModesTest(unittest.TestCase):
    def test_run_report_supports_market_and_stock_modes(self):
        original_run = AgentService.run
        original_to_payload = AgentService.to_analysis_payload

        async def fake_run(self, request, provider_cfg, model, api_key, access_token):
            del self, provider_cfg, model, api_key, access_token
            markdown = (
                "# Agent 分析报告\n\n"
                f"- 模式: {request.mode}\n\n"
                "## 结论摘要（3–6条）\n\n"
                "- 结论一 [E1]\n"
            )
            return AgentRunResult(
                analysis_input={
                    "tool_results": {
                        "search_news": {
                            "as_of": "2026-02-13",
                            "source": "rss",
                            "warnings": [],
                            "items": [{"title": "n1"}, {"title": "n2"}],
                        }
                    }
                },
                runtime_draft=RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    key_levels=[],
                    risks=[],
                    action_items=[],
                    confidence=0.6,
                    conclusions=["结论一 [E1]"],
                    scenario_assumptions={"base": "b", "bull": "u", "bear": "d"},
                    markdown=markdown,
                    raw={},
                ),
                final_report=AgentFinalReport(
                    mode=request.mode,
                    question=request.question,
                    conclusions=["结论一 [E1]"],
                    market_technical="x",
                    fundamentals="x",
                    catalysts_risks="x",
                    valuation_scenarios="x",
                    data_sources=[],
                    guardrail_issues=[],
                    confidence=0.6,
                    markdown=markdown,
                    raw={},
                ),
                tool_calls=[],
                guardrail_issues=[],
                evidence_map=[],
            )

        def fake_to_payload(self, request, run_result):
            del self
            payload = AnalysisInput(
                symbol=request.symbol or "MARKET", market=request.market or "GLOBAL"
            )
            output = AnalysisOutput(
                summary="summary",
                sentiment="neutral",
                key_levels=[],
                risks=[],
                action_items=[],
                confidence=0.6,
                markdown=run_result.final_report.markdown,
                raw={},
            )
            return payload, output

        AgentService.run = fake_run  # type: ignore[method-assign]
        AgentService.to_analysis_payload = fake_to_payload  # type: ignore[method-assign]

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                output_root = root / "output"
                output_root.mkdir(parents=True, exist_ok=True)
                config_path = root / "config" / "settings.yaml"
                store = ConfigStore(config_path=config_path)
                config = AppConfig(
                    output_root=output_root,
                    config_file=config_path,
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
                store.save(config)
                service = ReportService(config_store=store)

                market_result = asyncio.run(
                    service.run_report(RunRequest(mode="market"))
                )
                self.assertIn(
                    "Agent 分析报告",
                    market_result.summary.report_path.read_text(encoding="utf-8"),
                )
                self.assertEqual(market_result.summary.news_total, 2)

                stock_result = asyncio.run(
                    service.run_report(
                        RunRequest(
                            mode="stock",
                            symbol="AAPL",
                            market="US",
                        )
                    )
                )
                self.assertIn(
                    "模式: stock",
                    stock_result.summary.report_path.read_text(encoding="utf-8"),
                )
        finally:
            AgentService.run = original_run  # type: ignore[method-assign]
            AgentService.to_analysis_payload = original_to_payload  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
