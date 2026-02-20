from __future__ import annotations

from typing import Any, Dict, List

from market_reporter.modules.analysis.agent.schemas import (
    AgentEvidence,
    AgentFinalReport,
    GuardrailIssue,
    RuntimeDraft,
)


class AgentReportFormatter:
    def format_report(
        self,
        mode: str,
        question: str,
        runtime_draft: RuntimeDraft,
        tool_results: Dict[str, Dict[str, Any]],
        evidence_map: List[AgentEvidence],
        guardrail_issues: List[GuardrailIssue],
        confidence: float,
    ) -> AgentFinalReport:
        conclusions = self._build_conclusions(runtime_draft, evidence_map)
        market_technical = self._build_market_technical(mode, tool_results)
        indicator_table = self._build_indicator_table(mode, tool_results)
        fundamentals = self._build_fundamentals(mode, tool_results)
        catalysts_risks = self._build_catalysts_and_risks(
            runtime_draft, tool_results, guardrail_issues
        )
        risk_action_table = self._build_risk_action_table(runtime_draft)
        valuation_scenarios = self._build_valuation(runtime_draft)

        markdown = self._render_markdown(
            mode=mode,
            question=question,
            conclusions=conclusions,
            market_technical=market_technical,
            indicator_table=indicator_table,
            fundamentals=fundamentals,
            catalysts_risks=catalysts_risks,
            risk_action_table=risk_action_table,
            valuation_scenarios=valuation_scenarios,
            evidence_map=evidence_map,
            guardrail_issues=guardrail_issues,
            confidence=confidence,
        )

        return AgentFinalReport(
            mode="stock" if mode == "stock" else "market",
            question=question,
            conclusions=conclusions,
            market_technical=market_technical,
            fundamentals=fundamentals,
            catalysts_risks=catalysts_risks,
            valuation_scenarios=valuation_scenarios,
            data_sources=evidence_map,
            guardrail_issues=guardrail_issues,
            confidence=confidence,
            markdown=markdown,
            raw={
                "runtime": runtime_draft.raw,
            },
        )

    def _build_conclusions(
        self,
        runtime_draft: RuntimeDraft,
        evidence_map: List[AgentEvidence],
    ) -> List[str]:
        result: List[str] = []
        base = list(runtime_draft.conclusions or [])
        if not base and runtime_draft.summary:
            base.append(runtime_draft.summary)
        if len(base) < 3:
            base.extend(runtime_draft.action_items)
        if len(base) < 3:
            base.extend(runtime_draft.risks)
        if not base:
            base = ["当前样本不足以形成强结论，维持中性观察。"]

        pointer_ids = [item.evidence_id for item in evidence_map] or ["E1"]
        for idx, row in enumerate(base[:6]):
            line = row.strip()
            if not line:
                continue
            pointer = pointer_ids[idx % len(pointer_ids)]
            if "[E" not in line:
                line = f"{line} [{pointer}]"
            result.append(line)
        while len(result) < 3:
            pointer = pointer_ids[len(result) % len(pointer_ids)]
            result.append(f"补充结论待更多数据验证 [{pointer}]")
        return result[:6]

    @staticmethod
    def _build_market_technical(
        mode: str, tool_results: Dict[str, Dict[str, Any]]
    ) -> str:
        if mode != "stock":
            return "N/A（市场模式不提供单一标的技术位，使用宏观与新闻横截面信号）"

        indicators = tool_results.get("compute_indicators", {})
        if not isinstance(indicators, dict) or not indicators:
            return "价格样本不足，无法计算趋势与关键位。"

        trend = (
            indicators.get("trend", {})
            if isinstance(indicators.get("trend"), dict)
            else {}
        )
        momentum = (
            indicators.get("momentum", {})
            if isinstance(indicators.get("momentum"), dict)
            else {}
        )
        volume_price = (
            indicators.get("volume_price", {})
            if isinstance(indicators.get("volume_price"), dict)
            else {}
        )
        patterns = (
            indicators.get("patterns", {})
            if isinstance(indicators.get("patterns"), dict)
            else {}
        )
        sr = (
            indicators.get("support_resistance", {})
            if isinstance(indicators.get("support_resistance"), dict)
            else {}
        )
        strategy = (
            indicators.get("strategy", {})
            if isinstance(indicators.get("strategy"), dict)
            else {}
        )
        as_of = str(indicators.get("as_of") or "N/A")

        trend_primary = trend.get("primary", {}) if isinstance(trend, dict) else {}
        momentum_primary = (
            momentum.get("primary", {}) if isinstance(momentum, dict) else {}
        )
        volume_primary = (
            volume_price.get("primary", {}) if isinstance(volume_price, dict) else {}
        )
        patterns_primary = (
            patterns.get("primary", {}) if isinstance(patterns, dict) else {}
        )
        sr_primary = sr.get("primary", {}) if isinstance(sr, dict) else {}

        supports = AgentReportFormatter._format_levels(sr_primary.get("supports"))
        resistances = AgentReportFormatter._format_levels(sr_primary.get("resistances"))
        recent_patterns = AgentReportFormatter._format_patterns(
            patterns_primary.get("recent")
        )

        lines = [
            f"数据日期: {as_of}",
            "[趋势]",
            (
                f"MA 排列: {((trend_primary.get('ma') or {}).get('state') if isinstance(trend_primary, dict) else 'N/A')}; "
                f"MACD: {((trend_primary.get('macd') or {}).get('cross') if isinstance(trend_primary, dict) else 'N/A')}; "
                f"布林: {((trend_primary.get('bollinger') or {}).get('status') if isinstance(trend_primary, dict) else 'N/A')}"
            ),
            "[动量]",
            (
                f"RSI: {AgentReportFormatter._format_metric(((momentum_primary.get('rsi') or {}).get('value') if isinstance(momentum_primary, dict) else None))}; "
                f"RSI 状态: {((momentum_primary.get('rsi') or {}).get('status') if isinstance(momentum_primary, dict) else 'N/A')}; "
                f"KDJ: {((momentum_primary.get('kdj') or {}).get('status') if isinstance(momentum_primary, dict) else 'N/A')}; "
                f"背离: {((momentum_primary.get('divergence') or {}).get('type') if isinstance(momentum_primary, dict) else 'N/A')}"
            ),
            "[量价]",
            (
                f"量比: {AgentReportFormatter._format_metric(volume_primary.get('volume_ratio') if isinstance(volume_primary, dict) else None)}; "
                f"缩量回调: {AgentReportFormatter._format_metric(volume_primary.get('shrink_pullback') if isinstance(volume_primary, dict) else None)}; "
                f"放量突破: {AgentReportFormatter._format_metric(volume_primary.get('volume_breakout') if isinstance(volume_primary, dict) else None)}; "
                f"ATR14: {AgentReportFormatter._format_metric(volume_primary.get('atr_14') if isinstance(volume_primary, dict) else None)}"
            ),
            "[形态]",
            f"最近形态: {recent_patterns}",
            "[支撑/压力]",
            f"支撑: {supports}; 压力: {resistances}",
            "[策略级输出]",
            (
                f"score={AgentReportFormatter._format_metric(strategy.get('score'))}, stance={strategy.get('stance') or 'N/A'}, "
                f"position_size={AgentReportFormatter._format_metric(strategy.get('position_size'))}%, "
                f"entry_zone={AgentReportFormatter._format_metric(strategy.get('entry_zone'))}, stop_loss={AgentReportFormatter._format_metric(strategy.get('stop_loss'))}, "
                f"take_profit={AgentReportFormatter._format_metric(strategy.get('take_profit'))}"
            ),
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_indicator_table(
        mode: str, tool_results: Dict[str, Dict[str, Any]]
    ) -> str:
        header = [
            "| 维度 | 指标 | 值 | 说明 |",
            "| --- | --- | --- | --- |",
        ]
        if mode != "stock":
            return "\n".join(
                header + ["| 宏观 | 综合信号 | N/A | 市场模式不输出单一标的技术指标 |"]
            )

        indicators = tool_results.get("compute_indicators", {})
        if not isinstance(indicators, dict) or not indicators:
            return "\n".join(
                header + ["| 技术面 | 指标缺失 | N/A | 价格样本不足，无法计算指标 |"]
            )

        trend = (
            indicators.get("trend", {})
            if isinstance(indicators.get("trend"), dict)
            else {}
        )
        momentum = (
            indicators.get("momentum", {})
            if isinstance(indicators.get("momentum"), dict)
            else {}
        )
        volume_price = (
            indicators.get("volume_price", {})
            if isinstance(indicators.get("volume_price"), dict)
            else {}
        )
        strategy = (
            indicators.get("strategy", {})
            if isinstance(indicators.get("strategy"), dict)
            else {}
        )

        trend_primary = trend.get("primary", {}) if isinstance(trend, dict) else {}
        momentum_primary = (
            momentum.get("primary", {}) if isinstance(momentum, dict) else {}
        )
        volume_primary = (
            volume_price.get("primary", {}) if isinstance(volume_price, dict) else {}
        )

        rows = [
            (
                "趋势",
                "MA 状态",
                AgentReportFormatter._format_metric(
                    (
                        (trend_primary.get("ma") or {}).get("state")
                        if isinstance(trend_primary, dict)
                        else None
                    )
                ),
                "均线排列方向",
            ),
            (
                "趋势",
                "MACD",
                AgentReportFormatter._format_metric(
                    (
                        (trend_primary.get("macd") or {}).get("cross")
                        if isinstance(trend_primary, dict)
                        else None
                    )
                ),
                "MACD 交叉状态",
            ),
            (
                "趋势",
                "布林状态",
                AgentReportFormatter._format_metric(
                    (
                        (trend_primary.get("bollinger") or {}).get("status")
                        if isinstance(trend_primary, dict)
                        else None
                    )
                ),
                "价格与布林带关系",
            ),
            (
                "动量",
                "RSI",
                AgentReportFormatter._format_metric(
                    (
                        (momentum_primary.get("rsi") or {}).get("value")
                        if isinstance(momentum_primary, dict)
                        else None
                    )
                ),
                AgentReportFormatter._format_metric(
                    (
                        (momentum_primary.get("rsi") or {}).get("status")
                        if isinstance(momentum_primary, dict)
                        else None
                    )
                ),
            ),
            (
                "动量",
                "KDJ",
                AgentReportFormatter._format_metric(
                    (
                        (momentum_primary.get("kdj") or {}).get("status")
                        if isinstance(momentum_primary, dict)
                        else None
                    )
                ),
                "KDJ 状态",
            ),
            (
                "动量",
                "背离类型",
                AgentReportFormatter._format_metric(
                    (
                        (momentum_primary.get("divergence") or {}).get("type")
                        if isinstance(momentum_primary, dict)
                        else None
                    )
                ),
                "价格与动量背离",
            ),
            (
                "量价",
                "量比",
                AgentReportFormatter._format_metric(
                    volume_primary.get("volume_ratio")
                    if isinstance(volume_primary, dict)
                    else None
                ),
                "成交量变化",
            ),
            (
                "量价",
                "放量突破",
                AgentReportFormatter._format_metric(
                    volume_primary.get("volume_breakout")
                    if isinstance(volume_primary, dict)
                    else None
                ),
                "放量突破信号",
            ),
            (
                "量价",
                "ATR14",
                AgentReportFormatter._format_metric(
                    volume_primary.get("atr_14")
                    if isinstance(volume_primary, dict)
                    else None
                ),
                "波动幅度",
            ),
            (
                "策略",
                "Score",
                AgentReportFormatter._format_metric(strategy.get("score")),
                AgentReportFormatter._format_metric(strategy.get("stance")),
            ),
            (
                "策略",
                "仓位建议",
                AgentReportFormatter._format_metric(strategy.get("position_size")),
                "建议仓位(%)",
            ),
            (
                "策略",
                "止损/止盈",
                (
                    f"{AgentReportFormatter._format_metric(strategy.get('stop_loss'))} / "
                    f"{AgentReportFormatter._format_metric(strategy.get('take_profit'))}"
                ),
                "风险收益边界",
            ),
        ]

        lines = list(header)
        for dimension, metric, value, note in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        AgentReportFormatter._escape_table_cell(dimension),
                        AgentReportFormatter._escape_table_cell(metric),
                        AgentReportFormatter._escape_table_cell(value),
                        AgentReportFormatter._escape_table_cell(note),
                    ]
                )
                + " |"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_risk_action_table(runtime_draft: RuntimeDraft) -> str:
        header = [
            "| 风险项 | 触发条件 | 执行建议 |",
            "| --- | --- | --- |",
        ]
        risks = [
            AgentReportFormatter._format_metric(item)
            for item in runtime_draft.risks
            if str(item).strip()
        ]
        actions = [
            AgentReportFormatter._format_metric(item)
            for item in runtime_draft.action_items
            if str(item).strip()
        ]

        if not risks and not actions:
            return "\n".join(header + ["| N/A | N/A | N/A |"])

        rows: List[str] = []
        total = max(len(risks), len(actions))
        for index in range(total):
            risk = risks[index] if index < len(risks) else "N/A"
            action = actions[index] if index < len(actions) else "N/A"
            trigger = (
                f"{risk} 出现明确扩散信号" if risk != "N/A" else "关键指标偏离预设区间"
            )
            rows.append(
                "| "
                + " | ".join(
                    [
                        AgentReportFormatter._escape_table_cell(risk),
                        AgentReportFormatter._escape_table_cell(trigger),
                        AgentReportFormatter._escape_table_cell(action),
                    ]
                )
                + " |"
            )
        return "\n".join(header + rows)

    @staticmethod
    def _format_metric(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (int, float)):
            if value != value:
                return "N/A"
            if abs(float(value)) >= 1000:
                return f"{float(value):,.2f}"
            if abs(float(value)) >= 1:
                return f"{float(value):.2f}"
            return f"{float(value):.4f}".rstrip("0").rstrip(".") or "0"
        text = str(value).strip()
        return text or "N/A"

    @staticmethod
    def _escape_table_cell(value: Any) -> str:
        text = AgentReportFormatter._format_metric(value)
        return text.replace("|", "\\|").replace("\n", " ").strip() or "N/A"

    @staticmethod
    def _format_levels(raw_levels: Any) -> str:
        if not isinstance(raw_levels, list) or not raw_levels:
            return "N/A"
        parts: List[str] = []
        for row in raw_levels[:3]:
            if not isinstance(row, dict):
                continue
            label = row.get("level") or "-"
            price = row.get("price")
            touches = row.get("touches")
            parts.append(f"{label}:{price}(touches={touches})")
        return "; ".join(parts) if parts else "N/A"

    @staticmethod
    def _format_patterns(raw_patterns: Any) -> str:
        if not isinstance(raw_patterns, list) or not raw_patterns:
            return "N/A"
        parts: List[str] = []
        for row in raw_patterns[:3]:
            if not isinstance(row, dict):
                continue
            parts.append(f"{row.get('type')}:{row.get('direction')}@{row.get('ts')}")
        return "; ".join(parts) if parts else "N/A"

    @staticmethod
    def _build_fundamentals(mode: str, tool_results: Dict[str, Dict[str, Any]]) -> str:
        if mode != "stock":
            return "N/A（市场模式聚合宏观与新闻，不输出单个公司财务拆解）"
        fundamentals = tool_results.get("get_fundamentals", {})
        metrics = fundamentals.get("metrics") if isinstance(fundamentals, dict) else {}
        if not isinstance(metrics, dict) or not metrics:
            return "基本面数据不足。"
        return (
            f"营收: {metrics.get('revenue')}; 净利润: {metrics.get('net_income')}; "
            f"经营现金流: {metrics.get('operating_cash_flow')}; 自由现金流: {metrics.get('free_cash_flow')}; "
            f"总资产: {metrics.get('total_assets')}; 总负债: {metrics.get('total_liabilities')}; "
            f"股东权益: {metrics.get('shareholder_equity')}。"
        )

    @staticmethod
    def _build_catalysts_and_risks(
        runtime_draft: RuntimeDraft,
        tool_results: Dict[str, Dict[str, Any]],
        guardrail_issues: List[GuardrailIssue],
    ) -> str:
        news = tool_results.get("search_news", {})
        items = news.get("items") if isinstance(news, dict) else []
        top_news = []
        if isinstance(items, list):
            for row in items[:3]:
                if not isinstance(row, dict):
                    continue
                top_news.append(f"{row.get('published_at', '')} {row.get('title', '')}")
        risk_text = (
            "；".join(runtime_draft.risks[:4])
            if runtime_draft.risks
            else "未识别高置信风险项。"
        )
        guardrail_text = (
            "；".join([issue.message for issue in guardrail_issues])
            if guardrail_issues
            else "无一致性冲突。"
        )
        catalyst_text = "；".join(top_news) if top_news else "新闻催化不足。"
        return (
            f"短中期催化: {catalyst_text}\n"
            f"风险清单: {risk_text}\n"
            f"护栏冲突: {guardrail_text}"
        )

    @staticmethod
    def _build_valuation(runtime_draft: RuntimeDraft) -> str:
        assumptions = runtime_draft.scenario_assumptions or {}
        base = assumptions.get("base") or "基准: 盈利与风险溢价维持当前水平。"
        bull = assumptions.get("bull") or "乐观: 盈利超预期且估值扩张。"
        bear = assumptions.get("bear") or "悲观: 盈利下修且估值收缩。"
        return f"{base}\n{bull}\n{bear}"

    @staticmethod
    def _render_markdown(
        mode: str,
        question: str,
        conclusions: List[str],
        market_technical: str,
        indicator_table: str,
        fundamentals: str,
        catalysts_risks: str,
        risk_action_table: str,
        valuation_scenarios: str,
        evidence_map: List[AgentEvidence],
        guardrail_issues: List[GuardrailIssue],
        confidence: float,
    ) -> str:
        lines: List[str] = []
        lines.append("# Agent 分析报告")
        lines.append("")
        lines.append(f"- 模式: {mode}")
        lines.append(f"- 问题: {question}")
        lines.append(f"- 置信度: {confidence:.2f}")
        lines.append("")

        lines.append("## 结论摘要（3–6条）")
        lines.append("")
        for row in conclusions:
            lines.append(f"- {row}")
        lines.append("")

        lines.append("## 行情与技术面")
        lines.append("")
        lines.append(market_technical)
        lines.append("")

        lines.append("## 关键指标表")
        lines.append("")
        lines.append(indicator_table)
        lines.append("")

        lines.append("## 基本面")
        lines.append("")
        lines.append(fundamentals)
        lines.append("")

        lines.append("## 催化剂与风险清单")
        lines.append("")
        lines.append(catalysts_risks)
        lines.append("")

        lines.append("## 风险与动作清单")
        lines.append("")
        lines.append(risk_action_table)
        lines.append("")

        lines.append("## 估值与情景分析")
        lines.append("")
        lines.append(valuation_scenarios)
        lines.append("")

        if guardrail_issues:
            lines.append("## 一致性冲突项")
            lines.append("")
            for item in guardrail_issues:
                lines.append(f"- [{item.severity}] {item.message}")
            lines.append("")

        lines.append("## 数据来源与时间戳")
        lines.append("")
        lines.append("| 证据ID | 描述 | 来源 | 数据时间 | 指针 |")
        lines.append("| --- | --- | --- | --- | --- |")
        if evidence_map:
            for item in evidence_map:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            AgentReportFormatter._escape_table_cell(item.evidence_id),
                            AgentReportFormatter._escape_table_cell(item.statement),
                            AgentReportFormatter._escape_table_cell(item.source),
                            AgentReportFormatter._escape_table_cell(item.as_of),
                            AgentReportFormatter._escape_table_cell(item.pointer),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| N/A | N/A | N/A | N/A | N/A |")
        lines.append("")

        return "\n".join(lines).strip() + "\n"
