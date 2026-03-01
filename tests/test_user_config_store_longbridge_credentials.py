from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig, DatabaseConfig, LongbridgeConfig
from market_reporter.infra.db.repos import (
    LongbridgeCredentialRepo,
    UserConfigRepo,
    UserRepo,
)
from market_reporter.infra.db.session import hash_password, init_db, session_scope
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.user_config_store import UserConfigStore


class UserConfigStoreLongbridgeCredentialTest(unittest.TestCase):
    def _create_users(self, db_url: str) -> tuple[int, int]:
        with session_scope(db_url) as session:
            repo = UserRepo(session)
            u1 = repo.create(
                username="u1",
                password_hash=hash_password("pw-u1"),
            )
            u2 = repo.create(
                username="u2",
                password_hash=hash_password("pw-u2"),
            )
            return int(u1.id or 0), int(u2.id or 0)

    def test_credentials_are_isolated_by_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                config_path = root / "config" / "settings.yaml"
                db_path = root / "data" / "market_reporter.db"
                db_url = f"sqlite:///{db_path}"

                global_store = ConfigStore(config_path=config_path)
                global_store.save(
                    AppConfig(
                        config_file=config_path,
                        output_root=root / "output",
                        database=DatabaseConfig(url=db_url),
                        longbridge=LongbridgeConfig(
                            enabled=True,
                            app_key="shared-app-key",
                        ),
                    )
                )

                init_db(db_url)
                user1_id, user2_id = self._create_users(db_url)

                store_u1 = UserConfigStore(
                    database_url=db_url,
                    global_config_path=config_path,
                    user_id=user1_id,
                )
                store_u2 = UserConfigStore(
                    database_url=db_url,
                    global_config_path=config_path,
                    user_id=user2_id,
                )

                cfg_u1 = store_u1.load()
                cfg_u2 = store_u2.load()

                store_u1.save(
                    cfg_u1.model_copy(
                        update={
                            "longbridge": cfg_u1.longbridge.model_copy(
                                update={
                                    "enabled": True,
                                    "app_key": "shared-app-key",
                                    "app_secret": "secret-u1",
                                    "access_token": "token-u1",
                                }
                            )
                        }
                    )
                )
                store_u2.save(
                    cfg_u2.model_copy(
                        update={
                            "longbridge": cfg_u2.longbridge.model_copy(
                                update={
                                    "enabled": True,
                                    "app_key": "shared-app-key",
                                    "app_secret": "secret-u2",
                                    "access_token": "token-u2",
                                }
                            )
                        }
                    )
                )

                loaded_u1 = store_u1.load()
                loaded_u2 = store_u2.load()
                self.assertEqual(loaded_u1.longbridge.app_secret, "secret-u1")
                self.assertEqual(loaded_u1.longbridge.access_token, "token-u1")
                self.assertEqual(loaded_u2.longbridge.app_secret, "secret-u2")
                self.assertEqual(loaded_u2.longbridge.access_token, "token-u2")

                with session_scope(db_url) as session:
                    lb_repo = LongbridgeCredentialRepo(session)
                    row_u1 = lb_repo.get(user_id=user1_id)
                    row_u2 = lb_repo.get(user_id=user2_id)
                    self.assertIsNotNone(row_u1)
                    self.assertIsNotNone(row_u2)
                    row_u1_id = 0 if row_u1 is None else int(row_u1.id or 0)
                    row_u2_id = 0 if row_u2 is None else int(row_u2.id or 0)
                    self.assertNotEqual(row_u1_id, row_u2_id)

                    cfg_repo = UserConfigRepo(session)
                    row_cfg_u1 = cfg_repo.get(user1_id)
                    row_cfg_u2 = cfg_repo.get(user2_id)
                    row_cfg_u1_json = (
                        "" if row_cfg_u1 is None else row_cfg_u1.config_json
                    )
                    row_cfg_u2_json = (
                        "" if row_cfg_u2 is None else row_cfg_u2.config_json
                    )

                self.assertIsNotNone(row_cfg_u1)
                self.assertIsNotNone(row_cfg_u2)
                self.assertNotIn("secret-u1", row_cfg_u1_json)
                self.assertNotIn("token-u1", row_cfg_u1_json)
                self.assertNotIn("secret-u2", row_cfg_u2_json)
                self.assertNotIn("token-u2", row_cfg_u2_json)
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior

    def test_load_migrates_legacy_plaintext_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            key_file = root / "secrets" / "master_key.b64"
            prior = os.environ.get("MARKET_REPORTER_MASTER_KEY_FILE")
            os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = str(key_file)
            try:
                config_path = root / "config" / "settings.yaml"
                db_path = root / "data" / "market_reporter.db"
                db_url = f"sqlite:///{db_path}"

                global_store = ConfigStore(config_path=config_path)
                global_store.save(
                    AppConfig(
                        config_file=config_path,
                        output_root=root / "output",
                        database=DatabaseConfig(url=db_url),
                        longbridge=LongbridgeConfig(
                            enabled=True,
                            app_key="legacy-app-key",
                        ),
                    )
                )
                init_db(db_url)
                user1_id, _ = self._create_users(db_url)

                legacy_payload = global_store.load().model_dump(mode="json")
                legacy_payload["longbridge"] = {
                    "enabled": True,
                    "app_key": "legacy-app-key",
                    "app_secret": "legacy-secret",
                    "access_token": "legacy-token",
                }
                with session_scope(db_url) as session:
                    UserConfigRepo(session).upsert(
                        user_id=user1_id,
                        config_json=json.dumps(legacy_payload, ensure_ascii=False),
                    )

                store_u1 = UserConfigStore(
                    database_url=db_url,
                    global_config_path=config_path,
                    user_id=user1_id,
                )

                loaded = store_u1.load()
                self.assertEqual(loaded.longbridge.app_secret, "legacy-secret")
                self.assertEqual(loaded.longbridge.access_token, "legacy-token")
                self.assertTrue(loaded.longbridge.enabled)

                with session_scope(db_url) as session:
                    cfg_row = UserConfigRepo(session).get(user1_id)
                    lb_row = LongbridgeCredentialRepo(session).get(user_id=user1_id)
                    cfg_row_json = "" if cfg_row is None else cfg_row.config_json
                    lb_ciphertext = (
                        "" if lb_row is None else lb_row.credential_ciphertext
                    )

                self.assertIsNotNone(cfg_row)
                self.assertIsNotNone(lb_row)
                self.assertNotIn("legacy-secret", cfg_row_json)
                self.assertNotIn("legacy-token", cfg_row_json)
                self.assertNotIn("legacy-secret", lb_ciphertext)
                self.assertNotIn("legacy-token", lb_ciphertext)
            finally:
                if prior is None:
                    os.environ.pop("MARKET_REPORTER_MASTER_KEY_FILE", None)
                else:
                    os.environ["MARKET_REPORTER_MASTER_KEY_FILE"] = prior


if __name__ == "__main__":
    unittest.main()
