from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Protocol, Sequence, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.infra.db.session import init_db
from market_reporter.modules.analysis.agent.schemas import AgentRunRequest
from market_reporter.modules.analysis.agent.service import AgentService
from market_reporter.modules.analysis.agent.skill_catalog import SkillCatalog
from market_reporter.modules.watchlist.schemas import WatchlistItem
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.schemas import RunRequest


@dataclass
class ReportSkillContext:
    config: AppConfig
    overrides: Optional[RunRequest]
    generated_at: str
    agent_service: AgentService
    provider_cfg: AnalysisProviderConfig
    selected_model: str
    api_key: Optional[str]
    skill_content: str = ""
    on_step: Optional[Any] = None


@dataclass
class ReportSkillResult:
    markdown: str
    analysis_payload: Dict[str, object]
    news_total: int
    warnings: List[str]
    mode: str
    skill_id: str


class ReportSkill(Protocol):
    skill_id: str
    mode: str
    aliases: Sequence[str]

    async def run(self, context: ReportSkillContext) -> ReportSkillResult: ...


class CatalogReportSkill:
    """Report skill loaded from a SKILL.md file in the SkillCatalog."""

    def __init__(
        self,
        skill_id: str,
        mode: str,
        aliases: Tuple[str, ...],
        require_symbol: bool,
        skill_content: str,
    ) -> None:
        self.skill_id = skill_id
        self.mode = mode
        self.aliases = aliases
        self._require_symbol = require_symbol
        self._skill_content = skill_content

    async def run(self, context: ReportSkillContext) -> ReportSkillResult:
        context = ReportSkillContext(
            config=context.config,
            overrides=context.overrides,
            generated_at=context.generated_at,
            agent_service=context.agent_service,
            provider_cfg=context.provider_cfg,
            selected_model=context.selected_model,
            api_key=context.api_key,
            skill_content=self._skill_content,
        )
        return await _run_single_agent_report(
            context=context,
            mode=self.mode,
            skill_id=self.skill_id,
            require_symbol_and_market=self._require_symbol,
        )


