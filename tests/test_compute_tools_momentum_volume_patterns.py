from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from market_reporter.modules.analysis.agent.tools.compute_tools import ComputeTools
from market_reporter.modules.analysis.agent.tools.fundamentals_tools import (
    FundamentalsTools,
)


class ComputeToolsMomentumVolumePatternsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compute = ComputeTools(fundamentals_tools=FundamentalsTools())

    @staticmethod
    def _build_base_bars() -> list[dict]:
        bars: list[dict] = []
        start = datetime(2025, 6, 1)
        close = 100.0
        for idx in range(70):
            close += 0.18
            open_v = close - 0.12
            high_v = close + 0.45
            low_v = close - 0.45
            bars.append(
                {
                    "ts": (start + timedelta(days=idx)).isoformat(timespec="seconds"),
                    "open": round(open_v, 4),
                    "high": round(high_v, 4),
                    "low": round(low_v, 4),
                    "close": round(close, 4),
                    "volume": 1200 + idx * 10,
                }
            )

        # bearish candle
        prev_ts = start + timedelta(days=70)
        bars.append(
            {
                "ts": prev_ts.isoformat(timespec="seconds"),
                "open": 115.0,
                "high": 116.0,
                "low": 112.0,
                "close": 113.0,
                "volume": 1100.0,
            }
        )
        # bullish engulfing
        bars.append(
            {
                "ts": (prev_ts + timedelta(days=1)).isoformat(timespec="seconds"),
                "open": 112.0,
                "high": 117.0,
                "low": 111.0,
                "close": 116.5,
                "volume": 2200.0,
            }
        )
        # doji-like candle
        bars.append(
            {
                "ts": (prev_ts + timedelta(days=2)).isoformat(timespec="seconds"),
                "open": 116.4,
                "high": 118.0,
                "low": 115.8,
                "close": 116.43,
                "volume": 2400.0,
            }
        )
        # hammer-like candle with bigger volume
        bars.append(
            {
                "ts": (prev_ts + timedelta(days=3)).isoformat(timespec="seconds"),
                "open": 116.3,
                "high": 117.1,
                "low": 112.0,
                "close": 116.8,
                "volume": 5000.0,
            }
        )
        return bars

    def test_momentum_volume_and_pattern_fields(self):
        bars = self._build_base_bars()
        result = self.compute.compute_indicators(
            price_df={"1d": bars},
            indicators=["RSI", "KDJ", "VOL"],
            symbol="TEST",
        )

        momentum = result.momentum.get("primary", {})
        self.assertIn("rsi", momentum)
        self.assertIn("kdj", momentum)
        self.assertIn("divergence", momentum)
        self.assertIn(
            momentum.get("rsi", {}).get("status"),
            {"overbought", "oversold", "neutral", "unknown"},
        )

        volume_price = result.volume_price.get("primary", {})
        self.assertIn("volume_ratio", volume_price)
        self.assertIn("shrink_pullback", volume_price)
        self.assertIn("volume_breakout", volume_price)
        self.assertIsNotNone(volume_price.get("volume_ratio"))

        patterns = result.patterns.get("primary", {})
        recent = patterns.get("recent", [])
        self.assertTrue(isinstance(recent, list))
        self.assertGreater(len(recent), 0)
        pattern_types = {item.get("type") for item in recent if isinstance(item, dict)}
        self.assertTrue(pattern_types.intersection({"hammer", "engulfing", "doji"}))


if __name__ == "__main__":
    unittest.main()
