"""User-scoped configuration store backed by database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from market_reporter.config import AppConfig, default_app_config
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
            return self._global_store.load()

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            row = repo.get(self.user_id)
            if row is None:
                return self._global_store.load()
            try:
                data = json.loads(row.config_json)
                return AppConfig.model_validate(data).normalized()
            except Exception:
                return self._global_store.load()

    def save(self, config: AppConfig) -> AppConfig:
        if self.user_id is None:
            return self._global_store.save(config)

        normalized = config.normalized()
        data = normalized.model_dump(mode="json")

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            repo.upsert(
                user_id=self.user_id,
                config_json=json.dumps(data, ensure_ascii=False),
            )

        return normalized

    def load_global(self) -> AppConfig:
        return self._global_store.load()

    def save_global(self, config: AppConfig) -> AppConfig:
        return self._global_store.save(config)

    def has_user_config(self) -> bool:
        if self.user_id is None:
            return False

        with session_scope(self.database_url) as session:
            repo = UserConfigRepo(session)
            return repo.get(self.user_id) is not None

    def init_from_global(self) -> AppConfig:
        if self.user_id is None:
            return self._global_store.load()

        global_config = self._global_store.load()
        return self.save(global_config)
