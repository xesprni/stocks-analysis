from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import dashboard
from market_reporter.config import AppConfig
from market_reporter.services.config_store import ConfigStore


class DashboardSnapshotApiValidationTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.include_router(dashboard.router)
        return app

    def test_snapshot_rejects_invalid_pagination_params(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            config = AppConfig(
                output_root=root / "output",
                config_file=config_path,
                database={"url": f"sqlite:///{db_path}"},
            )
            store = ConfigStore(config_path=config_path)
            store.save(config)

            app = self._build_app(store)
            client = TestClient(app)

            bad_page = client.get("/api/dashboard/snapshot?page=0")
            self.assertEqual(bad_page.status_code, 422)

            bad_page_size_low = client.get("/api/dashboard/snapshot?page_size=1")
            self.assertEqual(bad_page_size_low.status_code, 422)

            bad_page_size_high = client.get("/api/dashboard/snapshot?page_size=100")
            self.assertEqual(bad_page_size_high.status_code, 422)

    def test_can_update_dashboard_auto_refresh_toggle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            config = AppConfig(
                output_root=root / "output",
                config_file=config_path,
                database={"url": f"sqlite:///{db_path}"},
            )
            store = ConfigStore(config_path=config_path)
            store.save(config)

            app = self._build_app(store)
            client = TestClient(app)

            response = client.put(
                "/api/dashboard/auto-refresh",
                json={"auto_refresh_enabled": False},
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertFalse(payload["auto_refresh_enabled"])

            reloaded = store.load()
            self.assertFalse(reloaded.dashboard.auto_refresh_enabled)


if __name__ == "__main__":
    unittest.main()
