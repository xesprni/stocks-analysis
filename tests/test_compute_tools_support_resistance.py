from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta

from market_reporter.modules.agent.tools.compute_tools import ComputeTools
from market_reporter.modules.agent.tools.fundamentals_tools import FundamentalsTools


class ComputeToolsSupportResistanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compute = ComputeTools(fundamentals_tools=FundamentalsTools())

    @staticmethod
    def _build_bars() -> list[dict]:
        bars: list[dict] = []
        start = datetime(2025, 3, 1)
        for idx in range(120):
            base = 100 + math.sin(idx / 5.0) * 4.0 + math.sin(idx / 13.0) * 2.0
            close = base + math.sin(idx / 3.0) * 0.7
            open_v = close - 0.3
            high_v = close + 1.2
            low_v = close - 1.2
            bars.append(
                {
                    "ts": (start + timedelta(days=idx)).isoformat(timespec="seconds"),
                    "open": round(open_v, 4),
                    "high": round(high_v, 4),
                    "low": round(low_v, 4),
                    "close": round(close, 4),
                    "volume": 1600 + (idx % 10) * 20,
                }
            )
        return bars

    def test_support_resistance_levels_are_labeled(self):
        bars = self._build_bars()
        result = self.compute.compute_indicators(price_df={"1d": bars}, symbol="LEVELS")

        sr = result.support_resistance.get("primary", {})
        supports = sr.get("supports", [])
        resistances = sr.get("resistances", [])
        self.assertLessEqual(len(supports), 3)
        self.assertLessEqual(len(resistances), 3)

        for idx, row in enumerate(supports):
            self.assertEqual(row.get("level"), f"S{idx + 1}")
            self.assertIsNotNone(row.get("price"))
        for idx, row in enumerate(resistances):
            self.assertEqual(row.get("level"), f"R{idx + 1}")
            self.assertIsNotNone(row.get("price"))

        touch_counts = sr.get("pivot_meta", {}).get("touch_counts", {})
        self.assertIsInstance(touch_counts, dict)


if __name__ == "__main__":
    unittest.main()
