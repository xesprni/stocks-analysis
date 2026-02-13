import asyncio
import unittest

from market_reporter.modules.agent.runtime.action_json_runtime import ActionJSONRuntime


class _FakeProvider:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete_text(self, prompt, model, system_prompt="", access_token=None):
        del prompt, model, system_prompt, access_token
        if not self._responses:
            return '{"action":"final","final":{"summary":"done"}}'
        return self._responses.pop(0)


class ActionJSONRuntimeTest(unittest.TestCase):
    def test_runtime_calls_tool_then_returns_final(self):
        provider = _FakeProvider(
            responses=[
                '{"action":"call_tool","tool":"search_news","arguments":{"query":"AAPL"}}',
                '{"action":"final","final":{"summary":"ok","sentiment":"neutral","key_levels":[],"risks":[],"action_items":[],"confidence":0.7,"conclusions":["结论 [E1]"],"scenario_assumptions":{"base":"b","bull":"u","bear":"d"},"markdown":"m"}}',
            ]
        )
        runtime = ActionJSONRuntime(provider=provider)

        async def executor(tool, args):
            self.assertEqual(tool, "search_news")
            self.assertEqual(args.get("query"), "AAPL")
            return {
                "as_of": "2026-02-13",
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


if __name__ == "__main__":
    unittest.main()
