from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import dashboard
from market_reporter.config import AppConfig
from market_reporter.modules.dashboard.schemas import (
    DashboardIndexMetricView,
    DashboardIndicesSnapshotView,
)
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

            bad_watch_page = client.get("/api/dashboard/watchlist?page=0")
            self.assertEqual(bad_watch_page.status_code, 422)

            bad_watch_page_size_low = client.get("/api/dashboard/watchlist?page_size=1")
            self.assertEqual(bad_watch_page_size_low.status_code, 422)

            bad_watch_page_size_high = client.get("/api/dashboard/watchlist?page_size=100")
            self.assertEqual(bad_watch_page_size_high.status_code, 422)

    def test_indices_endpoint_returns_service_payload(self):
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

            expected = DashboardIndicesSnapshotView(
                generated_at=datetime.now(timezone.utc),
                auto_refresh_enabled=True,
                auto_refresh_seconds=15,
                indices=[
                    DashboardIndexMetricView(
                        symbol="^GSPC",
                        market="US",
                        alias="S&P 500",
                        ts="2026-02-13T00:00:00+00:00",
                        price=5000.0,
                        change=10.0,
                        change_percent=0.2,
                        volume=1000.0,
                        currency="USD",
                        source="mock",
                    )
                ],
            )

            with patch(
                "market_reporter.api.dashboard.DashboardService.get_index_snapshot",
                new=AsyncMock(return_value=expected),
            ):
                response = client.get("/api/dashboard/indices")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(len(payload["indices"]), 1)
            self.assertEqual(payload["indices"][0]["symbol"], "^GSPC")

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
