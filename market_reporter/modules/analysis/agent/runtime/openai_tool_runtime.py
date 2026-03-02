from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft, ToolCallTrace

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class OpenAIToolRuntime:
    MAX_RETRIES_PER_TOOL_SIGNATURE = 2

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
        llm = ChatOpenAI(
            model=model,
            api_key=SecretStr(self.api_key),
            base_url=self.provider_config.base_url,
            timeout=self.provider_config.timeout,
            temperature=0.1,
        )
        llm_with_tools = llm.bind_tools(tool_specs, tool_choice="auto")

        messages: List[Any] = [
            SystemMessage(
                content=(
                    "You are a financial analysis orchestrator. "
                    "Decide which registered tools to call based on the task and evidence needs. "
                    "Use the skill tool when you need detailed skill markdown content. "
                    "Use the subagent tool when you need specialized intermediate synthesis. "
                    "For numeric statements, rely on tool outputs. "
                    "Return final answer as JSON with keys: "
                    "summary,sentiment,key_levels,risks,action_items,confidence,"
                    "conclusions,scenario_assumptions,markdown."
                )
            ),
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
        tool_attempts: Dict[str, int] = {}

        for _ in range(max_steps):
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = list(getattr(response, "tool_calls", []) or [])

            if tool_calls and used_calls < max_tool_calls:
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
                    if seen >= self.MAX_RETRIES_PER_TOOL_SIGNATURE:
                        result = self._tool_retry_limit_result(
                            name=name,
                            arguments=arguments,
                            attempts=seen,
                        )
                    else:
                        tool_attempts[attempt_key] = seen + 1
                        try:
                            result = await tool_executor(name, arguments)
                        except Exception as exc:
                            result = self._tool_error_result(name=name, exc=exc)
                    result = self._normalize_tool_result(name=name, result=result)
                    used_calls += 1
                    traces.append(
                        ToolCallTrace(
                            tool=name,
                            arguments=arguments,
                            result_preview=self._preview_result(result),
                        )
                    )
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
