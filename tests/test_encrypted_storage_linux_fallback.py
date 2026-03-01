from __future__ import annotations

from keyring.errors import KeyringError

from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.security.keychain_store import resolve_master_key_file
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.services.longbridge_credentials import LongbridgeCredentialService
from market_reporter.services.telegram_config import TelegramConfigService


def _raise_keyring_error(*args, **kwargs):
    raise KeyringError("no backend")


def test_linux_fallback_roundtrip_for_longbridge_and_telegram(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY_FILE", raising=False)
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY", raising=False)
    monkeypatch.setattr("keyring.get_password", _raise_keyring_error)
    monkeypatch.setattr("keyring.set_password", _raise_keyring_error)

    db_path = tmp_path / "data" / "market_reporter.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{db_path}"
    init_db(database_url)

    longbridge = LongbridgeCredentialService(database_url=database_url)
    longbridge.upsert(app_secret="lb-secret", access_token="lb-token")
    assert longbridge.get() == ("lb-secret", "lb-token")

    telegram = TelegramConfigService(database_url=database_url)
    telegram.upsert(
        enabled=True,
        chat_id="-100123",
        bot_token="tg-secret",
        timeout_seconds=12,
    )
    telegram_cfg = telegram.get()
    assert telegram_cfg.enabled is True
    assert telegram_cfg.chat_id == "-100123"
    assert telegram_cfg.bot_token == "tg-secret"

    key_file = resolve_master_key_file(database_url=database_url)
    assert key_file.exists()


def test_linux_fallback_roundtrip_for_analysis_provider_secret(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY_FILE", raising=False)
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY", raising=False)
    monkeypatch.setattr("keyring.get_password", _raise_keyring_error)
    monkeypatch.setattr("keyring.set_password", _raise_keyring_error)

    db_path = tmp_path / "data" / "market_reporter.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{db_path}"
    init_db(database_url)

    config = AppConfig(
        output_root=tmp_path / "output",
        config_file=tmp_path / "config" / "settings.yaml",
        database={"url": database_url},
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

    service = AnalysisService(config=config, registry=ProviderRegistry())
    service.put_secret("openai_compatible", "sk-linux")

    provider_cfg = service._find_provider("openai_compatible")
    resolved = service._resolve_api_key(provider_cfg)
    assert resolved == "sk-linux"

    key_file = resolve_master_key_file(database_url=database_url)
    assert key_file.exists()
