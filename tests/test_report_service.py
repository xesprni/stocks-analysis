import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.schemas import ReportRunSummary, ReportTaskStatus, RunResult
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.report_service import ReportService


class ReportServiceTest(unittest.TestCase):
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
                json.dumps({"summary": summary.model_dump(mode="json"), "warnings": ["x"]}),
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
                    if snapshot.status in {ReportTaskStatus.SUCCEEDED, ReportTaskStatus.FAILED}:
                        return snapshot
                    await asyncio.sleep(0.01)
                return await service.get_report_task(task.task_id)

            final_state = asyncio.run(scenario())
            self.assertEqual(final_state.status, ReportTaskStatus.SUCCEEDED)
            self.assertIsNotNone(final_state.result)
            self.assertEqual(final_state.result.summary.provider_id, "mock")

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
                    if snapshot.status in {ReportTaskStatus.SUCCEEDED, ReportTaskStatus.FAILED}:
                        return snapshot
                    await asyncio.sleep(0.01)
                return await service.get_report_task(task.task_id)

            final_state = asyncio.run(scenario())
            self.assertEqual(final_state.status, ReportTaskStatus.FAILED)
            self.assertIsNotNone(final_state.error_message)
            self.assertIn("provider timeout", final_state.error_message)


if __name__ == "__main__":
    unittest.main()
