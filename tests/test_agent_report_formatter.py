import unittest

from market_reporter.modules.analysis.agent.report_formatter import (
    AgentReportFormatter,
)
from market_reporter.modules.analysis.agent.schemas import RuntimeDraft


class AgentReportFormatterTest(unittest.TestCase):
    def test_build_market_technical_formats_strategy_range(self):
        text = AgentReportFormatter._build_market_technical(
            mode="stock",
            tool_results={
                "compute_indicators": {
                    "as_of": "2026-03-02T13:00:00",
                    "trend": {
                        "primary": {
                            "ma": {"state": "mixed"},
                            "macd": {"cross": "none"},
                            "bollinger": {"status": "revert_mid"},
                        }
                    },
                    "momentum": {
                        "primary": {
                            "rsi": {"value": 42.88, "status": "neutral"},
                            "kdj": {"status": "extreme_up"},
                            "divergence": {"type": "bullish"},
                        }
                    },
                    "volume_price": {
                        "primary": {
                            "volume_ratio": 0.7139,
                            "shrink_pullback": True,
                            "volume_breakout": False,
                            "atr_14": 2.89,
                        }
                    },
                    "patterns": {"primary": {"recent": []}},
                    "support_resistance": {"primary": {"supports": [], "resistances": []}},
                    "strategy": {
                        "score": 58.55,
                        "stance": "neutral",
                        "position_size": 50,
                        "entry_zone": {"low": 101.63, "high": 102.65},
                        "stop_loss": 100.02,
                        "take_profit": 103.41,
                    },
                }
            },
        )

        self.assertIn("entry_zone=101.63 ~ 102.65", text)
        self.assertIn("缩量回调: 是", text)
        self.assertNotIn("{'low':", text)

    def test_build_fundamentals_skips_missing_metrics(self):
        text = AgentReportFormatter._build_fundamentals(
            mode="stock",
            tool_results={
                "get_fundamentals_info": {
                    "metrics": {
                        "revenue": None,
                        "net_income": None,
                        "trailing_pe": 10.29,
                        "pb_ratio": 2.66,
                    }
                },
                "get_financial_reports": {"latest_metrics": {}},
            },
        )

        self.assertEqual(text, "TTM PE: 10.29；PB: 2.66。")
        self.assertNotIn("None", text)

    def test_build_catalysts_and_risks_uses_web_results_when_news_fallback(self):
        text = AgentReportFormatter._build_catalysts_and_risks(
            runtime_draft=RuntimeDraft(
                summary="summary",
                sentiment="neutral",
                risks=[],
                action_items=[],
                conclusions=[],
                scenario_assumptions={},
                markdown="",
            ),
            tool_results={
                "search_news": {
                    "warnings": [
                        "no_news_matched",
                        "news_fallback_recent_headlines",
                    ],
                    "items": [
                        {
                            "published_at": "2026-03-02T10:00:00+00:00",
                            "title": "Generic market headline",
                        }
                    ],
                },
                "search_web": {
                    "items": [
                        {
                            "published_at": "2026-03-02T11:00:00+00:00",
                            "title": "PDD earnings outlook update",
                        }
                    ]
                },
            },
            guardrail_issues=[],
        )

        self.assertIn("未命中标的相关新闻", text)
        self.assertIn("PDD earnings outlook update", text)
        self.assertNotIn("Generic market headline", text)


if __name__ == "__main__":
    unittest.main()
