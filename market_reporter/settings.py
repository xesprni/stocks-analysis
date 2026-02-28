from __future__ import annotations

from pathlib import Path
from typing import Optional

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
    auth_enabled: bool = True
    auth_api_key: Optional[str] = None
    jwt_secret_key: str = "change-me-in-production-with-a-secure-random-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    default_admin_username: str = "admin"
    default_admin_password: Optional[str] = None
