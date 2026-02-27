from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from market_reporter.config import (
    AppConfig,
    TelegramConfig,
    default_analysis_providers,
    default_app_config,
)
from market_reporter.infra.db.session import init_db
from market_reporter.services.longbridge_credentials import LongbridgeCredentialService
from market_reporter.services.telegram_config import TelegramConfigService


class ConfigStore:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            config = (
                default_app_config()
                .model_copy(update={"config_file": self.config_path})
                .normalized()
            )
            config.ensure_data_root()
            self.save(config)
            return config

        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid config file content: {self.config_path}")
        config = AppConfig.model_validate(raw).normalized()
        config = self._normalize_analysis_providers(config, raw_config=raw)
        config.ensure_data_root()
        if (
            self._should_rewrite_analysis(raw, config)
            or self._should_rewrite_agent(raw)
            or self._should_rewrite_dashboard(raw)
            or self._should_rewrite_longbridge(raw)
        ):
            return self.save(config)
        return self._hydrate_telegram_config(
            self._hydrate_longbridge_credentials(config)
        )

    def save(self, config: AppConfig) -> AppConfig:
        normalized = config.model_copy(
            update={"config_file": self.config_path}
        ).normalized()
        normalized.ensure_data_root()
        normalized = self._persist_longbridge_credentials(config=normalized)
        normalized = self._persist_telegram_config(config=normalized)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = normalized.model_dump(mode="json")
        self.config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        hydrated = self._hydrate_longbridge_credentials(normalized)
        return self._hydrate_telegram_config(hydrated)

    def patch(self, patch_data: Dict[str, Any]) -> AppConfig:
        current = self.load()
        payload = current.model_dump(mode="python")
        payload.update(patch_data)
        merged = AppConfig.model_validate(payload)
        return self.save(merged)

    @staticmethod
    def _normalize_analysis_providers(
        config: AppConfig, raw_config: Dict[str, Any]
    ) -> AppConfig:
        providers = []
        seen: set[str] = set()
        for provider in config.analysis.providers:
            provider_id = provider.provider_id.strip()
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            inferred_auth_mode = provider.auth_mode or (
                "none"
                if provider.type == "mock"
                else (
                    "chatgpt_oauth"
                    if provider.type == "codex_app_server"
                    else "api_key"
                )
            )
            providers.append(
                provider.model_copy(
                    update={
                        "provider_id": provider_id,
                        "auth_mode": inferred_auth_mode,
                    }
                )
            )

        raw_analysis = raw_config.get("analysis")
        raw_providers = (
            raw_analysis.get("providers") if isinstance(raw_analysis, dict) else None
        )
        should_backfill_defaults = not isinstance(raw_providers, list)
        if should_backfill_defaults:
            for provider in default_analysis_providers():
                if provider.provider_id in seen:
                    continue
                providers.append(provider)
                seen.add(provider.provider_id)

        if not providers:
            # Keep app usable when provider list is empty/invalid.
            defaults = default_analysis_providers()
            if defaults:
                providers = [defaults[0]]

        if providers and not any(provider.enabled for provider in providers):
            providers[0] = providers[0].model_copy(update={"enabled": True})

        analysis = config.analysis.model_copy(update={"providers": providers})
        provider_map = {provider.provider_id: provider for provider in providers}
        selected_default = provider_map.get(analysis.default_provider)
        if selected_default is None or not selected_default.enabled:
            fallback_provider = next(
                (provider.provider_id for provider in providers if provider.enabled),
                providers[0].provider_id if providers else "mock",
            )
            analysis = analysis.model_copy(
                update={"default_provider": fallback_provider}
            )

        default_provider = provider_map.get(analysis.default_provider)
        if default_provider is not None and default_provider.models:
            auth_mode = default_provider.auth_mode or (
                "chatgpt_oauth"
                if default_provider.type == "codex_app_server"
                else "api_key"
            )
            if (
                auth_mode != "chatgpt_oauth"
                and analysis.default_model not in default_provider.models
            ):
                analysis = analysis.model_copy(
                    update={"default_model": default_provider.models[0]}
                )
            if auth_mode == "chatgpt_oauth" and not analysis.default_model:
                analysis = analysis.model_copy(
                    update={"default_model": default_provider.models[0]}
                )

        return config.model_copy(update={"analysis": analysis})

    @staticmethod
    def _should_rewrite_analysis(
        raw_config: Dict[str, Any], normalized_config: AppConfig
    ) -> bool:
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
            auth_mode = row.get("auth_mode")
            if auth_mode is None:
                return True
            if not isinstance(auth_mode, str) or not auth_mode.strip():
                return True
            raw_ids.append(provider_id.strip())

        normalized_ids = [
            provider.provider_id for provider in normalized_config.analysis.providers
        ]
        if raw_ids != normalized_ids:
            return True
        if (
            raw_analysis.get("default_provider")
            != normalized_config.analysis.default_provider
        ):
            return True
        if (
            raw_analysis.get("default_model")
            != normalized_config.analysis.default_model
        ):
            return True
        return False

    @staticmethod
    def _should_rewrite_agent(raw_config: Dict[str, Any]) -> bool:
        raw_agent = raw_config.get("agent")
        if not isinstance(raw_agent, dict):
            return True
        required_keys = {
            "enabled",
            "max_steps",
            "max_tool_calls",
            "consistency_tolerance",
            "default_news_window_days",
            "default_filing_window_days",
            "default_price_window_days",
        }
        return not required_keys.issubset(set(raw_agent.keys()))

    @staticmethod
    def _should_rewrite_dashboard(raw_config: Dict[str, Any]) -> bool:
        raw_dashboard = raw_config.get("dashboard")
        if not isinstance(raw_dashboard, dict):
            return True
        required_keys = {
            "indices",
            "auto_refresh_enabled",
            "auto_refresh_seconds",
        }
        return not required_keys.issubset(set(raw_dashboard.keys()))

    @staticmethod
    def _should_rewrite_longbridge(raw_config: Dict[str, Any]) -> bool:
        raw_longbridge = raw_config.get("longbridge")
        if not isinstance(raw_longbridge, dict):
            return False
        app_secret = str(raw_longbridge.get("app_secret") or "").strip()
        access_token = str(raw_longbridge.get("access_token") or "").strip()
        return app_secret not in {"", "***"} or access_token not in {"", "***"}

    def _persist_longbridge_credentials(self, config: AppConfig) -> AppConfig:
        longbridge = config.longbridge
        app_secret = str(longbridge.app_secret or "").strip()
        access_token = str(longbridge.access_token or "").strip()
        app_key = str(longbridge.app_key or "").strip()

        has_credentials = False
        try:
            init_db(config.database.url)
            service = LongbridgeCredentialService(database_url=config.database.url)
            if (
                app_secret
                and access_token
                and app_secret != "***"
                and access_token != "***"
            ):
                service.upsert(app_secret=app_secret, access_token=access_token)
            has_credentials = service.has_credentials()
        except Exception:
            has_credentials = bool(
                app_secret
                and access_token
                and app_secret != "***"
                and access_token != "***"
            )

        sanitized_longbridge = longbridge.model_copy(
            update={
                "app_secret": "",
                "access_token": "",
                "enabled": bool(longbridge.enabled and app_key and has_credentials),
            }
        )
        return config.model_copy(update={"longbridge": sanitized_longbridge})

    def _hydrate_longbridge_credentials(self, config: AppConfig) -> AppConfig:
        longbridge = config.longbridge
        app_key = str(longbridge.app_key or "").strip()
        app_secret = ""
        access_token = ""
        has_credentials = False

        try:
            init_db(config.database.url)
            service = LongbridgeCredentialService(database_url=config.database.url)
            app_secret, access_token = service.get()
            has_credentials = bool(app_secret and access_token)
        except Exception:
            has_credentials = False

        hydrated_longbridge = longbridge.model_copy(
            update={
                "app_secret": app_secret,
                "access_token": access_token,
                "enabled": bool(longbridge.enabled and app_key and has_credentials),
            }
        )
        return config.model_copy(update={"longbridge": hydrated_longbridge})

    def _persist_telegram_config(self, config: AppConfig) -> AppConfig:
        telegram = config.telegram
        enabled = bool(telegram.enabled)
        chat_id = str(telegram.chat_id or "").strip()
        bot_token = str(telegram.bot_token or "").strip()
        timeout_seconds = int(telegram.timeout_seconds)
        timeout_seconds = min(60, max(3, timeout_seconds))

        try:
            init_db(config.database.url)
            service = TelegramConfigService(database_url=config.database.url)
            if not enabled and not chat_id and not bot_token:
                service.delete()
            else:
                service.upsert(
                    enabled=bool(enabled and chat_id and bot_token),
                    chat_id=chat_id,
                    bot_token=bot_token,
                    timeout_seconds=timeout_seconds,
                )
        except Exception:
            pass

        return config.model_copy(update={"telegram": TelegramConfig()})

    def _hydrate_telegram_config(self, config: AppConfig) -> AppConfig:
        try:
            init_db(config.database.url)
            service = TelegramConfigService(database_url=config.database.url)
            telegram = service.get()
        except Exception:
            telegram = TelegramConfig()
        return config.model_copy(update={"telegram": telegram})
