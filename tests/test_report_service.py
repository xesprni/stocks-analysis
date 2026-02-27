import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import reports
from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.modules.analysis.agent.schemas import (
    AgentFinalReport,
    AgentRunResult,
    RuntimeDraft,
)
from market_reporter.modules.analysis.agent.service import AgentService
from market_reporter.schemas import (
    ReportRunSummary,
    ReportTaskStatus,
    RunRequest,
    RunResult,
)
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.report_service import ReportService


class ReportServiceTest(unittest.TestCase):
    @staticmethod
    def _build_reports_app(
        config_store: ConfigStore, report_service: ReportService
    ) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.state.report_service = report_service
        app.include_router(reports.router)
        return app

    def test_list_reports_reads_meta_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            run_dir = output_root / "20260206_170000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "report.md").write_text("# demo", encoding="utf-8")
            (run_dir / "raw_data.json").write_text("{}", encoding="utf-8")
            summary = ReportRunSummary(
                run_id="20260206_170000",
                generated_at="2026-02-06T17:00:00+08:00",
                report_path=(run_dir / "report.md"),
                raw_data_path=(run_dir / "raw_data.json"),
                warnings_count=1,
                news_total=10,
            )
            (run_dir / "meta.json").write_text(
                json.dumps(
                    {"summary": summary.model_dump(mode="json"), "warnings": ["x"]}
                ),
                encoding="utf-8",
            )

            service = ReportService(config_store=store)
            reports = service.list_reports()

            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].run_id, "20260206_170000")
            self.assertEqual(reports[0].news_total, 10)
            self.assertEqual(reports[0].warnings_count, 1)

    def test_delete_report_removes_run_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            run_dir = output_root / "20260206_180000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "report.md").write_text("# demo", encoding="utf-8")
            (run_dir / "raw_data.json").write_text("{}", encoding="utf-8")

            service = ReportService(config_store=store)
            self.assertTrue(service.delete_report("20260206_180000"))
            self.assertFalse(run_dir.exists())
            self.assertFalse(service.delete_report("20260206_180000"))

    def test_async_report_task_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            service = ReportService(config_store=store)

            async def fake_run_report(overrides=None):
                del overrides
                await asyncio.sleep(0.01)
                summary = ReportRunSummary(
                    run_id="20260207_010101",
                    generated_at="2026-02-07T01:01:01+08:00",
                    report_path=(output_root / "20260207_010101" / "report.md"),
                    raw_data_path=(output_root / "20260207_010101" / "raw_data.json"),
                    warnings_count=0,
                    news_total=0,
                    provider_id="mock",
                    model="market-default",
                )
                return RunResult(summary=summary, warnings=[])

            service.run_report = fake_run_report  # type: ignore[method-assign]

            async def scenario():
                task = await service.start_report_async()
                snapshot = await service.get_report_task(task.task_id)
                self.assertEqual(snapshot.status, ReportTaskStatus.PENDING)

                for _ in range(50):
                    snapshot = await service.get_report_task(task.task_id)
                    if snapshot.status in {
                        ReportTaskStatus.SUCCEEDED,
                        ReportTaskStatus.FAILED,
                    }:
                        return snapshot
                    await asyncio.sleep(0.01)
                return await service.get_report_task(task.task_id)

            final_state = asyncio.run(scenario())
            self.assertEqual(final_state.status, ReportTaskStatus.SUCCEEDED)
            result = final_state.result
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.summary.provider_id, "mock")

    def test_async_report_task_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            service = ReportService(config_store=store)

            async def fake_run_report(overrides=None):
                del overrides
                await asyncio.sleep(0.01)
                raise RuntimeError("provider timeout")

            service.run_report = fake_run_report  # type: ignore[method-assign]

            async def scenario():
                task = await service.start_report_async()
                for _ in range(50):
                    snapshot = await service.get_report_task(task.task_id)
                    if snapshot.status in {
                        ReportTaskStatus.SUCCEEDED,
                        ReportTaskStatus.FAILED,
                    }:
                        return snapshot
                    await asyncio.sleep(0.01)
                return await service.get_report_task(task.task_id)

            final_state = asyncio.run(scenario())
            self.assertEqual(final_state.status, ReportTaskStatus.FAILED)
            error_message = final_state.error_message
            self.assertIsNotNone(error_message)
            assert error_message is not None
            self.assertIn("provider timeout", error_message)

    def test_run_report_writes_extended_summary_fields(self):
        original_run = AgentService.run
        original_to_payload = AgentService.to_analysis_payload

        async def fake_run(self, request, provider_cfg, model, api_key, access_token):
            del self, provider_cfg, model, api_key, access_token
            markdown = "# Agent 分析报告\\n\\n- 模式: market\\n"
            return AgentRunResult(
                analysis_input={
                    "tool_results": {
                        "search_news": {
                            "items": [{"title": "news-1"}],
                            "warnings": [],
                        }
                    }
                },
                runtime_draft=RuntimeDraft(
                    summary="summary",
                    sentiment="bullish",
                    key_levels=[],
                    risks=[],
                    action_items=[],
                    confidence=0.73,
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
                    confidence=0.73,
                    markdown=markdown,
                    raw={},
                ),
                tool_calls=[],
                guardrail_issues=[],
                evidence_map=[],
            )

        def fake_to_payload(self, request, run_result):
            del self, run_result
            return (
                AnalysisInput(symbol="MARKET", market="GLOBAL"),
                AnalysisOutput(
                    summary="summary",
                    sentiment="bullish",
                    key_levels=[],
                    risks=[],
                    action_items=[],
                    confidence=0.73,
                    markdown="# Agent 分析报告",
                    raw={},
                ),
            )

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
                result = asyncio.run(service.run_report())

                self.assertEqual(result.summary.confidence, 0.73)
                self.assertEqual(result.summary.sentiment, "bullish")
                self.assertEqual(result.summary.mode, "market")

                meta_payload = json.loads(
                    (result.summary.report_path.parent / "meta.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(meta_payload["summary"].get("confidence"), 0.73)
                self.assertEqual(meta_payload["summary"].get("sentiment"), "bullish")
                self.assertEqual(meta_payload["summary"].get("mode"), "market")
        finally:
            AgentService.run = original_run  # type: ignore[method-assign]
            AgentService.to_analysis_payload = original_to_payload  # type: ignore[method-assign]

    def test_read_summary_backfills_confidence_sentiment_mode_from_raw_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            run_dir = output_root / "20260210_120000"
            run_dir.mkdir(parents=True, exist_ok=True)
            report_path = run_dir / "report.md"
            raw_path = run_dir / "raw_data.json"
            report_path.write_text("# demo", encoding="utf-8")
            raw_path.write_text(
                json.dumps(
                    {
                        "mode": "stock",
                        "analysis": {
                            "confidence": 0.61,
                            "sentiment": "neutral",
                        },
                    }
                ),
                encoding="utf-8",
            )
            legacy_summary = {
                "run_id": "20260210_120000",
                "generated_at": "2026-02-10T12:00:00+08:00",
                "report_path": str(report_path),
                "raw_data_path": str(raw_path),
                "warnings_count": 2,
                "news_total": 6,
                "provider_id": "mock",
                "model": "market-default",
            }
            (run_dir / "meta.json").write_text(
                json.dumps({"summary": legacy_summary, "warnings": []}),
                encoding="utf-8",
            )

            service = ReportService(config_store=store)
            summary = service.list_reports()[0]
            self.assertEqual(summary.confidence, 0.61)
            self.assertEqual(summary.sentiment, "neutral")
            self.assertEqual(summary.mode, "stock")

    def test_reports_api_returns_extended_fields_for_legacy_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            run_dir = output_root / "20260211_090000"
            run_dir.mkdir(parents=True, exist_ok=True)
            report_path = run_dir / "report.md"
            raw_path = run_dir / "raw_data.json"
            report_path.write_text("# demo", encoding="utf-8")
            raw_path.write_text(
                json.dumps(
                    {
                        "mode": "market",
                        "analysis": {
                            "confidence": 0.88,
                            "sentiment": "bullish",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "run_id": "20260211_090000",
                            "generated_at": "2026-02-11T09:00:00+08:00",
                            "report_path": str(report_path),
                            "raw_data_path": str(raw_path),
                            "warnings_count": 1,
                            "news_total": 3,
                            "provider_id": "mock",
                            "model": "market-default",
                        },
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            service = ReportService(config_store=store)
            app = self._build_reports_app(config_store=store, report_service=service)
            client = TestClient(app)

            response = client.get("/api/reports")
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0].get("confidence"), 0.88)
            self.assertEqual(payload[0].get("sentiment"), "bullish")
            self.assertEqual(payload[0].get("mode"), "market")

    def test_run_report_supports_report_skill_override(self):
        original_run = AgentService.run
        original_to_payload = AgentService.to_analysis_payload

        async def fake_run(self, request, provider_cfg, model, api_key, access_token):
            del self, provider_cfg, model, api_key, access_token
            markdown = f"# Agent 分析报告\n\n- 模式: {request.mode}\n"
            return AgentRunResult(
                analysis_input={
                    "tool_results": {
                        "search_news": {
                            "items": [{"title": "news-1"}],
                            "warnings": [],
                        }
                    }
                },
                runtime_draft=RuntimeDraft(
                    summary="summary",
                    sentiment="neutral",
                    key_levels=[],
                    risks=[],
                    action_items=[],
                    confidence=0.66,
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
                    confidence=0.66,
                    markdown=markdown,
                    raw={},
                ),
                tool_calls=[],
                guardrail_issues=[],
                evidence_map=[],
            )

        def fake_to_payload(self, request, run_result):
            del self, request
            return (
                AnalysisInput(symbol="AAPL", market="US"),
                AnalysisOutput(
                    summary="summary",
                    sentiment="neutral",
                    key_levels=[],
                    risks=[],
                    action_items=[],
                    confidence=0.66,
                    markdown=run_result.final_report.markdown,
                    raw={},
                ),
            )

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
                result = asyncio.run(
                    service.run_report(
                        RunRequest(
                            mode="market",
                            skill_id="stock_report",
                            symbol="AAPL",
                            market="US",
                        )
                    )
                )

                self.assertEqual(result.summary.mode, "stock")
                raw_payload = json.loads(
                    result.summary.raw_data_path.read_text(encoding="utf-8")
                )
                self.assertEqual(raw_payload.get("skill_id"), "stock_report")
        finally:
            AgentService.run = original_run  # type: ignore[method-assign]
            AgentService.to_analysis_payload = original_to_payload  # type: ignore[method-assign]

    def test_run_report_notifies_failure_for_unhandled_exception(self):
        class FakeTelegramNotifier:
            def __init__(self) -> None:
                self.failed = []

            async def notify_report_succeeded(self, result):
                del result
                return True

            async def notify_report_failed(self, *, error, mode, skill_id=None):
                self.failed.append(
                    {
                        "error": error,
                        "mode": mode,
                        "skill_id": skill_id,
                    }
                )
                return True

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            notifier = FakeTelegramNotifier()
            service = ReportService(
                config_store=store,
                telegram_notifier=notifier,  # type: ignore[arg-type]
            )

            def fail_build_runtime_config(*, overrides=None):
                del overrides
                raise RuntimeError("runtime config unavailable")

            service._build_runtime_config = fail_build_runtime_config  # type: ignore[method-assign]

            with self.assertRaises(RuntimeError):
                asyncio.run(
                    service.run_report(
                        RunRequest(mode="stock", skill_id="stock_report")
                    )
                )

            self.assertEqual(len(notifier.failed), 1)
            self.assertEqual(notifier.failed[0]["mode"], "stock")
            self.assertEqual(notifier.failed[0]["skill_id"], "stock_report")
            error_text = str(notifier.failed[0]["error"])
            self.assertIn("runtime config unavailable", error_text)


if __name__ == "__main__":
    unittest.main()
