from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import config as config_module
from market_reporter.config import AppConfig, DatabaseConfig, TelegramConfig
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.telegram_config import TelegramConfigService


class TelegramApiTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.include_router(config_module.router)
        return app

    def _make_store(
        self, tmpdir: str, telegram: TelegramConfig | None = None
    ) -> ConfigStore:
        root = Path(tmpdir)
        config_path = root / "config" / "settings.yaml"
        db_path = root / "data" / "market_reporter.db"
        store = ConfigStore(config_path=config_path)
        config = AppConfig(
            output_root=root / "output",
            config_file=config_path,
            database=DatabaseConfig(url=f"sqlite:///{db_path}"),
            telegram=telegram or TelegramConfig(),
        )
        store.save(config)
        return store

    def test_get_telegram_config_redacts_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                store = self._make_store(
                    tmpdir,
                    telegram=TelegramConfig(
                        enabled=True,
                        chat_id="-100123",
                        bot_token="token-secret",
                        timeout_seconds=11,
                    ),
                )
                client = TestClient(self._build_app(store))

                response = client.get("/api/telegram")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["enabled"])
                self.assertEqual(payload["chat_id"], "-100123")
                self.assertEqual(payload["bot_token"], "***")
                self.assertEqual(payload["timeout_seconds"], 11)
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior

    def test_update_telegram_config_keeps_existing_token_with_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                store = self._make_store(
                    tmpdir,
                    telegram=TelegramConfig(
                        enabled=True,
                        chat_id="-100old",
                        bot_token="old-token",
                        timeout_seconds=10,
                    ),
                )
                client = TestClient(self._build_app(store))

                response = client.put(
                    "/api/telegram",
                    json={
                        "enabled": True,
                        "chat_id": "-100new",
                        "bot_token": "***",
                        "timeout_seconds": 18,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"ok": True})

                loaded = store.load()
                self.assertTrue(loaded.telegram.enabled)
                self.assertEqual(loaded.telegram.chat_id, "-100new")
                self.assertEqual(loaded.telegram.bot_token, "old-token")
                self.assertEqual(loaded.telegram.timeout_seconds, 18)
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior

    def test_delete_telegram_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                store = self._make_store(
                    tmpdir,
                    telegram=TelegramConfig(
                        enabled=True,
                        chat_id="-100del",
                        bot_token="to-delete",
                        timeout_seconds=12,
                    ),
                )
                client = TestClient(self._build_app(store))

                response = client.delete("/api/telegram")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"ok": True})

                loaded = store.load()
                self.assertFalse(loaded.telegram.enabled)
                self.assertEqual(loaded.telegram.chat_id, "")
                self.assertEqual(loaded.telegram.bot_token, "")

                service = TelegramConfigService(database_url=loaded.database.url)
                self.assertFalse(service.has_config())
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior


if __name__ == "__main__":
    unittest.main()
