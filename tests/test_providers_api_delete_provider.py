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


class DeleteAnalysisProviderApiTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.state.settings = AppSettings(
            auth_enabled=False,
            config_file=config_store.config_path,
        )
        app.include_router(providers.router)
        return app

    def test_delete_provider_does_not_fail_after_config_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            db_path = root / "data" / "market_reporter.db"
            config = AppConfig(
                output_root=root / "output",
                config_file=config_path,
                database={"url": f"sqlite:///{db_path}"},
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
                        ),
                        AnalysisProviderConfig(
                            provider_id="openai_compatible",
                            type="openai_compatible",
                            base_url="https://api.openai.com/v1",
                            models=["gpt-4o-mini"],
                            timeout=20,
                            enabled=True,
                            auth_mode="api_key",
                        ),
                    ],
                ),
            )
            store = ConfigStore(config_path=config_path)
            store.save(config)

            app = self._build_app(store)
            client = TestClient(app)
            response = client.delete("/api/providers/analysis/mock")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            provider_ids = [
                item["provider_id"] for item in payload["analysis"]["providers"]
            ]
            self.assertNotIn("mock", provider_ids)
            self.assertGreaterEqual(len(provider_ids), 1)

            # Reload through API to ensure config normalization does not re-add deleted provider.
            listed = client.get("/api/providers/analysis")
            self.assertEqual(listed.status_code, 200, listed.text)
            listed_ids = [item["provider_id"] for item in listed.json()]
            self.assertNotIn("mock", listed_ids)


if __name__ == "__main__":
    unittest.main()
