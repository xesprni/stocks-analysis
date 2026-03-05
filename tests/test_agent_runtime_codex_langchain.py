from __future__ import annotations

import asyncio
import unittest
from typing import Any, cast

from market_reporter.modules.analysis.agent.runtime.codex_langchain_runtime import (
    CodexLangChainRuntime,
)


class _FakeCodexProvider:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete_text(self, prompt, model, system_prompt="", access_token=None):
        del prompt, model, system_prompt, access_token
        if not self._responses:
            return '{"action":"final","final":{"summary":"done"}}'
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class CodexLangChainRuntimeTest(unittest.TestCase):
    def test_model_timeout_retries_then_succeeds(self):
        provider = _FakeCodexProvider(
            responses=[
                TimeoutError("Request timed out."),
                '{"action":"final","final":{"summary":"ok-after-timeout","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}}',
            ]
        )
        runtime = CodexLangChainRuntime(provider=cast(Any, provider))

        async def executor(tool, args):
            del tool, args
            return {"ok": True}

        async def scenario():
            return await runtime.run(
                model="test-model",
                question="analyze",
                mode="stock",
                context={"x": 1},
                tool_specs=[],
                tool_executor=executor,
                max_steps=3,
                max_tool_calls=3,
            )

        draft, traces = asyncio.run(scenario())
        self.assertEqual(draft.summary, "ok-after-timeout")
        self.assertEqual(len(traces), 0)

    def test_runtime_calls_tool_then_returns_final(self):
        provider = _FakeCodexProvider(
            responses=[
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"final","final":{"summary":"ok","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.7,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}}',
            ]
        )
        runtime = CodexLangChainRuntime(provider=cast(Any, provider))

        async def executor(tool, args):
            self.assertEqual(tool, "search_news")
            self.assertEqual(args.get("query"), "AAPL")
            return {
                "as_of": "2026-03-02",
                "source": "rss",
                "items": [{"title": "x"}],
            }

        async def scenario():
            draft, traces = await runtime.run(
                model="test-model",
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
            return draft, traces

        draft, traces = asyncio.run(scenario())
        self.assertEqual(draft.summary, "ok")
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].tool, "search_news")

    def test_runtime_tool_error_does_not_abort_loop(self):
        provider = _FakeCodexProvider(
            responses=[
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"final","final":{"summary":"ok-after-error","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}}',
            ]
        )
        runtime = CodexLangChainRuntime(provider=cast(Any, provider))

        async def executor(tool, args):
            del tool, args
            raise RuntimeError("tool boom")

        async def scenario():
            return await runtime.run(
                model="test-model",
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

        draft, traces = asyncio.run(scenario())
        self.assertEqual(draft.summary, "ok-after-error")
        self.assertEqual(len(traces), 1)
        warnings = traces[0].result_preview.get("warnings") or []
        self.assertTrue(isinstance(warnings, list) and warnings)
        self.assertIn("tool_execution_error", str(warnings[0]))

    def test_runtime_limits_repeated_same_failing_call(self):
        provider = _FakeCodexProvider(
            responses=[
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"final","final":{"summary":"ok","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.6,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}}',
            ]
        )
        runtime = CodexLangChainRuntime(provider=cast(Any, provider))

        state = {"calls": 0}

        async def executor(tool, args):
            del tool, args
            state["calls"] += 1
            raise ValueError("bad args")

        async def scenario():
            return await runtime.run(
                model="test-model",
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

        draft, traces = asyncio.run(scenario())
        self.assertEqual(draft.summary, "ok")
        self.assertEqual(state["calls"], 2)
        self.assertEqual(len(traces), 3)
        warnings = traces[2].result_preview.get("warnings") or []
        self.assertIn("tool_retry_limit_exceeded", warnings)


if __name__ == "__main__":
    unittest.main()
