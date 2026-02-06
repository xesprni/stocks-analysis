import json
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.schemas import ReportRunSummary
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


if __name__ == "__main__":
    unittest.main()
