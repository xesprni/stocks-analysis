from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from market_reporter.core.types import AnalysisInput


# ---------------------------------------------------------------------------
# System prompt sections
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = """\
You are a professional stock analysis assistant. You help users analyze stocks, market trends, \
financial data, and news for A-shares (CN), Hong Kong (HK), and US markets.

## Working Principles

1. **Data-driven**: Base all analysis on tool-returned data. Never fabricate numbers.
2. **Tool selection**: Choose appropriate tools based on the user's question. Fetch only what you need.
3. **Chinese output**: Provide analysis conclusions in Chinese.
4. **Fact vs opinion**: Clearly distinguish factual data from analytical opinions.
"""

_OUTPUT_FORMAT_SECTION = """
## Output Format

Return exactly one valid JSON object with these keys:
- "summary": One-sentence conclusion (in Chinese)
- "sentiment": "bullish" | "neutral" | "bearish"
- "key_levels": Array of key price levels or themes to watch
- "risks": Array of main risk factors
- "action_items": Array of actionable recommendations
- "confidence": Decimal between 0 and 1
- "conclusions": Array of detailed analytical conclusions
- "scenario_assumptions": Object with "base", "bull", "bear" scenario descriptions
- "markdown": Structured analysis report in Chinese markdown

Do NOT wrap output with markdown code fences. Return raw JSON only.
"""


# ---------------------------------------------------------------------------
# Dynamic prompt builders
# ---------------------------------------------------------------------------


def build_tools_section(tool_specs: Sequence[Dict[str, Any]]) -> str:
    """Build the Available Tools section dynamically from tool specifications."""
    if not tool_specs:
        return ""
    lines = ["\n## Available Tools\n", "You have access to the following tools:"]
    for spec in tool_specs:
        func = spec.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        lines.append(f"- **{name}**: {desc}")
        params = func.get("parameters", {}).get("properties", {})
        if params:
            for pname, pval in params.items():
                ptype = pval.get("type", "any")
                pdesc = pval.get("description", "")
                lines.append(f"  - `{pname}` ({ptype}): {pdesc}")
    return "\n".join(lines)


def build_system_prompt(
    tool_specs: Optional[Sequence[Dict[str, Any]]] = None,
    include_output_format: bool = True,
) -> str:
    """Build the complete system prompt with dynamic tools section.

    Args:
        tool_specs: Tool specifications from ToolRegistry.get_tool_specs().
            If None, the Available Tools section is omitted.
        include_output_format: Whether to include the output format section.
    """
    parts = [_BASE_SYSTEM_PROMPT]
    if tool_specs:
        parts.append(build_tools_section(tool_specs))
    if include_output_format:
        parts.append(_OUTPUT_FORMAT_SECTION)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt builder (user prompts)
# ---------------------------------------------------------------------------


def build_user_prompt(payload: AnalysisInput) -> str:
    """Build the user prompt for market overview / news alert triage."""
    if payload.watch_meta.get("mode") == "watchlist_news_listener":
        return _build_watchlist_listener_prompt(payload)
    return _build_analysis_prompt(payload)


def get_system_prompt(payload: AnalysisInput) -> str:
    """Return the system prompt for LLM-based analysis."""
    return build_system_prompt()


def get_system_prompt_text() -> str:
    """Return the system prompt text directly (without dynamic tools)."""
    return build_system_prompt()


def get_system_prompt_with_tools(
    tool_specs: Sequence[Dict[str, Any]],
) -> str:
    """Return the system prompt with dynamically generated tools section."""
    return build_system_prompt(tool_specs=tool_specs)


# ---------------------------------------------------------------------------
# User prompt builders
# ---------------------------------------------------------------------------


