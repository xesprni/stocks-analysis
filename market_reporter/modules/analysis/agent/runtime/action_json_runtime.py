from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft, ToolCallTrace
from market_reporter.modules.analysis.providers.codex_app_server_provider import (
    CodexAppServerProvider,
)

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class ActionJSONRuntime:
    def __init__(
        self,
        provider: CodexAppServerProvider,
        access_token: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.access_token = access_token

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
        traces: List[ToolCallTrace] = []
        observations: List[Dict[str, Any]] = []
        used_calls = 0

        for step in range(max_steps):
            instruction = {
                "protocol": "action_json_v1",
                "task": {
                    "mode": mode,
                    "question": question,
                },
                "tools": [item.get("function", {}).get("name") for item in tool_specs],
                "context": context,
                "observations": observations[-8:],
                "requirements": {
                    "json_only": True,
                    "must_use_tools_for_numbers": True,
                    "action_schema": {
                        "action": "call_tool|final",
                        "tool": "string",
                        "arguments": "object",
                        "final": {
                            "summary": "string",
                            "sentiment": "bullish|neutral|bearish",
                            "key_levels": ["string"],
                            "risks": ["string"],
                            "action_items": ["string"],
                            "confidence": "number",
                            "conclusions": ["string"],
                            "scenario_assumptions": {
                                "base": "",
                                "bull": "",
                                "bear": "",
                            },
                            "markdown": "string",
                        },
                    },
                },
            }
            response_text = await self.provider.complete_text(
                prompt=json.dumps(instruction, ensure_ascii=False),
                model=model,
                system_prompt=(
                    "Respond with pure JSON only. "
                    "Either request a tool call or return final structured result."
                ),
                access_token=self.access_token,
            )
            parsed = parse_json(response_text)
            if not isinstance(parsed, dict):
                break

            action = str(parsed.get("action") or "").strip().lower()
            if action == "call_tool" and used_calls < max_tool_calls:
                tool = str(parsed.get("tool") or "").strip()
                arguments = parsed.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                result = await tool_executor(tool, arguments)
                traces.append(
                    ToolCallTrace(
                        tool=tool,
                        arguments=arguments,
                        result_preview=self._preview_result(result),
                    )
                )
                observations.append(
                    {
                        "step": step,
                        "tool": tool,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                used_calls += 1
                continue

            if action == "final":
                final_payload = parsed.get("final")
                if isinstance(final_payload, dict):
                    draft = self._to_draft(final_payload)
                    return draft, traces
                break

        return self._fallback_draft(context), traces

    @staticmethod
    def _to_draft(data: Dict[str, Any]) -> RuntimeDraft:
        return RuntimeDraft.model_validate(
            {
                "summary": data.get("summary", ""),
                "sentiment": data.get("sentiment", "neutral"),
                "key_levels": data.get("key_levels", []),
                "risks": data.get("risks", []),
                "action_items": data.get("action_items", []),
                "confidence": float(data.get("confidence", 0.5)),
                "conclusions": data.get("conclusions", []),
                "scenario_assumptions": data.get("scenario_assumptions", {}),
                "markdown": data.get("markdown", ""),
                "raw": data,
            }
        )

    @staticmethod
    def _fallback_draft(context: Dict[str, Any]) -> RuntimeDraft:
        conclusions = [
            "数据已完成结构化采集，建议结合关键风险项谨慎解读。",
            "当前为工具优先生成结果，模型结构化结论回退到本地模板。",
        ]
        return RuntimeDraft(
            summary="模型结构化输出不可用，已回退到本地摘要。",
            sentiment="neutral",
            confidence=0.35,
            conclusions=conclusions,
            key_levels=[],
            risks=["模型未返回完整 JSON"],
            action_items=["检查 provider 连接与模型可用性"],
            scenario_assumptions={
                "base": "维持当前基本面与波动水平",
                "bull": "盈利与估值同步改善",
                "bear": "盈利下修且风险溢价上升",
            },
            markdown=json.dumps(context, ensure_ascii=False)[:1500],
            raw={"fallback": True},
        )

    @staticmethod
    def _preview_result(result: Dict[str, Any]) -> Dict[str, Any]:
        preview = dict(result)
        for key in ("bars", "items", "points", "rows", "reports"):
            value = preview.get(key)
            if isinstance(value, list) and len(value) > 3:
                preview[key] = value[:3]
                preview[f"{key}_count"] = len(value)
        return preview
