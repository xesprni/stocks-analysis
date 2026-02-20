"""Shared utility functions used across multiple modules."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def parse_json(content: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON string into a dict, recovering embedded JSON from mixed text.

    Returns ``None`` when *content* is empty, not valid JSON, or does not
    decode to a ``dict``.  When the raw string contains prose around a JSON
    object the function attempts to extract the outermost ``{…}`` substring.
    """
    if not content:
        return None
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None