def _build_watchlist_listener_prompt(payload: AnalysisInput) -> str:
    request_json = {
        "task": "对以下新闻告警候选进行专业分析，评估其市场影响。",
        "analysis_mode": "watchlist_news_listener",
        "candidates": payload.watch_meta.get("candidates", []),
        "required_output": payload.watch_meta.get("required_output", {}),
        "analysis_instructions": [
            "对每条新闻评估其对相关股票的影响程度和紧急性。",
            "结合市场环境判断新闻的实际影响力。",
            "给出severity评级：LOW/MEDIUM/HIGH。",
            "只返回JSON对象。",
        ],
    }
    return json.dumps(request_json, ensure_ascii=False)


def _build_analysis_prompt(payload: AnalysisInput) -> str:
    news_digest = _categorize_news(payload.news[:50])
    fund_flow: Dict[str, list] = {
        key: [point.model_dump(mode="json") for point in value[-12:]]
        for key, value in payload.fund_flow.items()
    }

    request_json = {
        "task": payload.watch_meta.get("question", "请综合分析当前市场形势。"),
        "data": {
            "news_digest": news_digest,
            "fund_flow": fund_flow,
            "fund_flow_summary": _summarize_fund_flow(payload),
            "watch_meta": payload.watch_meta,
        },
    }
    return json.dumps(request_json, ensure_ascii=False)


# ---------------------------------------------------------------------------
# News categorization helpers
# ---------------------------------------------------------------------------


def _categorize_news(news_items: list) -> Dict[str, list]:
    """Categorize news items by type for structured analysis."""
    categories: Dict[str, list] = {
        "macro_policy": [],
        "market_data": [],
        "company_sector": [],
        "geopolitical": [],
        "other": [],
    }

    macro_keywords = {
        "央行", "利率", "降息", "加息", "GDP", "CPI", "PMI",
        "货币政策", "财政", "fed", "pboc", "interest rate",
        "inflation", "monetary", "fiscal", "就业", "失业",
        "贸易", "关税", "汇率", "美联储", "国务院",
    }
    geo_keywords = {
        "战争", "制裁", "冲突", "地缘", "military",
        "sanction", "war", "tension", "选举", "election",
        "政变", "外交",
    }

    for item in news_items:
        title_lower = (item.title or "").lower()
        category_lower = (item.category or "").lower()
        entry = {
            "source": item.source,
            "category": item.category,
            "published": item.published,
            "title": item.title[:200],
        }

        if any(kw in title_lower for kw in macro_keywords):
            categories["macro_policy"].append(entry)
        elif any(kw in title_lower for kw in geo_keywords):
            categories["geopolitical"].append(entry)
        elif category_lower in ("market", "data", "经济数据", "行情"):
            categories["market_data"].append(entry)
        elif category_lower in ("company", "sector", "industry", "个股", "行业"):
            categories["company_sector"].append(entry)
        else:
            categories["other"].append(entry)

    return {k: v for k, v in categories.items() if v}


def _summarize_fund_flow(payload: AnalysisInput) -> Dict[str, object]:
    """Summarize fund flow trends across all series."""
    if not payload.fund_flow:
        return {}

    summary: Dict[str, object] = {}
    for key, points in payload.fund_flow.items():
        if not points:
            continue
        recent = points[-6:]
        values = []
        for p in recent:
            val = getattr(p, "value", None) or getattr(p, "amount", None)
            if val is not None:
                values.append(float(val))

        if not values:
            continue

        net_direction = (
            "inflow" if sum(values) > 0 else "outflow" if sum(values) < 0 else "neutral"
        )
        trend = "unknown"
        if len(values) >= 3:
            first_half = sum(values[: len(values) // 2])
            second_half = sum(values[len(values) // 2 :])
            if second_half > first_half * 1.2:
                trend = "accelerating_inflow"
            elif second_half < first_half * 0.8:
                trend = "decelerating" if second_half > 0 else "accelerating_outflow"
            else:
                trend = "stable"

        summary[key] = {
            "recent_periods": len(values),
            "net_direction": net_direction,
            "trend": trend,
            "total": round(sum(values), 2),
        }

    return summary
