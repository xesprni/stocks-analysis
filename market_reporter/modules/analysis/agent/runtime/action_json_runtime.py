from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.agent.runtime.payload_normalizer import (
    runtime_draft_from_payload,
)
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft, ToolCallTrace
from market_reporter.modules.analysis.providers.codex_app_server_provider import (
    CodexAppServerProvider,
)

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class ActionJSONRuntime:
    MAX_RETRIES_PER_TOOL_SIGNATURE = 2
    MAX_MODEL_CALL_RETRIES = 2

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
        tool_attempts: Dict[str, int] = {}

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
            response_text = await self._complete_text_with_retry(
                prompt=json.dumps(instruction, ensure_ascii=False),
                model=model,
                system_prompt=(
                    "Respond with pure JSON only. "
                    "Either request a tool call or return final structured result."
                ),
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
                attempt_key = self._tool_attempt_key(tool=tool, arguments=arguments)
                seen = tool_attempts.get(attempt_key, 0)
                if seen >= self.MAX_RETRIES_PER_TOOL_SIGNATURE:
                    result = self._tool_retry_limit_result(
                        tool=tool,
                        arguments=arguments,
                        attempts=seen,
                    )
                else:
                    tool_attempts[attempt_key] = seen + 1
                    try:
                        result = await tool_executor(tool, arguments)
                    except Exception as exc:
                        result = self._tool_error_result(tool=tool, exc=exc)
                result = self._normalize_tool_result(tool=tool, result=result)
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

    async def _complete_text_with_retry(
        self,
        prompt: str,
        model: str,
        system_prompt: str,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self.MAX_MODEL_CALL_RETRIES + 1):
            try:
                return await self.provider.complete_text(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    access_token=self.access_token,
                )
            except Exception as exc:
                last_error = exc
                if not self._is_timeout_error(exc):
                    raise
                if attempt >= self.MAX_MODEL_CALL_RETRIES:
                    break
                await asyncio.sleep(0.1 * (attempt + 1))

        if last_error is None:
            raise RuntimeError("Provider request failed unexpectedly.")
        raise TimeoutError(
            f"Provider request timed out after {self.MAX_MODEL_CALL_RETRIES + 1} attempts: {last_error}"
        )

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return (
            "timeout" in name
            or "timed out" in message
            or "timeout" in message
            or "deadline exceeded" in message
        )

    @staticmethod
    def _to_draft(data: Dict[str, Any]) -> RuntimeDraft:
        return runtime_draft_from_payload(data)

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

    @staticmethod
    def _tool_attempt_key(tool: str, arguments: Dict[str, Any]) -> str:
        try:
            encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        except Exception:
            encoded = str(arguments)
        return f"{tool.strip().lower()}::{encoded}"

    @staticmethod
    def _tool_error_result(tool: str, exc: Exception) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        error_type = type(exc).__name__
        warning_code = "tool_execution_error"
        hint = "Inspect tool schema and arguments, then try a corrected call."
        if isinstance(exc, (ValueError, TypeError)):
            warning_code = "tool_argument_error"
            hint = (
                "Arguments likely violate tool schema; adjust required fields or types."
            )
        return {
            "tool": tool,
            "status": "error",
            "source": "tool_executor",
            "as_of": timestamp,
            "retrieved_at": timestamp,
            "warnings": [
                f"{warning_code}:{error_type}",
                str(exc),
            ],
            "error": {
                "type": error_type,
                "message": str(exc),
                "retryable": True,
                "hint": hint,
            },
        }

    @staticmethod
    def _tool_retry_limit_result(
        tool: str,
        arguments: Dict[str, Any],
        attempts: int,
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "tool": tool,
            "status": "error",
            "source": "tool_executor",
            "as_of": timestamp,
            "retrieved_at": timestamp,
            "warnings": ["tool_retry_limit_exceeded"],
            "error": {
                "type": "ToolRetryLimitExceeded",
                "message": (
                    "Same tool call failed repeatedly. "
                    "Change arguments or choose a different tool before retrying."
                ),
                "retryable": False,
                "max_attempts": attempts,
            },
            "arguments": arguments,
        }

    @staticmethod
    def _normalize_tool_result(tool: str, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "tool": tool,
            "status": "error",
            "source": "tool_executor",
            "as_of": timestamp,
            "retrieved_at": timestamp,
            "warnings": ["tool_result_invalid"],
            "raw": result,
        }