class WatchlistReportSkill:
    skill_id = "watchlist_report"
    mode = "watchlist"
    aliases = ("watchlist",)

    def __init__(self, skill_content: str = "") -> None:
        self._skill_content = skill_content

    async def run(self, context: ReportSkillContext) -> ReportSkillResult:
        init_db(context.config.database.url)
        watchlist_service = WatchlistService(config=context.config)
        items = watchlist_service.list_enabled_items()
        if not items:
            raise ValueError(
                "Watchlist report mode requires at least one enabled item."
            )

        limit = context.overrides.watchlist_limit if context.overrides else None
        selected_items = items[:limit] if limit is not None else items

        warnings: List[str] = []
        if len(selected_items) < len(items):
            warnings.append(
                f"watchlist_limit_applied: selected {len(selected_items)} of {len(items)}"
            )

        rows: List[Dict[str, Any]] = []
        news_total = 0
        for item in selected_items:
            row = await self._run_watchlist_item(
                item=item,
                base_question=context.overrides.question
                if context.overrides and context.overrides.question
                else "",
                peer_list=context.overrides.peer_list
                if context.overrides and context.overrides.peer_list
                else [],
                context=context,
            )
            rows.append(row)
            news_total += int(row.get("news_total") or 0)
            row_warnings = row.get("warnings")
            if isinstance(row_warnings, list):
                warnings.extend([str(item) for item in row_warnings])

        successful = [row for row in rows if str(row.get("status")) == "SUCCEEDED"]
        confidence_values = [
            float(row.get("confidence") or 0.0)
            for row in successful
            if row.get("confidence") is not None
        ]
        avg_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.0
        )

        sentiment_score = 0
        for row in successful:
            sentiment_score += _sentiment_score(str(row.get("sentiment") or ""))
        if sentiment_score > 0:
            aggregate_sentiment = "bullish"
        elif sentiment_score < 0:
            aggregate_sentiment = "bearish"
        else:
            aggregate_sentiment = "neutral"

        markdown = self._render_watchlist_markdown(
            generated_at=context.generated_at,
            rows=rows,
            aggregate_sentiment=aggregate_sentiment,
            average_confidence=avg_confidence,
        )
        analysis_payload: Dict[str, object] = {
            "summary": "持仓报告已生成",
            "sentiment": aggregate_sentiment,
            "key_levels": [],
            "risks": [],
            "action_items": [],
            "confidence": avg_confidence,
            "markdown": markdown,
            "raw": {
                "watchlist": {
                    "total_items": len(items),
                    "analyzed_items": len(selected_items),
                    "successful_items": len(successful),
                    "entries": rows,
                }
            },
        }
        return ReportSkillResult(
            markdown=markdown,
            analysis_payload=analysis_payload,
            news_total=news_total,
            warnings=warnings,
            mode=self.mode,
            skill_id=self.skill_id,
        )

    async def _run_watchlist_item(
        self,
        item: WatchlistItem,
        base_question: str,
        peer_list: List[str],
        context: ReportSkillContext,
    ) -> Dict[str, Any]:
        question = (
            base_question.strip()
            if base_question.strip()
            else (
                f"请从持仓视角分析 {item.symbol} ({item.market}) 的风险收益、仓位建议与风控要点。"
            )
        )
        request = AgentRunRequest(
            mode="stock",
            symbol=item.symbol,
            market=item.market,
            question=question,
            peer_list=peer_list,
        )
        try:
            run = await context.agent_service.run(
                request=request,
                provider_cfg=context.provider_cfg,
                model=context.selected_model,
                api_key=context.api_key,
                skill_content=self._skill_content,
                on_step=context.on_step,
            )
            _, output = context.agent_service.to_analysis_payload(
                request=request,
                run_result=run,
            )
            news_total, warnings = extract_agent_run_stats(run)
            return {
                "symbol": item.symbol,
                "market": item.market,
                "alias": item.alias,
                "display_name": item.display_name,
                "status": "SUCCEEDED",
                "summary": output.summary,
                "sentiment": output.sentiment,
                "confidence": output.confidence,
                "risks": output.risks,
                "action_items": output.action_items,
                "news_total": news_total,
                "warnings": warnings,
                "agent": {
                    "final_report": run.final_report.model_dump(mode="json"),
                    "tool_calls": [
                        call.model_dump(mode="json") for call in run.tool_calls
                    ],
                    "evidence_map": [
                        evidence.model_dump(mode="json")
                        for evidence in run.evidence_map
                    ],
                    "guardrail_issues": [
                        issue.model_dump(mode="json") for issue in run.guardrail_issues
                    ],
                    "analysis_input": run.analysis_input,
                    "runtime_draft": run.runtime_draft.model_dump(mode="json"),
                },
            }
        except Exception as exc:
            return {
                "symbol": item.symbol,
                "market": item.market,
                "alias": item.alias,
                "display_name": item.display_name,
                "status": "FAILED",
                "summary": f"分析失败: {exc}",
                "sentiment": "neutral",
                "confidence": 0.0,
                "risks": [],
                "action_items": ["检查 provider 配置和鉴权状态"],
                "news_total": 0,
                "warnings": [f"watchlist_item_failed[{item.symbol}]: {exc}"],
            }

    @staticmethod
    def _render_watchlist_markdown(
        generated_at: str,
        rows: List[Dict[str, Any]],
        aggregate_sentiment: str,
        average_confidence: float,
    ) -> str:
        lines: List[str] = [
            "# 持仓报告 (Watchlist)",
            "",
            f"- 生成时间: {generated_at}",
            f"- 持仓数量: {len(rows)}",
            f"- 组合情绪: {aggregate_sentiment}",
            f"- 平均置信度: {average_confidence:.2f}",
            "",
            "## 持仓概览",
            "",
            "| Symbol | Market | Name | Sentiment | Confidence | Status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            name = str(
                row.get("display_name") or row.get("alias") or row.get("symbol") or ""
            )
            confidence = row.get("confidence")
            confidence_text = (
                f"{float(confidence):.2f}" if confidence is not None else "N/A"
            )
            lines.append(
                "| "
                f"{row.get('symbol', '')} | "
                f"{row.get('market', '')} | "
                f"{name} | "
                f"{row.get('sentiment', 'neutral')} | "
                f"{confidence_text} | "
                f"{row.get('status', '')} |"
            )

        for row in rows:
            lines.append("")
            lines.append(
                f"## {row.get('symbol', '')} ({row.get('market', '')}) - {row.get('status', '')}"
            )
            lines.append("")
            lines.append(f"- 摘要: {row.get('summary', '')}")
            lines.append(f"- 情绪: {row.get('sentiment', 'neutral')}")
            confidence = row.get("confidence")
            if confidence is None:
                lines.append("- 置信度: N/A")
            else:
                lines.append(f"- 置信度: {float(confidence):.2f}")
            risks = row.get("risks")
            if isinstance(risks, list) and risks:
                lines.append("- 风险: " + "；".join(str(item) for item in risks[:5]))
            actions = row.get("action_items")
            if isinstance(actions, list) and actions:
                lines.append("- 建议: " + "；".join(str(item) for item in actions[:5]))
        return "\n".join(lines) + "\n"


