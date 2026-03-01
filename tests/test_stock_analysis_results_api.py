from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import analysis
from market_reporter.api.stock_analysis_tasks import StockAnalysisTaskManager
from market_reporter.config import AppConfig, DatabaseConfig
from market_reporter.infra.db.repos import StockAnalysisRunRepo
from market_reporter.infra.db.session import init_db, session_scope
from market_reporter.modules.analysis.schemas import (
    StockAnalysisTaskStatus,
    StockAnalysisTaskView,
)
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings


class StockAnalysisResultsApiTest(unittest.TestCase):
    @staticmethod
    def _build_app(
        config_store: ConfigStore, task_manager: StockAnalysisTaskManager
    ) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.state.stock_analysis_task_manager = task_manager
        app.state.settings = AppSettings(
            auth_enabled=False,
            config_file=config_store.config_path,
        )
        app.include_router(analysis.router)
        return app

    def test_list_and_get_stock_analysis_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "market_reporter.db"
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)

            config_path = root / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)
            config = AppConfig(
                output_root=output_root,
                config_file=config_path,
                database=DatabaseConfig(url=f"sqlite:///{db_path}"),
            )
            store.save(config)
            init_db(config.database.url)

            with session_scope(config.database.url) as session:
                repo = StockAnalysisRunRepo(session)
                row1 = repo.add(
                    symbol="AAPL",
                    market="US",
                    provider_id="mock",
                    model="market-default",
                    status="SUCCESS",
                    input_json=json.dumps({"symbol": "AAPL"}),
                    output_json=json.dumps(
                        {
                            "summary": "AAPL summary",
                            "sentiment": "bullish",
                            "confidence": 0.8,
                        }
                    ),
                    markdown="# AAPL",
                )
                row1_id = int(row1.id)
                row2 = repo.add(
                    symbol="PDD",
                    market="US",
                    provider_id="mock",
                    model="market-default",
                    status="SUCCESS",
                    input_json=json.dumps({"symbol": "PDD"}),
                    output_json=json.dumps(
                        {
                            "summary": "PDD summary",
                            "sentiment": "neutral",
                            "confidence": 0.6,
                        }
                    ),
                    markdown="# PDD",
                )
                row2_id = int(row2.id)

            app = self._build_app(store, StockAnalysisTaskManager(store))
            client = TestClient(app)

            list_response = client.get("/api/analysis/stocks/runs?limit=10")
            self.assertEqual(list_response.status_code, 200)
            payload = list_response.json()
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["id"], row2_id)
            self.assertEqual(payload[1]["id"], row1_id)

            filtered = client.get("/api/analysis/stocks/runs?symbol=aapl&market=US")
            self.assertEqual(filtered.status_code, 200)
            filtered_payload = filtered.json()
            self.assertEqual(len(filtered_payload), 1)
            self.assertEqual(filtered_payload[0]["symbol"], "AAPL")

            detail_response = client.get(f"/api/analysis/stocks/runs/{row1_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail = detail_response.json()
            self.assertEqual(detail["id"], row1_id)
            self.assertEqual(detail["symbol"], "AAPL")
            self.assertEqual(detail["output_json"]["summary"], "AAPL summary")

            not_found = client.get("/api/analysis/stocks/runs/999999")
            self.assertEqual(not_found.status_code, 404)

            deleted = client.delete(f"/api/analysis/stocks/runs/{row1_id}")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(deleted.json(), {"deleted": True})

            deleted_again = client.delete(f"/api/analysis/stocks/runs/{row1_id}")
            self.assertEqual(deleted_again.status_code, 200)
            self.assertEqual(deleted_again.json(), {"deleted": False})

            after_delete = client.get(f"/api/analysis/stocks/runs/{row1_id}")
            self.assertEqual(after_delete.status_code, 404)

    def test_list_stock_analysis_tasks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            output_root.mkdir(parents=True, exist_ok=True)
            config_path = root / "config" / "settings.yaml"

            store = ConfigStore(config_path=config_path)
            config = AppConfig(output_root=output_root, config_file=config_path)
            store.save(config)

            manager = StockAnalysisTaskManager(store)
            now = datetime.now(timezone.utc)
            manager._tasks = {
                "task_old": StockAnalysisTaskView(
                    task_id="task_old",
                    symbol="AAPL",
                    market="US",
                    status=StockAnalysisTaskStatus.RUNNING,
                    created_at=now - timedelta(minutes=1),
                ),
                "task_new": StockAnalysisTaskView(
                    task_id="task_new",
                    symbol="PDD",
                    market="US",
                    status=StockAnalysisTaskStatus.PENDING,
                    created_at=now,
                ),
            }

            app = self._build_app(store, manager)
            client = TestClient(app)
            response = client.get("/api/analysis/stocks/tasks")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["task_id"], "task_new")
            self.assertEqual(payload[1]["task_id"], "task_old")


if __name__ == "__main__":
    unittest.main()
