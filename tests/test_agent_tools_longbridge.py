"""Tests for MarketTools and FundamentalsTools with Longbridge config."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.analysis.agent.tools.market_tools import MarketTools
from market_reporter.modules.analysis.agent.tools.fundamentals_tools import (
    FundamentalsTools,
)


def _lb_config(**overrides) -> LongbridgeConfig:
    defaults = {
        "enabled": True,
        "app_key": "key",
        "app_secret": "secret",
        "access_token": "token",
    }
    defaults.update(overrides)
    return LongbridgeConfig(**defaults)


class MarketToolsUseLongbridgeTest(unittest.TestCase):
    def test_use_longbridge_enabled(self):
        tools = MarketTools(lb_config=_lb_config())
        self.assertTrue(tools._use_longbridge)

    def test_use_longbridge_disabled(self):
        tools = MarketTools(lb_config=_lb_config(enabled=False))
        self.assertFalse(tools._use_longbridge)

    def test_use_longbridge_no_config(self):
        tools = MarketTools(lb_config=None)
        self.assertFalse(tools._use_longbridge)

    def test_use_longbridge_missing_key(self):
        tools = MarketTools(lb_config=_lb_config(app_key=""))
        self.assertFalse(tools._use_longbridge)

    def test_use_longbridge_missing_token(self):
        tools = MarketTools(lb_config=_lb_config(access_token=""))
        self.assertFalse(tools._use_longbridge)


class FundamentalsToolsUseLongbridgeTest(unittest.TestCase):
    def test_use_longbridge_enabled(self):
        tools = FundamentalsTools(lb_config=_lb_config())
        self.assertTrue(tools._use_longbridge)

    def test_use_longbridge_disabled(self):
        tools = FundamentalsTools(lb_config=_lb_config(enabled=False))
        self.assertFalse(tools._use_longbridge)

    def test_use_longbridge_no_config(self):
        tools = FundamentalsTools(lb_config=None)
        self.assertFalse(tools._use_longbridge)


class MarketToolsLongbridgePathTest(unittest.IsolatedAsyncioTestCase):
    @patch(
        "market_reporter.modules.analysis.agent.tools.market_tools.MarketTools._get_price_history_longbridge"
    )
    async def test_longbridge_path_chosen_when_enabled(self, mock_lb):
        from market_reporter.modules.analysis.agent.schemas import PriceHistoryResult

        mock_lb.return_value = PriceHistoryResult(
            symbol="AAPL",
            market="US",
            interval="1d",
            adjusted=True,
            bars=[],
            as_of="2026-02-20T00:00:00+00:00",
            source="longbridge",
            retrieved_at="2026-02-20T00:00:00+00:00",
            warnings=["empty_price_history"],
        )
        tools = MarketTools(lb_config=_lb_config())
        result = await tools.get_price_history(
            symbol="AAPL",
            start="2026-01-01",
            end="2026-02-20",
            interval="1d",
            adjusted=True,
            market="US",
        )
        mock_lb.assert_called_once()
        self.assertEqual(result.source, "longbridge")

    @patch(
        "market_reporter.modules.analysis.agent.tools.market_tools.MarketTools._get_price_history_sync"
    )
    async def test_yfinance_path_chosen_when_disabled(self, mock_yf):
        from market_reporter.modules.analysis.agent.schemas import PriceHistoryResult

        mock_yf.return_value = PriceHistoryResult(
            symbol="AAPL",
            market="US",
            interval="1d",
            adjusted=True,
            bars=[],
            as_of="2026-02-20T00:00:00+00:00",
            source="yfinance",
            retrieved_at="2026-02-20T00:00:00+00:00",
            warnings=["empty_price_history"],
        )
        tools = MarketTools(lb_config=None)
        result = await tools.get_price_history(
            symbol="AAPL",
            start="2026-01-01",
            end="2026-02-20",
            interval="1d",
            adjusted=True,
            market="US",
        )
        mock_yf.assert_called_once()
        self.assertEqual(result.source, "yfinance")


class FundamentalsToolsLongbridgePathTest(unittest.IsolatedAsyncioTestCase):
    @patch(
        "market_reporter.modules.analysis.agent.tools.fundamentals_tools.FundamentalsTools._get_fundamentals_longbridge"
    )
    async def test_longbridge_path_chosen_when_enabled(self, mock_lb):
        from market_reporter.modules.analysis.agent.schemas import FundamentalsResult

        mock_lb.return_value = FundamentalsResult(
            symbol="AAPL",
            market="US",
            metrics={"trailing_pe": 25.0},
            as_of="2026-02-20T00:00:00+00:00",
            source="longbridge",
            retrieved_at="2026-02-20T00:00:00+00:00",
            warnings=[],
        )
        tools = FundamentalsTools(lb_config=_lb_config())
        result = await tools.get_fundamentals(symbol="AAPL", market="US")
        mock_lb.assert_called_once()
        self.assertEqual(result.source, "longbridge")

    @patch(
        "market_reporter.modules.analysis.agent.tools.fundamentals_tools.FundamentalsTools._get_fundamentals_sync"
    )
    async def test_yfinance_path_chosen_when_disabled(self, mock_yf):
        from market_reporter.modules.analysis.agent.schemas import FundamentalsResult

        mock_yf.return_value = FundamentalsResult(
            symbol="AAPL",
            market="US",
            metrics={"trailing_pe": 25.0},
            as_of="2026-02-20T00:00:00+00:00",
            source="yfinance",
            retrieved_at="2026-02-20T00:00:00+00:00",
            warnings=[],
        )
        tools = FundamentalsTools(lb_config=None)
        result = await tools.get_fundamentals(symbol="AAPL", market="US")
        mock_yf.assert_called_once()
        self.assertEqual(result.source, "yfinance")


class FundamentalsToolsSafeFloatTest(unittest.TestCase):
    def test_safe_float_none(self):
        self.assertIsNone(FundamentalsTools._safe_float(None))

    def test_safe_float_number(self):
        self.assertAlmostEqual(FundamentalsTools._safe_float(25.5), 25.5)

    def test_safe_float_string(self):
        self.assertAlmostEqual(FundamentalsTools._safe_float("3.14"), 3.14)

    def test_safe_float_nan(self):
        self.assertIsNone(FundamentalsTools._safe_float(float("nan")))

    def test_safe_float_invalid_string(self):
        self.assertIsNone(FundamentalsTools._safe_float("not_a_number"))


if __name__ == "__main__":
    unittest.main()