class ReportSkillRegistry:
    """Registry that loads report skills from both SkillCatalog and built-in strategies."""

    def __init__(self, catalog: Optional[SkillCatalog] = None) -> None:
        self._skills_by_alias: Dict[str, ReportSkill] = {}
        self._catalog = catalog
        self._reload()

    def _reload(self) -> None:
        self._skills_by_alias = {}

        # Load catalog-based skills
        if self._catalog is not None:
            self._catalog.reload()
            for summary in self._catalog.list_skills():
                if not summary.mode:
                    continue  # Skip non-report skills (e.g. git-release)
                body = self._catalog.load_skill_body(summary.name) or ""
                if summary.mode == "watchlist":
                    skill: ReportSkill = WatchlistReportSkill(skill_content=body)
                else:
                    skill = CatalogReportSkill(
                        skill_id=summary.name,
                        mode=summary.mode,
                        aliases=summary.aliases,
                        require_symbol=summary.require_symbol,
                        skill_content=body,
                    )
                self._register(skill)

        # Fallback: if no catalog skills loaded, register hardcoded builtins
        if not self._skills_by_alias:
            self._register_builtin_defaults()

    def reload(self) -> None:
        self._reload()

    def _register_builtin_defaults(self) -> None:
        self._register(
            CatalogReportSkill(
                skill_id="market_report",
                mode="market",
                aliases=("market",),
                require_symbol=False,
                skill_content="",
            )
        )
        self._register(
            CatalogReportSkill(
                skill_id="stock_report",
                mode="stock",
                aliases=("stock",),
                require_symbol=True,
                skill_content="",
            )
        )
        self._register(WatchlistReportSkill())

    def _register(self, skill: Any) -> None:
        self._register_alias(skill.skill_id, skill)
        self._register_alias(skill.mode, skill)
        for alias in skill.aliases:
            self._register_alias(alias, skill)

    def resolve(self, skill_id: Optional[str], mode: str) -> ReportSkill:
        requested = (skill_id or "").strip().lower()
        if requested:
            skill = self._skills_by_alias.get(requested)
            if skill is not None:
                return skill
            raise ValueError(f"Unknown report skill: {skill_id}")

        fallback = (mode or "").strip().lower()
        skill = self._skills_by_alias.get(fallback)
        if skill is not None:
            return skill
        raise ValueError(f"Unsupported report mode: {mode}")

    def _register_alias(self, raw_alias: str, skill: ReportSkill) -> None:
        alias = (raw_alias or "").strip().lower()
        if not alias:
            return
        existing = self._skills_by_alias.get(alias)
        if existing is not None and existing.skill_id != skill.skill_id:
            raise ValueError(f"Report skill alias conflict: {alias}")
        self._skills_by_alias[alias] = skill


