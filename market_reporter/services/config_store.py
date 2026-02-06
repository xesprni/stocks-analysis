from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from market_reporter.config import (
    AppConfig,
    default_analysis_providers,
    default_app_config,
    normalize_source_id,
)


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
        config = self._normalize_analysis_providers(config)
        config.ensure_data_root()
        if self._should_rewrite_news_sources(raw) or self._should_rewrite_analysis(raw, config):
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

    @staticmethod
    def _normalize_analysis_providers(config: AppConfig) -> AppConfig:
        providers = []
        seen: set[str] = set()
        for provider in config.analysis.providers:
            provider_id = provider.provider_id.strip()
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            providers.append(provider.model_copy(update={"provider_id": provider_id}))

        for provider in default_analysis_providers():
            if provider.provider_id in seen:
                continue
            providers.append(provider)
            seen.add(provider.provider_id)

        analysis = config.analysis.model_copy(update={"providers": providers})
        provider_map = {provider.provider_id: provider for provider in providers}
        if analysis.default_provider not in provider_map:
            fallback_provider = next(
                (provider.provider_id for provider in providers if provider.enabled),
                providers[0].provider_id if providers else "mock",
            )
            analysis = analysis.model_copy(update={"default_provider": fallback_provider})

        default_provider = provider_map.get(analysis.default_provider)
        if default_provider is not None and default_provider.models:
            auth_mode = default_provider.auth_mode or (
                "chatgpt_oauth" if default_provider.type == "codex_app_server" else "api_key"
            )
            if auth_mode != "chatgpt_oauth" and analysis.default_model not in default_provider.models:
                analysis = analysis.model_copy(update={"default_model": default_provider.models[0]})
            if auth_mode == "chatgpt_oauth" and not analysis.default_model:
                analysis = analysis.model_copy(update={"default_model": default_provider.models[0]})

        return config.model_copy(update={"analysis": analysis})

    @staticmethod
    def _should_rewrite_analysis(raw_config: Dict[str, Any], normalized_config: AppConfig) -> bool:
        raw_analysis = raw_config.get("analysis")
        if not isinstance(raw_analysis, dict):
            return True
        raw_providers = raw_analysis.get("providers")
        if not isinstance(raw_providers, list):
            return True
        raw_ids = []
        for row in raw_providers:
            if not isinstance(row, dict):
                return True
            provider_id = row.get("provider_id")
            if not isinstance(provider_id, str) or not provider_id.strip():
                return True
            raw_ids.append(provider_id.strip())

        normalized_ids = [provider.provider_id for provider in normalized_config.analysis.providers]
        if raw_ids != normalized_ids:
            return True
        if raw_analysis.get("default_provider") != normalized_config.analysis.default_provider:
            return True
        if raw_analysis.get("default_model") != normalized_config.analysis.default_model:
            return True
        return False
