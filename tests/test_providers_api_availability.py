from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import providers
from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings


class ProviderAvailabilityApiTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.state.settings = AppSettings(
            auth_enabled=False,
            config_file=config_store.config_path,
        )
        app.include_router(providers.router)
        return app

    def test_availability_endpoint_for_unknown_provider_returns_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            config = AppConfig(
                output_root=root / "output",
                config_file=config_path,
                database={"url": f"sqlite:///{db_path}"},
                analysis=AnalysisConfig(
                    default_provider="openai_compatible",
                    default_model="gpt-4o-mini",
                    providers=[
                        AnalysisProviderConfig(
                            provider_id="openai_compatible",
                            type="openai_compatible",
                            base_url="https://api.openai.com/v1",
                            models=["gpt-4o-mini"],
                            timeout=20,
                            enabled=True,
                            auth_mode="api_key",
                        )
                    ],
                ),
            )
            store = ConfigStore(config_path=config_path)
            store.save(config)

            app = self._build_app(store)
            client = TestClient(app)
            response = client.get(
                "/api/providers/analysis/unknown_provider/availability"
            )
            self.assertEqual(response.status_code, 200, response.text)

            payload = response.json()
            self.assertFalse(payload["available"])
            self.assertEqual(payload["status"], "not-ready")
            self.assertEqual(payload["provider_id"], "unknown_provider")

    def test_availability_endpoint_returns_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            config = AppConfig(
                output_root=root / "output",
                config_file=config_path,
                database={"url": f"sqlite:///{db_path}"},
                analysis=AnalysisConfig(
                    default_provider="openai_compatible",
                    default_model="gpt-4o-mini",
                    providers=[
                        AnalysisProviderConfig(
                            provider_id="openai_compatible",
                            type="openai_compatible",
                            base_url="https://api.openai.com/v1",
                            models=["gpt-4o-mini"],
                            timeout=20,
                            enabled=True,
                            auth_mode="api_key",
                        )
                    ],
                ),
            )
            store = ConfigStore(config_path=config_path)
            store.save(config)

            app = self._build_app(store)
            client = TestClient(app)
            response = client.get(
                "/api/providers/analysis/openai_compatible/availability"
            )
            self.assertEqual(response.status_code, 200, response.text)

            payload = response.json()
            self.assertFalse(payload["available"])
            self.assertEqual(payload["status"], "not-ready")


if __name__ == "__main__":
    unittest.main()
