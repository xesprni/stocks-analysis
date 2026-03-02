from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SubAgentSummary:
    name: str
    description: str


class SubAgentRegistry:
    def __init__(self, subagents: Optional[List[SubAgentSummary]] = None) -> None:
        defaults = subagents or [
            SubAgentSummary(
                name="technical_reviewer",
                description="Extract trend, momentum, and key levels from indicator payloads.",
            ),
            SubAgentSummary(
                name="risk_reviewer",
                description="Summarize major downside scenarios and risk controls.",
            ),
            SubAgentSummary(
                name="macro_reviewer",
                description="Summarize macro/news catalysts and cross-market drivers.",
            ),
        ]
        self._subagents = {item.name.lower(): item for item in defaults}

    def list_subagents(self) -> List[SubAgentSummary]:
        return sorted(self._subagents.values(), key=lambda item: item.name)

    async def run(
        self,
        name: str,
        task: str,
        context: Dict[str, Any],
        tool_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        key = (name or "").strip().lower()
        summary = self._subagents.get(key)
        if summary is None:
            return {
                "name": name,
                "task": task,
                "status": "not_found",
                "output": "Unknown subagent.",
                "available": [item.name for item in self.list_subagents()],
            }

        if key == "technical_reviewer":
            return self._technical_review(
                summary=summary, task=task, tool_results=tool_results
            )
        if key == "risk_reviewer":
            return self._risk_review(
                summary=summary, task=task, tool_results=tool_results
            )
        if key == "macro_reviewer":
            return self._macro_review(
                summary=summary,
                task=task,
                context=context,
                tool_results=tool_results,
            )

        return {
            "name": summary.name,
            "task": task,
            "status": "ok",
            "output": summary.description,
        }

    @staticmethod
    def _technical_review(
        summary: SubAgentSummary,
        task: str,
        tool_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        indicators = tool_results.get("compute_indicators", {})
        strategy = indicators.get("strategy") if isinstance(indicators, dict) else {}
        trend = indicators.get("trend") if isinstance(indicators, dict) else {}
        primary_trend = trend.get("primary") if isinstance(trend, dict) else {}
        ma_state = (
            (primary_trend.get("ma") or {}).get("state")
            if isinstance(primary_trend, dict)
            else "unknown"
        )
        stance = strategy.get("stance") if isinstance(strategy, dict) else "neutral"
        score = strategy.get("score") if isinstance(strategy, dict) else None
        output = (
            f"task={task or 'technical review'}; "
            f"ma_state={ma_state}; stance={stance}; score={score}"
        )
        return {
            "name": summary.name,
            "task": task,
            "status": "ok",
            "output": output,
        }

    @staticmethod
    def _risk_review(
        summary: SubAgentSummary,
        task: str,
        tool_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        warnings: List[str] = []
        for payload in tool_results.values():
            if not isinstance(payload, dict):
                continue
            row_warnings = payload.get("warnings")
            if isinstance(row_warnings, list):
                warnings.extend(
                    [str(item) for item in row_warnings if str(item).strip()]
                )
        warnings = list(dict.fromkeys(warnings))
        output = (
            f"task={task or 'risk review'}; "
            f"warnings_count={len(warnings)}; top_warnings={warnings[:5]}"
        )
        return {
            "name": summary.name,
            "task": task,
            "status": "ok",
            "output": output,
            "warnings": warnings,
        }

    @staticmethod
    def _macro_review(
        summary: SubAgentSummary,
        task: str,
        context: Dict[str, Any],
        tool_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        market = str(context.get("market") or "").upper()
        news_items = 0
        macro_points = 0

        news_payload = tool_results.get("search_news")
        if isinstance(news_payload, dict) and isinstance(
            news_payload.get("items"), list
        ):
            news_items = len(news_payload.get("items") or [])

        macro_payload = tool_results.get("get_macro_data")
        if isinstance(macro_payload, dict) and isinstance(
            macro_payload.get("points"), list
        ):
            macro_points = len(macro_payload.get("points") or [])

        output = (
            f"task={task or 'macro review'}; market={market or 'GLOBAL'}; "
            f"news_items={news_items}; macro_points={macro_points}"
        )
        return {
            "name": summary.name,
            "task": task,
            "status": "ok",
            "output": output,
        }
