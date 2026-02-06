from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from market_reporter.config import AppConfig, default_app_config, normalize_source_id


class ConfigStore:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            config = default_app_config().model_copy(
                update={"config_file": self.config_path}
            ).normalized()
            config.ensure_data_root()
            self.save(config)
            return config

        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid config file content: {self.config_path}")
        config = AppConfig.model_validate(raw).normalized()
        config.ensure_data_root()
        if self._should_rewrite_news_sources(raw):
            self.save(config)
        return config

    def save(self, config: AppConfig) -> AppConfig:
        normalized = config.model_copy(update={"config_file": self.config_path}).normalized()
        normalized.ensure_data_root()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = normalized.model_dump(mode="json")
        self.config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return normalized

    def patch(self, patch_data: Dict[str, Any]) -> AppConfig:
        current = self.load()
        payload = current.model_dump(mode="python")
        payload.update(patch_data)
        merged = AppConfig.model_validate(payload)
        return self.save(merged)

    @staticmethod
    def _should_rewrite_news_sources(raw_config: Dict[str, Any]) -> bool:
        raw_sources = raw_config.get("news_sources")
        if not isinstance(raw_sources, list):
            return False
        seen: set[str] = set()
        for row in raw_sources:
            if not isinstance(row, dict):
                return True
            if "enabled" not in row:
                return True
            raw_source_id = row.get("source_id")
            if not isinstance(raw_source_id, str) or not raw_source_id.strip():
                return True
            normalized_id = normalize_source_id(raw_source_id)
            if normalized_id != raw_source_id.strip():
                return True
            if normalized_id in seen:
                return True
            seen.add(normalized_id)
        return False
