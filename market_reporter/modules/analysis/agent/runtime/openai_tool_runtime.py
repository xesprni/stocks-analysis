from __future__ import annotations

import json
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.agent.runtime.payload_normalizer import (
    runtime_draft_from_payload,
)
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft, ToolCallTrace
from market_reporter.modules.analysis.prompt_builder import get_system_prompt_with_tools

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]

logger = logging.getLogger(__name__)


class OpenAIToolRuntime:
    MAX_RETRIES_PER_TOOL_SIGNATURE = 2
    MAX_MODEL_CALL_RETRIES = 2
    DEFAULT_WALL_TIMEOUT_SECONDS = 300  # 5 minutes hard cap

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
        skill_content: Optional[str] = None,
        on_step: Optional[Any] = None,
        wall_timeout_seconds: float = DEFAULT_WALL_TIMEOUT_SECONDS,
    ) -> Tuple[RuntimeDraft, List[ToolCallTrace]]:
        llm = ChatOpenAI(
            model=model,
            api_key=SecretStr(self.api_key),
            base_url=self.provider_config.base_url,
            timeout=self.provider_config.timeout,
            temperature=0.1,
        )
        llm_with_tools = llm.bind_tools(tool_specs, tool_choice="auto")

        messages: List[Any] = [
            SystemMessage(content=get_system_prompt_with_tools(tool_specs, skill_content=skill_content)),
            HumanMessage(
                content=json.dumps(
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
                )
            ),
        ]

        traces: List[ToolCallTrace] = []
        used_calls = 0
        content_text = ""
        structured: Dict[str, Any] | None = None
        tool_attempts: Dict[str, int] = {}
        wall_deadline = time.monotonic() + wall_timeout_seconds

        for step_idx in range(max_steps):
            # Wall-clock timeout check
            elapsed_total = time.monotonic() - (wall_deadline - wall_timeout_seconds)
            if time.monotonic() >= wall_deadline:
                logger.warning(
                    "Agent wall timeout (%.0fs) exceeded after step %d (%d tool calls)",
                    wall_timeout_seconds, step_idx, used_calls,
                )
                if not structured and traces:
                    structured = self._wall_timeout_payload(
                        elapsed_seconds=elapsed_total,
                        step=step_idx,
                        tool_calls=used_calls,
                    )
                break

            # Notify: model thinking
            if on_step is not None:
                try:
                    await on_step({
                        "tool": "__model_thinking__",
                        "arguments": {"step": step_idx + 1, "max_steps": max_steps},
                        "result_preview": {},
                        "status": "thinking",
                    })
                except Exception:
                    pass

            t_model_start = time.monotonic()
            response = await self._invoke_model_with_retry(
                llm_with_tools=llm_with_tools,
                messages=messages,
            )
            model_ms = int((time.monotonic() - t_model_start) * 1000)
            tool_calls = list(getattr(response, "tool_calls", []) or [])

            if tool_calls:
                if used_calls >= max_tool_calls:
                    structured = self._tool_budget_exhausted_payload(
                        tool_calls=tool_calls,
                        max_tool_calls=max_tool_calls,
                    )
                    break

                messages.append(response)
                for call in tool_calls:
                    if used_calls >= max_tool_calls:
                        break
                    name = str(call.get("name") or "").strip()
                    arguments = call.get("args")
                    if not isinstance(arguments, dict):
                        arguments = {}

                    attempt_key = self._tool_attempt_key(name=name, arguments=arguments)
                    seen = tool_attempts.get(attempt_key, 0)
                    tool_ms: int | None = None
                    if seen >= self.MAX_RETRIES_PER_TOOL_SIGNATURE:
                        result = self._tool_retry_limit_result(
                            name=name,
                            arguments=arguments,
                            attempts=seen,
                        )
                    else:
                        tool_attempts[attempt_key] = seen + 1
                        t_tool_start = time.monotonic()
                        try:
                            result = await tool_executor(name, arguments)
                        except Exception as exc:
                            result = self._tool_error_result(name=name, exc=exc)
                        tool_ms = int((time.monotonic() - t_tool_start) * 1000)
                    result = self._normalize_tool_result(name=name, result=result)
                    used_calls += 1
                    trace = ToolCallTrace(
                        tool=name,
                        arguments=arguments,
                        result_preview=self._preview_result(result),
                        duration_ms=tool_ms,
                    )
                    traces.append(trace)
                    if on_step is not None:
                        try:
                            await on_step(trace.model_dump())
                        except Exception:
                            pass
                    call_id = str(call.get("id") or f"tool_call_{used_calls}")
                    messages.append(
                        ToolMessage(
                            content=json.dumps(result, ensure_ascii=False),
                            tool_call_id=call_id,
                        )
                    )
                continue

            content_text = self._content_to_text(response.content)
            break

        if structured is None:
            structured = parse_json(content_text)
        if structured is None:
            structured = self._unstructured_content_payload(content_text)

        draft = runtime_draft_from_payload(structured)
        return draft, traces

    async def _invoke_model_with_retry(
        self,
        llm_with_tools: Any,
        messages: List[Any],
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.MAX_MODEL_CALL_RETRIES + 1):
            try:
                return await llm_with_tools.ainvoke(messages)
            except Exception as exc:
                last_error = exc
                if not self._is_timeout_error(exc):
                    raise
                if attempt >= self.MAX_MODEL_CALL_RETRIES:
                    break
                await asyncio.sleep(0.1 * (attempt + 1))

        if last_error is None:
            raise RuntimeError("Model invocation failed unexpectedly.")
        raise TimeoutError(
            f"Model request timed out after {self.MAX_MODEL_CALL_RETRIES + 1} attempts: {last_error}"
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
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
            return "\n".join(chunks).strip()
        return str(content or "").strip()

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
    def _tool_attempt_key(name: str, arguments: Dict[str, Any]) -> str:
        try:
            encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        except Exception:
            encoded = str(arguments)
        return f"{name.strip().lower()}::{encoded}"

    @staticmethod
    def _tool_error_result(name: str, exc: Exception) -> Dict[str, Any]:
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
            "tool": name,
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
        name: str,
        arguments: Dict[str, Any],
        attempts: int,
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "tool": name,
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
    def _normalize_tool_result(name: str, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "tool": name,
            "status": "error",
            "source": "tool_executor",
            "as_of": timestamp,
            "retrieved_at": timestamp,
            "warnings": ["tool_result_invalid"],
            "raw": result,
        }

    @staticmethod
    def _wall_timeout_payload(
        *,
        elapsed_seconds: float,
        step: int,
        tool_calls: int,
    ) -> Dict[str, Any]:
        summary = (
            f"Agent 执行超时（{elapsed_seconds:.0f}s），已完成 {step} 轮、{tool_calls} 次工具调用。"
            "以下报告基于已收集证据自动整理。"
        )
        return {
            "summary": summary,
            "sentiment": "neutral",
            "key_levels": [],
            "risks": ["Agent 执行超时，分析可能不完整。"],
            "action_items": ["检查 LLM provider 响应速度，或降低 max_steps。"],
            "confidence": 0.3,
            "conclusions": [summary],
            "scenario_assumptions": {},
            "markdown": summary,
            "wall_timeout": True,
        }

    @staticmethod
    def _unstructured_content_payload(content_text: str) -> Dict[str, Any]:
        text = content_text.strip()
        return {
            "summary": text[:240] if text else "模型未返回结构化内容。",
            "sentiment": "neutral",
            "key_levels": [],
            "risks": [],
            "action_items": [],
            "confidence": 0.4,
            "conclusions": [],
            "scenario_assumptions": {},
            "markdown": text or "模型未返回可读内容。",
            "raw_model_response": text,
            "parse_fallback": True,
        }

    @staticmethod
    def _tool_budget_exhausted_payload(
        *,
        tool_calls: List[Dict[str, Any]],
        max_tool_calls: int,
    ) -> Dict[str, Any]:
        requested_tools = [
            str(call.get("name") or "").strip()
            for call in tool_calls
            if str(call.get("name") or "").strip()
        ]
        deduped_tools = list(dict.fromkeys(requested_tools))
        summary = (
            f"已达到工具调用上限（{max_tool_calls} 次），"
            "以下报告基于已收集证据自动整理，模型未完成最终结构化归纳。"
        )
        action_items = ["减少重复工具调用，必要时适度提高 max_tool_calls。"]
        if deduped_tools:
            action_items.append(
                "达到上限后模型仍请求工具: " + ", ".join(deduped_tools[:4])
            )
        return {
            "summary": summary,
            "sentiment": "neutral",
            "key_levels": [],
            "risks": ["模型在达到工具调用上限后仍请求更多工具。"],
            "action_items": action_items,
            "confidence": 0.4,
            "conclusions": [summary],
            "scenario_assumptions": {},
            "markdown": "模型在达到工具调用上限后未返回最终结构化结论。",
            "tool_budget_exhausted": True,
            "requested_tools_after_limit": deduped_tools,
        }
