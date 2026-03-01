"""User-scoped configuration store backed by database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from market_reporter.config import AppConfig
from market_reporter.infra.db.repos import UserConfigRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.services.config_store import ConfigStore


class UserConfigStore:
    """Per-user configuration stored in database."""

    def __init__(
        self,
        database_url: str,
        global_config_path: Path,
        user_id: Optional[int] = None,
    ) -> None:
        self.database_url = database_url
        self.global_config_path = global_config_path
        self.user_id = user_id
        self._global_store = ConfigStore(config_path=global_config_path)

    def load(self) -> AppConfig:
        if self.user_id is None:
            return self._global_store.load(user_id=None)

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            row = repo.get(self.user_id)
            if row is None:
                return self._global_store.load(user_id=self.user_id)
            try:
                data = json.loads(row.config_json)
                config = AppConfig.model_validate(data).normalized()
            except Exception:
                return self._global_store.load(user_id=self.user_id)

            sanitized = self._migrate_legacy_sensitive_config(config)
            sanitized_payload = sanitized.model_dump(mode="json")
            if data != sanitized_payload:
                repo.upsert(
                    user_id=self.user_id,
                    config_json=json.dumps(sanitized_payload, ensure_ascii=False),
                )

        return self._hydrate_sensitive_config(sanitized)

    def save(self, config: AppConfig) -> AppConfig:
        if self.user_id is None:
            return self._global_store.save(config, user_id=None)

        normalized = config.normalized()
        sanitized = self._persist_sensitive_config(normalized)
        data = sanitized.model_dump(mode="json")

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            repo.upsert(
                user_id=self.user_id,
                config_json=json.dumps(data, ensure_ascii=False),
            )

        return self._hydrate_sensitive_config(sanitized)

    def load_global(self) -> AppConfig:
        return self._global_store.load(user_id=None)

    def save_global(self, config: AppConfig) -> AppConfig:
        return self._global_store.save(config, user_id=None)

    def has_user_config(self) -> bool:
        if self.user_id is None:
            return False

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            return repo.get(self.user_id) is not None

    def init_from_global(self) -> AppConfig:
        if self.user_id is None:
            return self._global_store.load(user_id=None)

        global_config = self._global_store.load(user_id=self.user_id)
        return self.save(global_config)

    def _persist_sensitive_config(self, config: AppConfig) -> AppConfig:
        with_longbridge = self._global_store._persist_longbridge_credentials(
            config=config,
            user_id=self.user_id,
        )
        return self._global_store._persist_telegram_config(
            config=with_longbridge,
            user_id=self.user_id,
        )

    def _hydrate_sensitive_config(self, config: AppConfig) -> AppConfig:
        with_longbridge = self._global_store._hydrate_longbridge_credentials(
            config=config,
            user_id=self.user_id,
        )
        return self._global_store._hydrate_telegram_config(
            config=with_longbridge,
            user_id=self.user_id,
        )

    def _migrate_legacy_sensitive_config(self, config: AppConfig) -> AppConfig:
        migrated = config

        app_secret = str(config.longbridge.app_secret or "").strip()
        access_token = str(config.longbridge.access_token or "").strip()
        needs_lb_migration = app_secret not in {"", "***"} or access_token not in {
            "",
            "***",
        }
        if needs_lb_migration:
            migrated = self._global_store._persist_longbridge_credentials(
                config=migrated,
                user_id=self.user_id,
            )

        chat_id = str(config.telegram.chat_id or "").strip()
        bot_token = str(config.telegram.bot_token or "").strip()
        needs_tg_migration = bool(chat_id or (bot_token and bot_token != "***"))
        if needs_tg_migration:
            migrated = self._global_store._persist_telegram_config(
                config=migrated,
                user_id=self.user_id,
            )

        return migrated
