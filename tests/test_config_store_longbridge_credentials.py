from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig, DatabaseConfig, LongbridgeConfig
from market_reporter.infra.db.repos import LongbridgeCredentialRepo
from market_reporter.infra.db.session import init_db, session_scope
from market_reporter.services.config_store import ConfigStore


class ConfigStoreLongbridgeCredentialTest(unittest.TestCase):
    def test_save_writes_encrypted_longbridge_credential_and_sanitizes_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                config_path = root / "config" / "settings.yaml"
                db_path = root / "data" / "market_reporter.db"
                store = ConfigStore(config_path=config_path)

                config = AppConfig(
                    config_file=config_path,
                    output_root=root / "output",
                    database=DatabaseConfig(url=f"sqlite:///{db_path}"),
                    longbridge=LongbridgeConfig(
                        enabled=True,
                        app_key="lb-app-key",
                        app_secret="lb-secret",
                        access_token="lb-token",
                    ),
                )
                store.save(config)

                raw_yaml = config_path.read_text(encoding="utf-8")
                self.assertIn("app_key: lb-app-key", raw_yaml)
                self.assertNotIn("lb-secret", raw_yaml)
                self.assertNotIn("lb-token", raw_yaml)

                loaded = store.load()
                self.assertEqual(loaded.longbridge.app_key, "lb-app-key")
                self.assertEqual(loaded.longbridge.app_secret, "lb-secret")
                self.assertEqual(loaded.longbridge.access_token, "lb-token")
                self.assertTrue(loaded.longbridge.enabled)

                init_db(loaded.database.url)
                with session_scope(loaded.database.url) as session:
                    row = LongbridgeCredentialRepo(session).get()
                    ciphertext = "" if row is None else row.credential_ciphertext
                    nonce = "" if row is None else row.nonce

                self.assertIsNotNone(row)
                self.assertNotIn("lb-secret", ciphertext)
                self.assertNotIn("lb-token", ciphertext)
                self.assertTrue(bool(nonce.strip()))
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior


if __name__ == "__main__":
    unittest.main()
