from __future__ import annotations

import math
from typing import Any, Dict, List

from market_reporter.modules.analysis.agent.schemas import RuntimeDraft


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _coerce_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        output: List[str] = []
        for item in value:
            text = _coerce_text(item)
            if text:
                output.append(text)
        return output
    text = _coerce_text(value)
    return [text] if text else []


def _coerce_text_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    output: Dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _coerce_text(raw_key)
        text = _coerce_text(raw_value)
        if key and text:
            output[key] = text
    return output


def _extract_confidence_candidate(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, str):
        text = value.strip().rstrip("%")
        if not text:
            return None
        try:
            result = float(text)
        except ValueError:
            return None
        return result if math.isfinite(result) else None
    if isinstance(value, dict):
        for key in ("confidence", "value", "score", "probability"):
            if key not in value:
                continue
            result = _extract_confidence_candidate(value.get(key))
            if result is not None:
                return result
    return None


def coerce_confidence(value: Any, default: float = 0.5) -> float:
    result = _extract_confidence_candidate(value)
    if result is None:
        return default
    if result > 1.0 and result <= 100.0:
        result /= 100.0
    if result < 0.0:
        return 0.0
    if result > 1.0:
        return 1.0
    return result


def runtime_draft_from_payload(
    payload: Dict[str, Any],
    *,
    default_confidence: float = 0.5,
) -> RuntimeDraft:
    data = payload if isinstance(payload, dict) else {}
    return RuntimeDraft.model_validate(
        {
            "summary": _coerce_text(data.get("summary")),
            "sentiment": _coerce_text(data.get("sentiment"), "neutral"),
            "key_levels": _coerce_text_list(data.get("key_levels")),
            "risks": _coerce_text_list(data.get("risks")),
            "action_items": _coerce_text_list(data.get("action_items")),
            "confidence": coerce_confidence(
                data.get("confidence"),
                default=default_confidence,
            ),
            "conclusions": _coerce_text_list(data.get("conclusions")),
            "scenario_assumptions": _coerce_text_map(
                data.get("scenario_assumptions")
            ),
            "markdown": _coerce_text(data.get("markdown")),
            "raw": data,
        }
    )
