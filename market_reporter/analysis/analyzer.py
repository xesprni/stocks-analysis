import re
from collections import Counter
from statistics import mean
from typing import Dict, List

from market_reporter.models import AnalysisFlowSummary, AnalysisResult, FlowPoint, NewsItem

TOKEN_PATTERN = re.compile(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}")

POSITIVE_TERMS = {
    "up",
    "rally",
    "beat",
    "growth",
    "recovery",
    "easing",
    "surge",
    "反弹",
    "增长",
    "修复",
    "上调",
    "改善",
}

NEGATIVE_TERMS = {
    "down",
    "drop",
    "fall",
    "risk",
    "inflation",
    "tightening",
    "recession",
    "decline",
    "下滑",
    "风险",
    "收紧",
    "通胀",
    "衰退",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "after",
    "over",
    "market",
    "markets",
    "will",
    "says",
    "news",
    "this",
    "that",
    "into",
    "have",
    "has",
    "new",
    "its",
    "about",
    "latest",
    "中国",
    "美国",
    "市场",
    "政策",
    "经济",
}


class Analyzer:
    def analyze(
        self,
        generated_at: str,
        news_items: List[NewsItem],
        flow_series: Dict[str, List[FlowPoint]],
    ) -> AnalysisResult:
        sentiment_score = self._score_sentiment(news_items)
        sentiment_label = self._label_sentiment(sentiment_score)

        flow_summary: Dict[str, AnalysisFlowSummary] = {}
        for key, points in flow_series.items():
            flow_summary[key] = self._summarize_flow(points)

        top_keywords = self._extract_top_keywords(news_items, top_n=15)
        news_by_category = self._count_news_by_category(news_items)
        highlights = self._build_highlights(sentiment_label, flow_summary)

        return AnalysisResult(
            generated_at=generated_at,
            news_total=len(news_items),
            news_by_category=news_by_category,
            top_keywords=top_keywords,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            flow_summary=flow_summary,
            highlights=highlights,
        )

    def _count_news_by_category(self, news_items: List[NewsItem]) -> Dict[str, int]:
        counter: Counter = Counter()
        for item in news_items:
            counter[item.category] += 1
        return dict(counter)

    def _extract_top_keywords(self, news_items: List[NewsItem], top_n: int) -> List:
        counter: Counter = Counter()
        for item in news_items:
            for token in TOKEN_PATTERN.findall(item.title):
                normalized = token.lower()
                if normalized in STOPWORDS:
                    continue
                if len(normalized) <= 1:
                    continue
                counter[normalized] += 1
        return counter.most_common(top_n)

    def _score_sentiment(self, news_items: List[NewsItem]) -> int:
        score = 0
        for item in news_items:
            title = item.title.lower()
            positive_hits = sum(1 for term in POSITIVE_TERMS if term in title or term in item.title)
            negative_hits = sum(1 for term in NEGATIVE_TERMS if term in title or term in item.title)
            score += positive_hits - negative_hits
        return score

    @staticmethod
    def _label_sentiment(score: int) -> str:
        if score >= 5:
            return "偏积极"
        if score <= -5:
            return "偏谨慎"
        return "中性"

    def _summarize_flow(self, points: List[FlowPoint]) -> AnalysisFlowSummary:
        if not points:
            return AnalysisFlowSummary(
                series_name="",
                market="",
                unit="",
                latest_date=None,
                latest_value=None,
                recent_average=None,
                change_vs_previous=None,
                direction="数据不足",
            )

        ordered = sorted(points, key=lambda point: point.date)
        latest = ordered[-1]
        latest_value = latest.value
        previous_value = ordered[-2].value if len(ordered) > 1 else None
        recent_points = ordered[-4:] if len(ordered) >= 4 else ordered
        recent_average = mean(point.value for point in recent_points)
        change = latest_value - previous_value if previous_value is not None else None

        direction = "中性"
        if change is not None:
            if change > 0:
                direction = "流入增强"
            elif change < 0:
                direction = "流入回落"

        return AnalysisFlowSummary(
            series_name=latest.series_name,
            market=latest.market,
            unit=latest.unit,
            latest_date=latest.date,
            latest_value=latest_value,
            recent_average=recent_average,
            change_vs_previous=change,
            direction=direction,
        )

    def _build_highlights(
        self,
        sentiment_label: str,
        flow_summary: Dict[str, AnalysisFlowSummary],
    ) -> List[str]:
        highlights: List[str] = [f"新闻情绪判断：{sentiment_label}。"]

        for key, summary in flow_summary.items():
            if summary.latest_value is None:
                continue
            latest_text = f"{summary.latest_value:.2f}{summary.unit}"
            if key == "a_share_northbound_net_inflow":
                highlights.append(f"A股北向最新净流入为 {latest_text}，状态：{summary.direction}。")
            elif key == "hk_share_southbound_net_inflow":
                highlights.append(f"港股南向最新净流入为 {latest_text}，状态：{summary.direction}。")
            elif key == "us_equity_mutual_fund_flow":
                highlights.append(f"美股共同基金股票资产交易额最新值 {latest_text}。")
            elif key == "us_equity_etf_flow":
                highlights.append(f"美股ETF股票资产交易额最新值 {latest_text}。")

        if len(highlights) == 1:
            highlights.append("可用资金流数据不足，建议检查网络与数据源可达性。")

        return highlights
