from typing import Dict, List

from market_reporter.models import AnalysisResult, FlowPoint, NewsItem


class ReportRenderer:
    def render_markdown(
        self,
        analysis: AnalysisResult,
        news_items: List[NewsItem],
        flow_series: Dict[str, List[FlowPoint]],
        errors: List[str],
    ) -> str:
        lines: List[str] = []
        lines.append("# 财经/政策新闻与资金流分析报告")
        lines.append("")
        lines.append(f"- 生成时间: {analysis.generated_at}")
        lines.append(f"- 新闻总量: {analysis.news_total}")
        lines.append("")

        lines.append("## 一、执行摘要")
        lines.append("")
        for item in analysis.highlights:
            lines.append(f"- {item}")
        lines.append("")

        lines.append("## 二、新闻概览")
        lines.append("")
        lines.append(f"- 情绪标签: **{analysis.sentiment_label}** (score={analysis.sentiment_score})")
        lines.append("- 分类统计:")
        for category, count in sorted(analysis.news_by_category.items()):
            lines.append(f"  - {category}: {count}")
        lines.append("")

        lines.append("### 热词 Top 15")
        lines.append("")
        lines.append("| 关键词 | 频次 |")
        lines.append("| --- | ---: |")
        for keyword, freq in analysis.top_keywords:
            lines.append(f"| {keyword} | {freq} |")
        lines.append("")

        lines.append("### 重点新闻（最新 20 条）")
        lines.append("")
        lines.append("| 分类 | 来源 | 发布时间 | 标题 |")
        lines.append("| --- | --- | --- | --- |")
        for item in news_items[:20]:
            safe_title = item.title.replace("|", " ")
            if item.link:
                safe_title = f"[{safe_title}]({item.link})"
            lines.append(
                f"| {item.category} | {item.source} | {item.published or '-'} | {safe_title} |"
            )
        lines.append("")

        lines.append("## 三、资金流统计")
        lines.append("")
        lines.append("| 指标 | 市场 | 最新日期 | 最新值 | 近4期均值 | 较前一期变化 | 方向 |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
        for key, summary in analysis.flow_summary.items():
            latest = "-" if summary.latest_value is None else f"{summary.latest_value:.2f}"
            avg = "-" if summary.recent_average is None else f"{summary.recent_average:.2f}"
            delta = "-" if summary.change_vs_previous is None else f"{summary.change_vs_previous:.2f}"
            metric_name = summary.series_name or key
            lines.append(
                f"| {metric_name} ({summary.unit}) | {summary.market or '-'} | "
                f"{summary.latest_date or '-'} | {latest} | {avg} | {delta} | {summary.direction} |"
            )
        lines.append("")

        lines.append("## 四、原始资金流序列（最近 8 条）")
        lines.append("")
        for key, points in flow_series.items():
            lines.append(f"### {key}")
            lines.append("")
            lines.append("| 日期 | 数值 | 单位 |")
            lines.append("| --- | ---: | --- |")
            for point in points[-8:]:
                lines.append(f"| {point.date} | {point.value:.2f} | {point.unit} |")
            if not points:
                lines.append("| - | - | - |")
            lines.append("")

        if errors:
            lines.append("## 五、采集告警")
            lines.append("")
            for err in errors:
                lines.append(f"- {err}")
            lines.append("")

        lines.append("## 六、方法说明")
        lines.append("")
        lines.append("- A/H 资金流来自东财互联互通序列（北向/南向净流入）。")
        lines.append("- US 资金流使用 FRED 的基金与 ETF 股票资产交易额序列。")
        lines.append("- 新闻情绪采用关键词启发式打分，仅作为快速筛查信号。")
        lines.append("")

        return "\n".join(lines).strip() + "\n"
