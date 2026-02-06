from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from market_reporter.config import AppConfig, default_app_config


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
