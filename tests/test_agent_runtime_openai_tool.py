from __future__ import annotations

import asyncio
import unittest

from market_reporter.config import AnalysisProviderConfig
from market_reporter.modules.analysis.agent.runtime import openai_tool_runtime
from market_reporter.modules.analysis.agent.runtime.openai_tool_runtime import (
    OpenAIToolRuntime,
)


class _FakeAIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = list(tool_calls or [])


class _FakeChatOpenAI:
    queued_responses = []

    def __init__(self, **kwargs):
        del kwargs

    def bind_tools(self, tool_specs, tool_choice="auto"):
        del tool_specs, tool_choice
        return self

    async def ainvoke(self, messages):
        del messages
        if not self.queued_responses:
            return _FakeAIMessage(
                content='{"summary":"done","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.5,"conclusions":[],"scenario_assumptions":{},"markdown":"m"}'
            )
        response = self.queued_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OpenAIToolRuntimeTest(unittest.TestCase):
    def test_model_timeout_retries_then_succeeds(self):
        provider_cfg = AnalysisProviderConfig(
            provider_id="openai",
            type="openai_compatible",
            base_url="https://example.com/v1",
            models=["gpt-test"],
            timeout=10,
            enabled=True,
            auth_mode="api_key",
        )

        original_cls = openai_tool_runtime.ChatOpenAI
        _FakeChatOpenAI.queued_responses = [
            TimeoutError("Request timed out."),
            _FakeAIMessage(
                content='{"summary":"ok-after-timeout","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}'
            ),
        ]
        openai_tool_runtime.ChatOpenAI = _FakeChatOpenAI

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key="test-key")

        async def executor(tool, arguments):
            del tool, arguments
            return {"ok": True}

        async def scenario():
            return await runtime.run(
                model="gpt-test",
                question="analyze",
                mode="stock",
                context={"x": 1},
                tool_specs=[],
                tool_executor=executor,
                max_steps=2,
                max_tool_calls=2,
            )

        try:
            draft, traces = asyncio.run(scenario())
        finally:
            openai_tool_runtime.ChatOpenAI = original_cls

        self.assertEqual(draft.summary, "ok-after-timeout")
        self.assertEqual(len(traces), 0)

    def test_tool_error_does_not_abort_runtime(self):
        provider_cfg = AnalysisProviderConfig(
            provider_id="openai",
            type="openai_compatible",
            base_url="https://example.com/v1",
            models=["gpt-test"],
            timeout=10,
            enabled=True,
            auth_mode="api_key",
        )

        original_cls = openai_tool_runtime.ChatOpenAI
        _FakeChatOpenAI.queued_responses = [
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_1",
                        "name": "search_news",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                content='{"summary":"ok-after-error","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}'
            ),
        ]
        openai_tool_runtime.ChatOpenAI = _FakeChatOpenAI

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key="test-key")

        async def executor(tool, arguments):
            del tool, arguments
            raise RuntimeError("tool boom")

        async def scenario():
            return await runtime.run(
                model="gpt-test",
                question="analyze",
                mode="stock",
                context={"x": 1},
                tool_specs=[
                    {
                        "type": "function",
                        "function": {"name": "search_news"},
                    }
                ],
                tool_executor=executor,
                max_steps=4,
                max_tool_calls=4,
            )

        try:
            draft, traces = asyncio.run(scenario())
        finally:
            openai_tool_runtime.ChatOpenAI = original_cls

        self.assertEqual(draft.summary, "ok-after-error")
        self.assertEqual(len(traces), 1)
        warnings = traces[0].result_preview.get("warnings") or []
        self.assertTrue(isinstance(warnings, list) and warnings)
        self.assertIn("tool_execution_error", str(warnings[0]))

    def test_runtime_limits_repeated_same_failing_call(self):
        provider_cfg = AnalysisProviderConfig(
            provider_id="openai",
            type="openai_compatible",
            base_url="https://example.com/v1",
            models=["gpt-test"],
            timeout=10,
            enabled=True,
            auth_mode="api_key",
        )

        original_cls = openai_tool_runtime.ChatOpenAI
        _FakeChatOpenAI.queued_responses = [
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_1",
                        "name": "search_news",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_2",
                        "name": "search_news",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_3",
                        "name": "search_news",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                content='{"summary":"ok","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}'
            ),
        ]
        openai_tool_runtime.ChatOpenAI = _FakeChatOpenAI

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key="test-key")
        state = {"calls": 0}

        async def executor(tool, arguments):
            del tool, arguments
            state["calls"] += 1
            raise ValueError("bad args")

        async def scenario():
            return await runtime.run(
                model="gpt-test",
                question="analyze",
                mode="stock",
                context={"x": 1},
                tool_specs=[
                    {
                        "type": "function",
                        "function": {"name": "search_news"},
                    }
                ],
                tool_executor=executor,
                max_steps=6,
                max_tool_calls=6,
            )

        try:
            draft, traces = asyncio.run(scenario())
        finally:
            openai_tool_runtime.ChatOpenAI = original_cls

        self.assertEqual(draft.summary, "ok")
        self.assertEqual(state["calls"], 2)
        self.assertEqual(len(traces), 3)
        warnings = traces[2].result_preview.get("warnings") or []
        self.assertIn("tool_retry_limit_exceeded", warnings)

    def test_runtime_reports_tool_budget_exhaustion(self):
        provider_cfg = AnalysisProviderConfig(
            provider_id="openai",
            type="openai_compatible",
            base_url="https://example.com/v1",
            models=["gpt-test"],
            timeout=10,
            enabled=True,
            auth_mode="api_key",
        )

        original_cls = openai_tool_runtime.ChatOpenAI
        _FakeChatOpenAI.queued_responses = [
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_1",
                        "name": "search_news",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_2",
                        "name": "search_web",
                        "args": {"query": "AAPL"},
                    }
                ]
            ),
            _FakeAIMessage(
                tool_calls=[
                    {
                        "id": "tool_call_3",
                        "name": "get_macro_data",
                        "args": {"market": "US"},
                    }
                ]
            ),
        ]
        openai_tool_runtime.ChatOpenAI = _FakeChatOpenAI

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key="test-key")

        async def executor(tool, arguments):
            return {"tool": tool, "arguments": arguments, "warnings": []}

        async def scenario():
            return await runtime.run(
                model="gpt-test",
                question="analyze",
                mode="market",
                context={"x": 1},
                tool_specs=[
                    {"type": "function", "function": {"name": "search_news"}},
                    {"type": "function", "function": {"name": "search_web"}},
                    {"type": "function", "function": {"name": "get_macro_data"}},
                ],
                tool_executor=executor,
                max_steps=5,
                max_tool_calls=2,
            )

        try:
            draft, traces = asyncio.run(scenario())
        finally:
            openai_tool_runtime.ChatOpenAI = original_cls

        self.assertEqual(len(traces), 2)
        self.assertIn("工具调用上限", draft.summary)
        self.assertIn("未完成最终结构化归纳", draft.summary)

    def test_runtime_coerces_mapping_confidence(self):
        provider_cfg = AnalysisProviderConfig(
            provider_id="openai",
            type="openai_compatible",
            base_url="https://example.com/v1",
            models=["gpt-test"],
            timeout=10,
            enabled=True,
            auth_mode="api_key",
        )

        original_cls = openai_tool_runtime.ChatOpenAI
        _FakeChatOpenAI.queued_responses = [
            _FakeAIMessage(
                content='{"summary":"coerced","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":{"score":80},"conclusions":[],"scenario_assumptions":{},"markdown":"m"}'
            )
        ]
        openai_tool_runtime.ChatOpenAI = _FakeChatOpenAI

        runtime = OpenAIToolRuntime(provider_config=provider_cfg, api_key="test-key")

        async def executor(tool, arguments):
            del tool, arguments
            return {"ok": True}

        async def scenario():
            return await runtime.run(
                model="gpt-test",
                question="analyze",
                mode="stock",
                context={"x": 1},
                tool_specs=[],
                tool_executor=executor,
                max_steps=2,
                max_tool_calls=2,
            )

        try:
            draft, _ = asyncio.run(scenario())
        finally:
            openai_tool_runtime.ChatOpenAI = original_cls

        self.assertEqual(draft.summary, "coerced")
        self.assertAlmostEqual(draft.confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
