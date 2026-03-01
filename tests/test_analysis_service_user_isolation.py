from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import hash_password, init_db, session_scope
from market_reporter.infra.security.crypto import generate_master_key
from market_reporter.modules.analysis.service import AnalysisService


class DummyKeychainStore:
    def __init__(self) -> None:
        self._key = generate_master_key()

    def get_or_create_master_key(self) -> bytes:
        return self._key


class AnalysisServiceUserIsolationTest(unittest.TestCase):
    def test_provider_secret_isolated_by_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "market_reporter.db"
            db_url = f"sqlite:///{db_path}"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
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
            init_db(config.database.url)

            with session_scope(config.database.url) as session:
                user_repo = UserRepo(session)
                user1 = user_repo.create(
                    username="analysis-u1",
                    password_hash=hash_password("pw-u1"),
                )
                user2 = user_repo.create(
                    username="analysis-u2",
                    password_hash=hash_password("pw-u2"),
                )
                user1_id = int(user1.id or 0)
                user2_id = int(user2.id or 0)

            keychain_store = DummyKeychainStore()
            service_u1 = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                user_id=user1_id,
                keychain_store=keychain_store,
            )
            service_u2 = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                user_id=user2_id,
                keychain_store=keychain_store,
            )
            service_global = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                user_id=None,
                keychain_store=keychain_store,
            )

            service_u1.put_secret("openai_compatible", "api-key-u1")
            service_u2.put_secret("openai_compatible", "api-key-u2")

            _, _, api_key_u1, _ = service_u1.resolve_credentials(
                provider_id="openai_compatible",
                model="gpt-4o-mini",
            )
            _, _, api_key_u2, _ = service_u2.resolve_credentials(
                provider_id="openai_compatible",
                model="gpt-4o-mini",
            )
            _, _, api_key_global, _ = service_global.resolve_credentials(
                provider_id="openai_compatible",
                model="gpt-4o-mini",
            )

            self.assertEqual(api_key_u1, "api-key-u1")
            self.assertEqual(api_key_u2, "api-key-u2")
            self.assertIsNone(api_key_global)


if __name__ == "__main__":
    unittest.main()