async def _run_single_agent_report(
    context: ReportSkillContext,
    mode: str,
    skill_id: str,
    require_symbol_and_market: bool,
) -> ReportSkillResult:
    symbol = context.overrides.symbol if context.overrides else None
    market = context.overrides.market if context.overrides else None
    if require_symbol_and_market and (not symbol or not market):
        raise ValueError("Stock report mode requires symbol and market.")

    agent_mode: Literal["stock", "market"] = "stock" if mode == "stock" else "market"
    agent_request = AgentRunRequest(
        mode=agent_mode,
        symbol=symbol,
        market=market,
        question=(
            context.overrides.question
            if context.overrides and context.overrides.question
            else ""
        ),
        peer_list=context.overrides.peer_list
        if context.overrides and context.overrides.peer_list
        else [],
    )
    agent_run = await context.agent_service.run(
        request=agent_request,
        provider_cfg=context.provider_cfg,
        model=context.selected_model,
        api_key=context.api_key,
        skill_content=context.skill_content,
        on_step=context.on_step,
    )
    _, analysis_output = context.agent_service.to_analysis_payload(
        request=agent_request,
        run_result=agent_run,
    )
    analysis_payload = analysis_output.model_dump(mode="json")
    news_total, warnings = extract_agent_run_stats(agent_run)
    analysis_payload["agent"] = {
        "final_report": agent_run.final_report.model_dump(mode="json"),
        "tool_calls": [item.model_dump(mode="json") for item in agent_run.tool_calls],
        "evidence_map": [
            item.model_dump(mode="json") for item in agent_run.evidence_map
        ],
        "guardrail_issues": [
            item.model_dump(mode="json") for item in agent_run.guardrail_issues
        ],
        "analysis_input": agent_run.analysis_input,
        "runtime_draft": agent_run.runtime_draft.model_dump(mode="json"),
    }
    return ReportSkillResult(
        markdown=analysis_output.markdown,
        analysis_payload=analysis_payload,
        news_total=news_total,
        warnings=warnings,
        mode=agent_mode,
        skill_id=skill_id,
    )


def extract_agent_run_stats(agent_run: Any) -> Tuple[int, List[str]]:
    news_total = 0
    warnings: List[str] = []

    analysis_input = (
        agent_run.analysis_input if hasattr(agent_run, "analysis_input") else {}
    )
    tool_results = (
        analysis_input.get("tool_results", {})
        if isinstance(analysis_input, dict)
        else {}
    )
    if isinstance(tool_results, dict):
        news_payload = tool_results.get("search_news")
        if isinstance(news_payload, dict):
            items = news_payload.get("items")
            if isinstance(items, list):
                news_total = len(items)
        for payload in tool_results.values():
            if not isinstance(payload, dict):
                continue
            row_warnings = payload.get("warnings")
            if not isinstance(row_warnings, list):
                continue
            for row in row_warnings:
                warnings.append(str(row))

    guardrail_issues = (
        agent_run.guardrail_issues if hasattr(agent_run, "guardrail_issues") else []
    )
    if isinstance(guardrail_issues, list):
        for issue in guardrail_issues:
            code = str(getattr(issue, "code", "unknown"))
            message = str(getattr(issue, "message", ""))
            warnings.append(f"guardrail[{code}]: {message}")

    return news_total, warnings


def _sentiment_score(sentiment: str) -> int:
    text = sentiment.strip().lower()
    if not text:
        return 0
    if any(
        token in text for token in ["bull", "positive", "optimistic", "看多", "乐观"]
    ):
        return 1
    if any(
        token in text for token in ["bear", "negative", "pessimistic", "看空", "悲观"]
    ):
        return -1
    return 0
