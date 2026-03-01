from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig, DatabaseConfig
from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import hash_password, init_db, session_scope
from market_reporter.schemas import ReportRunSummary
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.report_service import ReportService


class ReportServiceUserIsolationTest(unittest.TestCase):
    def _create_run(self, root: Path, run_id: str) -> None:
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "report.md"
        raw_path = run_dir / "raw_data.json"
        report_path.write_text("# demo", encoding="utf-8")
        raw_path.write_text("{}", encoding="utf-8")
        summary = ReportRunSummary(
            run_id=run_id,
            generated_at="2026-02-20T12:00:00+08:00",
            report_path=report_path,
            raw_data_path=raw_path,
            warnings_count=0,
            news_total=0,
        )
        (run_dir / "meta.json").write_text(
            json.dumps({"summary": summary.model_dump(mode="json"), "warnings": []}),
            encoding="utf-8",
        )

    def test_list_and_get_reports_are_user_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            db_url = f"sqlite:///{db_path}"

            store = ConfigStore(config_path=config_path)
            store.save(
                AppConfig(
                    output_root=output_root,
                    config_file=config_path,
                    database=DatabaseConfig(url=db_url),
                )
            )
            init_db(db_url)

            with session_scope(db_url) as session:
                repo = UserRepo(session)
                user1 = repo.create(
                    username="report-u1",
                    password_hash=hash_password("pw-u1"),
                )
                user2 = repo.create(
                    username="report-u2",
                    password_hash=hash_password("pw-u2"),
                )
                user1_id = int(user1.id or 0)
                user2_id = int(user2.id or 0)

            self._create_run(output_root / f"user_{user1_id}", "20260220_120000")
            self._create_run(output_root / f"user_{user2_id}", "20260220_120500")

            service = ReportService(config_store=store)

            u1_reports = service.list_reports(user_id=user1_id)
            u2_reports = service.list_reports(user_id=user2_id)
            global_reports = service.list_reports(user_id=None)

            self.assertEqual(len(u1_reports), 1)
            self.assertEqual(len(u2_reports), 1)
            self.assertEqual(len(global_reports), 0)
            self.assertEqual(u1_reports[0].run_id, "20260220_120000")
            self.assertEqual(u2_reports[0].run_id, "20260220_120500")

            u1_detail = service.get_report("20260220_120000", user_id=user1_id)
            self.assertEqual(u1_detail.summary.run_id, "20260220_120000")

            with self.assertRaises(FileNotFoundError):
                service.get_report("20260220_120500", user_id=user1_id)


if __name__ == "__main__":
    unittest.main()
