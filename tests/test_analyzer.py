import unittest

from market_reporter.analysis.analyzer import Analyzer
from market_reporter.models import FlowPoint, NewsItem


class AnalyzerTest(unittest.TestCase):
    def test_analyze_returns_expected_summary(self):
        analyzer = Analyzer()
        news = [
            NewsItem(
                category="finance",
                source="demo",
                title="Markets rally as growth outlook improves",
                link="",
                published="2026-02-05",
            ),
            NewsItem(
                category="policy",
                source="demo",
                title="央行政策微调，市场风险偏好回升",
                link="",
                published="2026-02-05",
            ),
            NewsItem(
                category="finance",
                source="demo",
                title="Tech stocks drop amid inflation concern",
                link="",
                published="2026-02-05",
            ),
        ]
        flows = {
            "a_share_northbound_net_inflow": [
                FlowPoint(
                    market="A_SHARE",
                    series_key="a_share_northbound_net_inflow",
                    series_name="A股北向净流入（陆股通）",
                    date="2026-02-03",
                    value=50.0,
                    unit="亿元人民币",
                ),
                FlowPoint(
                    market="A_SHARE",
                    series_key="a_share_northbound_net_inflow",
                    series_name="A股北向净流入（陆股通）",
                    date="2026-02-04",
                    value=80.0,
                    unit="亿元人民币",
                ),
            ],
            "us_equity_etf_flow": [
                FlowPoint(
                    market="US",
                    series_key="us_equity_etf_flow",
                    series_name="美国ETF股票资产交易额",
                    date="2025-10-01",
                    value=23.0,
                    unit="十亿美元",
                ),
                FlowPoint(
                    market="US",
                    series_key="us_equity_etf_flow",
                    series_name="美国ETF股票资产交易额",
                    date="2026-01-01",
                    value=30.0,
                    unit="十亿美元",
                ),
            ],
        }

        result = analyzer.analyze(
            generated_at="2026-02-06T09:00:00+08:00",
            news_items=news,
            flow_series=flows,
        )

        self.assertEqual(result.news_total, 3)
        self.assertIn("finance", result.news_by_category)
        self.assertIn("a_share_northbound_net_inflow", result.flow_summary)
        self.assertEqual(
            result.flow_summary["a_share_northbound_net_inflow"].direction,
            "流入增强",
        )
        self.assertGreaterEqual(len(result.highlights), 1)


if __name__ == "__main__":
    unittest.main()
