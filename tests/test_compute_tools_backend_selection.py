from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from market_reporter.modules.analysis.agent.tools.compute_tools import ComputeTools
from market_reporter.modules.analysis.agent.tools.fundamentals_tools import (
    FundamentalsTools,
)


class ComputeToolsBackendSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compute = ComputeTools(fundamentals_tools=FundamentalsTools())

    @staticmethod
    def _build_bars(start: datetime, points: int = 90) -> list[dict]:
        bars: list[dict] = []
        close = 100.0
        for idx in range(points):
            close += 0.5
            open_v = close - 0.3
            high_v = close + 0.8
            low_v = close - 0.9
            bars.append(
                {
                    "ts": (start + timedelta(days=idx)).isoformat(timespec="seconds"),
                    "open": round(open_v, 4),
                    "high": round(high_v, 4),
                    "low": round(low_v, 4),
                    "close": round(close, 4),
                    "volume": 1000 + idx * 10,
                }
            )
        return bars

    def test_prefers_talib_when_available(self):
        bars = self._build_bars(datetime(2025, 1, 1))
        with (
            patch.object(
                ComputeTools,
                "_compute_with_talib",
                return_value=({"rsi_14": 55.0, "macd": 1.2}, []),
            ),
            patch.object(
                ComputeTools,
                "_compute_with_pandas_ta",
                return_value=({"rsi_14": 40.0, "macd": -0.4}, []),
            ),
        ):
            result = self.compute.compute_indicators(
                price_df={"1d": bars}, symbol="AAPL"
            )

        self.assertEqual(result.source, "ta-lib/computed")

    def test_falls_back_to_pandas_ta_when_talib_unavailable(self):
        bars = self._build_bars(datetime(2025, 1, 1))
        with (
            patch.object(
                ComputeTools,
                "_compute_with_talib",
                return_value=({}, ["talib_unavailable_fallback"]),
            ),
            patch.object(
                ComputeTools,
                "_compute_with_pandas_ta",
                return_value=({"rsi_14": 52.5}, []),
            ),
        ):
            result = self.compute.compute_indicators(
                price_df={"1d": bars}, symbol="AAPL"
            )

        self.assertEqual(result.source, "pandas-ta/computed")
        self.assertIn("talib_unavailable_fallback", result.warnings)

    def test_falls_back_to_builtin_when_all_ta_backends_unavailable(self):
        bars = self._build_bars(datetime(2025, 1, 1))
        with (
            patch.object(
                ComputeTools,
                "_compute_with_talib",
                return_value=({}, ["talib_unavailable_fallback"]),
            ),
            patch.object(
                ComputeTools,
                "_compute_with_pandas_ta",
                return_value=({}, ["pandas_ta_unavailable_fallback"]),
            ),
        ):
            result = self.compute.compute_indicators(
                price_df={"1d": bars}, symbol="AAPL"
            )

        self.assertEqual(result.source, "builtin/computed")
        self.assertIn("talib_unavailable_fallback", result.warnings)
        self.assertIn("pandas_ta_unavailable_fallback", result.warnings)
        self.assertIn("indicator_backend_builtin_fallback", result.warnings)
        self.assertIn("close", result.values)
        self.assertIn("rsi_14", result.values)


if __name__ == "__main__":
    unittest.main()
