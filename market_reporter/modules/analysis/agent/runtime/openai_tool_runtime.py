from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft, ToolCallTrace

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class OpenAIToolRuntime:
    def __init__(
        self,
        provider_config: AnalysisProviderConfig,
        api_key: str,
    ) -> None:
        self.provider_config = provider_config
        self.api_key = api_key

    async def run(
        self,
        model: str,
        question: str,
        mode: str,
        context: Dict[str, Any],
        tool_specs: List[Dict[str, Any]],
        tool_executor: ToolExecutor,
        max_steps: int,
        max_tool_calls: int,
    ) -> Tuple[RuntimeDraft, List[ToolCallTrace]]:
        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.provider_config.base_url,
            timeout=self.provider_config.timeout,
        )

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a financial analysis orchestrator. "
                    "Use tools for any numeric claims. "
                    "Return final answer as JSON with keys: "
                    "summary,sentiment,key_levels,risks,action_items,confidence,conclusions,"
                    "scenario_assumptions,markdown."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "mode": mode,
                        "question": question,
                        "context": context,
                        "requirements": {
                            "must_cite_evidence": True,
                            "no_fabrication": True,
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        traces: List[ToolCallTrace] = []
        used_calls = 0
        content_text = ""
        for _ in range(max_steps):
            response = await client.chat.completions.create(
                model=model,
                temperature=0.1,
                messages=messages,
                tools=tool_specs,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls and used_calls < max_tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [call.model_dump() for call in tool_calls],
                    }
                )
                for call in tool_calls:
                    if used_calls >= max_tool_calls:
                        break
                    name = call.function.name
                    raw_args = call.function.arguments or "{}"
                    try:
                        arguments = json.loads(raw_args)
                    except Exception:
                        arguments = {}
                    result = await tool_executor(name, arguments)
                    used_calls += 1
                    traces.append(
                        ToolCallTrace(
                            tool=name,
                            arguments=arguments,
                            result_preview=self._preview_result(result),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                continue

            content_text = (msg.content or "").strip()
            break

        structured = parse_json(content_text)
        if structured is None:
            structured = {
                "summary": content_text[:240]
                if content_text
                else "模型未返回结构化内容。",
                "sentiment": "neutral",
                "key_levels": [],
                "risks": [],
                "action_items": [],
                "confidence": 0.4,
                "conclusions": [],
                "scenario_assumptions": {},
                "markdown": content_text or "模型未返回可读内容。",
            }

        draft = RuntimeDraft.model_validate(
            {
                "summary": structured.get("summary", ""),
                "sentiment": structured.get("sentiment", "neutral"),
                "key_levels": structured.get("key_levels", []),
                "risks": structured.get("risks", []),
                "action_items": structured.get("action_items", []),
                "confidence": float(structured.get("confidence", 0.5)),
                "conclusions": structured.get("conclusions", []),
                "scenario_assumptions": structured.get("scenario_assumptions", {}),
                "markdown": structured.get("markdown", ""),
                "raw": structured,
            }
        )
        return draft, traces

    @staticmethod
    def _preview_result(result: Dict[str, Any]) -> Dict[str, Any]:
        preview = dict(result)
        for key in ("bars", "items", "points", "rows", "filings"):
            value = preview.get(key)
            if isinstance(value, list) and len(value) > 3:
                preview[key] = value[:3]
                preview[f"{key}_count"] = len(value)
        return preview
