"""Tests for Longbridge API endpoints (token management and config retrieval)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_reporter.api import config as config_module
from market_reporter.config import AppConfig, DatabaseConfig, LongbridgeConfig
from market_reporter.services.longbridge_credentials import LongbridgeCredentialService
from market_reporter.services.config_store import ConfigStore


class LongbridgeApiTest(unittest.TestCase):
    def _build_app(self, config_store: ConfigStore) -> FastAPI:
        app = FastAPI()
        app.state.config_store = config_store
        app.include_router(config_module.router)
        return app

    def _make_store(self, tmpdir: str, **lb_overrides) -> ConfigStore:
        root = Path(tmpdir)
        config_path = root / "config" / "settings.yaml"
        db_path = root / "data" / "market_reporter.db"
        lb = LongbridgeConfig(**lb_overrides) if lb_overrides else LongbridgeConfig()
        config = AppConfig(
            output_root=root / "output",
            config_file=config_path,
            database=DatabaseConfig(url=f"sqlite:///{db_path}"),
            longbridge=lb,
        )
        store = ConfigStore(config_path=config_path)
        store.save(config)
        return store

    # ---- GET /api/longbridge ----

    def test_get_longbridge_config_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(
                tmpdir,
                enabled=True,
                app_key="real_key",
                app_secret="real_secret",
                access_token="real_token",
            )
            app = self._build_app(store)
            client = TestClient(app)

            response = client.get("/api/longbridge")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["app_key"], "real_key")
            self.assertEqual(data["app_secret"], "***")
            self.assertEqual(data["access_token"], "***")
            self.assertTrue(data["enabled"])

    def test_get_longbridge_config_empty_secrets_not_redacted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            app = self._build_app(store)
            client = TestClient(app)

            response = client.get("/api/longbridge")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["app_secret"], "")
            self.assertEqual(data["access_token"], "")
            self.assertFalse(data["enabled"])

    # ---- PUT /api/longbridge/token ----

    def test_update_longbridge_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            app = self._build_app(store)
            client = TestClient(app)

            response = client.put(
                "/api/longbridge/token",
                json={
                    "app_key": "new_key",
                    "app_secret": "new_secret",
                    "access_token": "new_token",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True})

            # Verify the config was actually saved
            config = store.load()
            self.assertEqual(config.longbridge.app_key, "new_key")
            self.assertEqual(config.longbridge.app_secret, "new_secret")
            self.assertEqual(config.longbridge.access_token, "new_token")
            self.assertTrue(config.longbridge.enabled)

            raw_yaml = store.config_path.read_text(encoding="utf-8")
            self.assertNotIn("new_secret", raw_yaml)
            self.assertNotIn("new_token", raw_yaml)

    def test_update_longbridge_token_partial_disables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            app = self._build_app(store)
            client = TestClient(app)

            response = client.put(
                "/api/longbridge/token",
                json={
                    "app_key": "key_only",
                    "app_secret": "",
                    "access_token": "",
                },
            )
            self.assertEqual(response.status_code, 200)
            config = store.load()
            self.assertFalse(config.longbridge.enabled)

    # ---- DELETE /api/longbridge/token ----

    def test_delete_longbridge_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(
                tmpdir,
                enabled=True,
                app_key="key",
                app_secret="secret",
                access_token="token",
            )
            app = self._build_app(store)
            client = TestClient(app)

            response = client.delete("/api/longbridge/token")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True})

            config = store.load()
            self.assertFalse(config.longbridge.enabled)
            self.assertEqual(config.longbridge.app_key, "")
            self.assertEqual(config.longbridge.app_secret, "")
            self.assertEqual(config.longbridge.access_token, "")

            credential_service = LongbridgeCredentialService(
                database_url=config.database.url
            )
            self.assertFalse(credential_service.has_credentials())

    # ---- GET /api/config redaction ----

    def test_get_config_redacts_longbridge_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(
                tmpdir,
                enabled=True,
                app_key="my_key",
                app_secret="my_secret",
                access_token="my_token",
            )
            app = self._build_app(store)
            client = TestClient(app)

            response = client.get("/api/config")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            lb = data["longbridge"]
            self.assertEqual(lb["app_key"], "my_key")
            self.assertEqual(lb["app_secret"], "***")
            self.assertEqual(lb["access_token"], "***")

    def test_update_config_keeps_redacted_longbridge_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(
                tmpdir,
                enabled=True,
                app_key="my_key",
                app_secret="my_secret",
                access_token="my_token",
            )
            app = self._build_app(store)
            client = TestClient(app)

            payload = client.get("/api/config").json()
            payload["symbol_search"]["default_provider"] = "longbridge"

            response = client.put("/api/config", json=payload)
            self.assertEqual(response.status_code, 200)

            config = store.load()
            self.assertEqual(config.longbridge.app_secret, "my_secret")
            self.assertEqual(config.longbridge.access_token, "my_token")
            self.assertEqual(config.symbol_search.default_provider, "longbridge")


class LongbridgeConfigModelTest(unittest.TestCase):
    def test_default_config_disabled(self):
        cfg = LongbridgeConfig()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.app_key, "")
        self.assertEqual(cfg.app_secret, "")
        self.assertEqual(cfg.access_token, "")

    def test_roundtrip_serialization(self):
        cfg = LongbridgeConfig(
            enabled=True,
            app_key="k",
            app_secret="s",
            access_token="t",
        )
        data = cfg.model_dump()
        restored = LongbridgeConfig.model_validate(data)
        self.assertEqual(restored.enabled, True)
        self.assertEqual(restored.app_key, "k")
        self.assertEqual(restored.app_secret, "s")
        self.assertEqual(restored.access_token, "t")

    def test_app_config_includes_longbridge(self):
        config = AppConfig()
        self.assertIsInstance(config.longbridge, LongbridgeConfig)
        self.assertFalse(config.longbridge.enabled)


if __name__ == "__main__":
    unittest.main()
