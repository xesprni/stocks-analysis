from __future__ import annotations

from typing import Optional

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.agent.runtime.action_json_runtime import ActionJSONRuntime
from market_reporter.modules.agent.runtime.openai_tool_runtime import OpenAIToolRuntime


class AgentRuntimeFactory:
    @staticmethod
    def create_runtime(
        provider_cfg: AnalysisProviderConfig,
        registry: ProviderRegistry,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        lowered_id = (provider_cfg.provider_id or "").strip().lower()
        lowered_type = (provider_cfg.type or "").strip().lower()

        if lowered_id == "cc" or lowered_type == "cc":
            raise NotImplementedError("not_implemented:cc")

        if lowered_type == "openai_compatible":
            if not api_key:
                raise ValueError("API key is required for openai tool runtime")
            return OpenAIToolRuntime(provider_config=provider_cfg, api_key=api_key)

        if lowered_type == "codex_app_server":
            provider = registry.resolve(
                "analysis",
                provider_cfg.type,
                provider_config=provider_cfg,
            )
            return ActionJSONRuntime(provider=provider, access_token=access_token)

        # Fallback to action-json protocol for unknown providers that can return text.
        provider = registry.resolve(
            "analysis",
            provider_cfg.type,
            provider_config=provider_cfg,
        )
        return ActionJSONRuntime(provider=provider, access_token=access_token)
