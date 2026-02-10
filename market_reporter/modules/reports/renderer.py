from __future__ import annotations

from typing import Dict, List

from market_reporter.core.types import AnalysisOutput, FlowPoint, NewsItem


class ReportRenderer:
    def render_markdown(
        self,
        generated_at: str,
        analysis_output: AnalysisOutput,
        news_items: List[NewsItem],
        flow_series: Dict[str, List[FlowPoint]],
        warnings: List[str],
        provider_id: str,
        model: str,
    ) -> str:
        # Build markdown incrementally to keep section ordering deterministic.
        lines: List[str] = []
        lines.append("# 市场分析报告")
        lines.append("")
        lines.append(f"- 生成时间: {generated_at}")
        lines.append(f"- 分析引擎: {provider_id}")
        lines.append(f"- 模型: {model}")
        lines.append(f"- 新闻总量: {len(news_items)}")
        lines.append("")

        lines.append("## 一、模型结论")
        lines.append("")
        lines.append(analysis_output.markdown)
        lines.append("")

        lines.append("## 二、结构化输出")
        lines.append("")
        lines.append(f"- Summary: {analysis_output.summary}")
        lines.append(f"- Sentiment: {analysis_output.sentiment}")
        lines.append(f"- Confidence: {analysis_output.confidence:.2f}")
        lines.append("")
        lines.append("### Key Levels")
        lines.append("")
        for row in analysis_output.key_levels:
            lines.append(f"- {row}")
        if not analysis_output.key_levels:
            lines.append("- (none)")
        lines.append("")
        lines.append("### Risks")
        lines.append("")
        for row in analysis_output.risks:
            lines.append(f"- {row}")
        if not analysis_output.risks:
            lines.append("- (none)")
        lines.append("")
        lines.append("### Action Items")
        lines.append("")
        for row in analysis_output.action_items:
            lines.append(f"- {row}")
        if not analysis_output.action_items:
            lines.append("- (none)")
        lines.append("")

        lines.append("## 三、新闻样本（最多20条）")
        lines.append("")
        lines.append("| 分类 | 来源 | 时间 | 标题 |")
        lines.append("| --- | --- | --- | --- |")
        for item in news_items[:20]:
            safe_title = item.title.replace("|", " ")
            if item.link:
                safe_title = f"[{safe_title}]({item.link})"
            lines.append(f"| {item.category} | {item.source} | {item.published or '-'} | {safe_title} |")
        if not news_items:
            lines.append("| - | - | - | - |")
        lines.append("")

        lines.append("## 四、资金流样本")
        lines.append("")
        # Keep only tail samples to avoid oversized reports.
        for key, rows in flow_series.items():
            lines.append(f"### {key}")
            lines.append("")
            lines.append("| 日期 | 数值 | 单位 |")
            lines.append("| --- | ---: | --- |")
            for row in rows[-8:]:
                lines.append(f"| {row.date} | {row.value:.2f} | {row.unit} |")
            if not rows:
                lines.append("| - | - | - |")
            lines.append("")

        if warnings:
            lines.append("## 五、告警")
            lines.append("")
            for warning in warnings:
                lines.append(f"- {warning}")
            lines.append("")

        return "\n".join(lines).strip() + "\n"
