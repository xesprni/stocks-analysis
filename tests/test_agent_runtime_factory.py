from __future__ import annotations

import unittest

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.analysis.agent.runtime.codex_langchain_runtime import (
    CodexLangChainRuntime,
)
from market_reporter.modules.analysis.agent.runtime.factory import AgentRuntimeFactory


class _DummyCodexProvider:
    async def complete_text(self, prompt, model, system_prompt="", access_token=None):
        del prompt, model, system_prompt, access_token
        return "{}"


class AgentRuntimeFactoryTest(unittest.TestCase):
    def test_codex_provider_uses_langchain_runtime(self):
        registry = ProviderRegistry()
        registry.register(
            "analysis", "codex_app_server", lambda **kwargs: _DummyCodexProvider()
        )

        cfg = AnalysisProviderConfig(
            provider_id="codex_app_server",
            type="codex_app_server",
            base_url="",
            models=["gpt-5-codex"],
            timeout=30,
            enabled=True,
            auth_mode="chatgpt_oauth",
        )

        runtime = AgentRuntimeFactory.create_runtime(
            provider_cfg=cfg,
            registry=registry,
            api_key=None,
            access_token="token",
        )
        self.assertIsInstance(runtime, CodexLangChainRuntime)


if __name__ == "__main__":
    unittest.main()
