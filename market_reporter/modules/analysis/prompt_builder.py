from __future__ import annotations

from typing import Any, Dict, Optional, Sequence


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
    skill_content: Optional[str] = None,
) -> str:
    """Build the complete system prompt with dynamic tools section."""
    parts = [_BASE_SYSTEM_PROMPT]
    if tool_specs:
        parts.append(build_tools_section(tool_specs))
    if include_output_format:
        parts.append(_OUTPUT_FORMAT_SECTION)
    if skill_content and skill_content.strip():
        parts.append(f"\n## Skill Instructions\n\n{skill_content.strip()}")
    return "\n".join(parts)


def get_system_prompt_with_tools(
    tool_specs: Sequence[Dict[str, Any]],
    skill_content: Optional[str] = None,
) -> str:
    """Return the system prompt with dynamically generated tools section."""
    return build_system_prompt(tool_specs=tool_specs, skill_content=skill_content)
