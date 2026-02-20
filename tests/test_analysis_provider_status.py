import asyncio
import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.security.crypto import generate_master_key
from market_reporter.modules.analysis.service import AnalysisService


class DummyKeychainStore:
    def __init__(self) -> None:
        self._key = generate_master_key()

    def get_or_create_master_key(self) -> bytes:
        return self._key


class AnalysisProviderStatusTest(unittest.TestCase):
    def test_provider_status_ready_and_missing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
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
                        ),
                        AnalysisProviderConfig(
                            provider_id="openai_compatible",
                            type="openai_compatible",
                            base_url="https://api.openai.com/v1",
                            models=["gpt-4o-mini"],
                            timeout=20,
                            enabled=True,
                        ),
                    ],
                ),
            )
            init_db(config.database.url)
            service = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                keychain_store=DummyKeychainStore(),
            )

            providers = {row.provider_id: row for row in service.list_providers()}
            self.assertTrue(providers["mock"].ready)
            self.assertFalse(providers["mock"].secret_required)
            self.assertEqual(providers["mock"].status, "ready")

            self.assertFalse(providers["openai_compatible"].ready)
            self.assertTrue(providers["openai_compatible"].secret_required)
            self.assertEqual(providers["openai_compatible"].status, "missing-secret")

    def test_provider_ready_after_secret_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
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
                        )
                    ],
                ),
            )
            init_db(config.database.url)
            service = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                keychain_store=DummyKeychainStore(),
            )

            with self.assertRaisesRegex(ValueError, "API key"):
                service.ensure_provider_ready("openai_compatible", "gpt-4o-mini")

            service.put_secret("openai_compatible", "secret-value")
            provider = service.ensure_provider_ready("openai_compatible", "gpt-4o-mini")
            self.assertEqual(provider.provider_id, "openai_compatible")
            providers = {row.provider_id: row for row in service.list_providers()}
            self.assertTrue(providers["openai_compatible"].ready)
            self.assertTrue(providers["openai_compatible"].has_secret)

    def test_auth_status_for_none_mode_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
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
                        )
                    ],
                ),
            )
            init_db(config.database.url)
            service = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                keychain_store=DummyKeychainStore(),
            )

            status = asyncio.run(service.get_provider_auth_status("mock"))
            self.assertEqual(status.status, "ready")
            self.assertTrue(status.connected)

    def test_oauth_provider_requires_login_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
                analysis=AnalysisConfig(
                    default_provider="codex_app_server",
                    default_model="gpt-5-codex",
                    providers=[
                        AnalysisProviderConfig(
                            provider_id="codex_app_server",
                            type="codex_app_server",
                            base_url="",
                            models=["gpt-5-codex"],
                            timeout=20,
                            enabled=True,
                            auth_mode="chatgpt_oauth",
                        )
                    ],
                ),
            )
            init_db(config.database.url)
            service = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                keychain_store=DummyKeychainStore(),
            )

            providers = {row.provider_id: row for row in service.list_providers()}
            self.assertEqual(providers["codex_app_server"].status, "login-required")
            self.assertFalse(providers["codex_app_server"].ready)
            with self.assertRaisesRegex(ValueError, "login"):
                service.ensure_provider_ready("codex_app_server", "gpt-5-codex")

    def test_dynamic_provider_keeps_runtime_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
                analysis=AnalysisConfig(
                    default_provider="codex_app_server",
                    default_model="gpt-5-codex",
                    providers=[
                        AnalysisProviderConfig(
                            provider_id="codex_app_server",
                            type="codex_app_server",
                            base_url="http://localhost:9999",
                            models=["gpt-5-codex"],
                            timeout=20,
                            enabled=True,
                            auth_mode="chatgpt_oauth",
                        )
                    ],
                ),
            )
            init_db(config.database.url)
            service = AnalysisService(
                config=config,
                registry=ProviderRegistry(),
                keychain_store=DummyKeychainStore(),
            )

            provider, selected_model = service._select_provider_and_model(
                provider_id="codex_app_server",
                model="gpt-5-codex-high",
            )
            self.assertEqual(provider.provider_id, "codex_app_server")
            self.assertEqual(selected_model, "gpt-5-codex-high")


if __name__ == "__main__":
    unittest.main()
