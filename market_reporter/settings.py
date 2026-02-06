from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKET_REPORTER_",
        env_file=".env",
        extra="ignore",
    )

    config_file: Path = Path("config/settings.yaml")
    frontend_dist: Path = Path("frontend/dist")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    keychain_service_name: str = "market-reporter"
    keychain_account_name: str = "master-key"
