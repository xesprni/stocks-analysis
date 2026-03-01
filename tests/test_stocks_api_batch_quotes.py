from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import stocks
from market_reporter.config import AppConfig
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings


class StockBatchQuotesApiTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.state.settings = AppSettings(
            auth_enabled=False,
            config_file=config_store.config_path,
        )
        app.include_router(stocks.router)
        return app

    def test_batch_quotes_returns_same_length_as_request(self):
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

            response = client.post(
                "/api/stocks/quotes",
                json={
                    "items": [
                        {"symbol": "^GSPC", "market": "US"},
                        {"symbol": "000001", "market": "CN"},
                    ]
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["market"], "US")
            self.assertEqual(payload[1]["market"], "CN")


if __name__ == "__main__":
    unittest.main()
