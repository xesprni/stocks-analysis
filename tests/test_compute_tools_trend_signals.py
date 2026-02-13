from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from market_reporter.modules.agent.tools.compute_tools import ComputeTools
from market_reporter.modules.agent.tools.fundamentals_tools import FundamentalsTools


class ComputeToolsTrendSignalsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compute = ComputeTools(fundamentals_tools=FundamentalsTools())

    @staticmethod
    def _build_bars(prices: list[float], start: datetime) -> list[dict]:
        bars: list[dict] = []
        for idx, close in enumerate(prices):
            open_v = prices[idx - 1] if idx > 0 else close
            high_v = max(open_v, close) * 1.01
            low_v = min(open_v, close) * 0.99
            bars.append(
                {
                    "ts": (start + timedelta(days=idx)).isoformat(timespec="seconds"),
                    "open": round(open_v, 4),
                    "high": round(high_v, 4),
                    "low": round(low_v, 4),
                    "close": round(close, 4),
                    "volume": 1000 + idx * 5,
                }
            )
        return bars

    def test_trend_structure_and_strategy_output(self):
        prices = [100 + idx * 0.8 for idx in range(90)]
        bars = self._build_bars(prices, datetime(2025, 1, 1))

        result = self.compute.compute_indicators(
            price_df={"1d": bars, "5m": bars[-70:]},
            indicators=["MA", "MACD", "RSI"],
            symbol="AAPL",
            indicator_profile="trend",
        )

        self.assertEqual(result.symbol, "AAPL")
        self.assertIn("primary", result.trend)
        self.assertIn("ma", result.trend["primary"])
        self.assertEqual(result.trend["primary"]["ma"]["state"], "bullish")
        self.assertIn(result.trend["primary"]["macd"]["cross"], {"none", "golden_cross", "dead_cross"})
        self.assertIn(result.trend["primary"]["bollinger"]["status"], {"inside_band", "above_mid", "breakout_up", "breakout_down", "revert_mid"})

        self.assertIn("score", result.strategy)
        self.assertIn("stance", result.strategy)
        self.assertIn("position_size", result.strategy)
        self.assertIn(result.strategy["stance"], {"bullish", "neutral", "bearish"})

        self.assertIn("close", result.values)
        self.assertIn("macd", result.values)

    def test_macd_cross_helper(self):
        self.assertEqual(self.compute._macd_cross([-0.3, 0.2], [-0.1, 0.0]), "golden_cross")
        self.assertEqual(self.compute._macd_cross([0.2, -0.3], [0.1, 0.0]), "dead_cross")
        self.assertEqual(self.compute._macd_cross([0.1, 0.2], [0.0, 0.1]), "none")


if __name__ == "__main__":
    unittest.main()
