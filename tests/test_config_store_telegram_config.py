from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig, DatabaseConfig, TelegramConfig
from market_reporter.infra.db.repos import TelegramConfigRepo
from market_reporter.infra.db.session import init_db, session_scope
from market_reporter.services.config_store import ConfigStore


class ConfigStoreTelegramConfigTest(unittest.TestCase):
    def test_save_encrypts_telegram_config_and_keeps_yaml_clean(self):
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
                    telegram=TelegramConfig(
                        enabled=True,
                        chat_id="-100123456789",
                        bot_token="123456:tg-secret-token",
                        timeout_seconds=12,
                    ),
                )
                store.save(config)

                raw_yaml = config_path.read_text(encoding="utf-8")
                self.assertNotIn("tg-secret-token", raw_yaml)
                self.assertNotIn("-100123456789", raw_yaml)

                loaded = store.load()
                self.assertTrue(loaded.telegram.enabled)
                self.assertEqual(loaded.telegram.chat_id, "-100123456789")
                self.assertEqual(loaded.telegram.bot_token, "123456:tg-secret-token")
                self.assertEqual(loaded.telegram.timeout_seconds, 12)

                init_db(loaded.database.url)
                with session_scope(loaded.database.url) as session:
                    row = TelegramConfigRepo(session).get()
                    ciphertext = "" if row is None else row.config_ciphertext

                self.assertIsNotNone(row)
                self.assertNotIn("tg-secret-token", ciphertext)
                self.assertNotIn("-100123456789", ciphertext)
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior


if __name__ == "__main__":
    unittest.main()
