"""Tests for the Longbridge market data provider.

All Longbridge SDK calls are mocked so no network or credentials are needed.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.market_data.providers.longbridge_provider import (
    LongbridgeMarketDataProvider,
)


def _make_lb_config(**overrides) -> LongbridgeConfig:
    defaults = {
        "enabled": True,
        "app_key": "test_key",
        "app_secret": "test_secret",
        "access_token": "test_token",
    }
    defaults.update(overrides)
    return LongbridgeConfig(**defaults)


def _make_quote(**overrides):
    ts = datetime(2026, 2, 20, 10, 30, 0, tzinfo=timezone.utc)
    defaults = {
        "last_done": 150.25,
        "prev_close": 148.50,
        "volume": 1_000_000,
        "timestamp": ts,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_candlestick(**overrides):
    ts = datetime(2026, 2, 20, 0, 0, 0, tzinfo=timezone.utc)
    defaults = {
        "open": 148.0,
        "high": 151.0,
        "low": 147.5,
        "close": 150.0,
        "volume": 500_000,
        "timestamp": ts,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_intraday_line(**overrides):
    ts = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    defaults = {
        "price": 150.0,
        "volume": 100_000,
        "timestamp": ts,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class LongbridgeProviderQuoteTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_quote_us_symbol(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_make_quote()]
        provider._ctx = mock_ctx

        quote = await provider.get_quote("AAPL", "US")

        mock_ctx.quote.assert_called_once_with(["AAPL.US"])
        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.market, "US")
        self.assertAlmostEqual(quote.price, 150.25)
        self.assertAlmostEqual(quote.change, 150.25 - 148.50)
        expected_pct = (150.25 - 148.50) / 148.50 * 100
        self.assertAlmostEqual(quote.change_percent, expected_pct, places=4)
        self.assertEqual(quote.volume, 1_000_000.0)
        self.assertEqual(quote.currency, "USD")
        self.assertEqual(quote.source, "longbridge")

    async def test_get_quote_cn_symbol(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_make_quote(last_done=18.5, prev_close=18.0)]
        provider._ctx = mock_ctx

        quote = await provider.get_quote("600519", "CN")

        mock_ctx.quote.assert_called_once_with(["600519.SH"])
        self.assertEqual(quote.symbol, "600519.SH")
        self.assertEqual(quote.market, "CN")
        self.assertEqual(quote.currency, "CNY")

    async def test_get_quote_hk_symbol(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_make_quote(last_done=350.0, prev_close=345.0)]
        provider._ctx = mock_ctx

        quote = await provider.get_quote("0700", "HK")

        mock_ctx.quote.assert_called_once_with(["0700.HK"])
        self.assertEqual(quote.symbol, "0700.HK")
        self.assertEqual(quote.market, "HK")
        self.assertEqual(quote.currency, "HKD")

    async def test_get_quotes_batch(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [
            SimpleNamespace(
                symbol="AAPL.US",
                last_done=150.0,
                prev_close=148.0,
                volume=100,
                timestamp=datetime(2026, 2, 20, 10, 30, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                symbol="0700.HK",
                last_done=300.0,
                prev_close=295.0,
                volume=200,
                timestamp=datetime(2026, 2, 20, 10, 31, 0, tzinfo=timezone.utc),
            ),
        ]
        provider._ctx = mock_ctx

        rows = await provider.get_quotes([("AAPL", "US"), ("700", "HK")])

        mock_ctx.quote.assert_called_once_with(["AAPL.US", "0700.HK"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].symbol, "AAPL")
        self.assertEqual(rows[0].market, "US")
        self.assertEqual(rows[1].symbol, "0700.HK")
        self.assertEqual(rows[1].market, "HK")

    async def test_get_quote_no_prev_close(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_make_quote(prev_close=None)]
        provider._ctx = mock_ctx

        quote = await provider.get_quote("AAPL", "US")
        self.assertIsNone(quote.change)
        self.assertIsNone(quote.change_percent)

    async def test_get_quote_empty_raises(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = []
        provider._ctx = mock_ctx

        with self.assertRaises(ValueError):
            await provider.get_quote("AAPL", "US")


class LongbridgeProviderKlineTest(unittest.IsolatedAsyncioTestCase):
    @patch(
        "market_reporter.modules.market_data.providers.longbridge_provider.LongbridgeMarketDataProvider._map_period"
    )
    async def test_get_kline_returns_bars(self, mock_map):
        # Mock Period enum value
        mock_period = MagicMock()
        mock_map.return_value = mock_period

        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.candlesticks.return_value = [
            _make_candlestick(),
            _make_candlestick(
                open=150.0,
                high=153.0,
                low=149.0,
                close=152.0,
                volume=600_000,
                timestamp=datetime(2026, 2, 21, 0, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        provider._ctx = mock_ctx

        bars = await provider.get_kline("AAPL", "US", "1d", 10)

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].symbol, "AAPL")
        self.assertEqual(bars[0].market, "US")
        self.assertEqual(bars[0].interval, "1d")
        self.assertAlmostEqual(bars[0].open, 148.0)
        self.assertAlmostEqual(bars[0].close, 150.0)
        self.assertAlmostEqual(bars[1].close, 152.0)
        self.assertEqual(bars[0].source, "longbridge")

    @patch(
        "market_reporter.modules.market_data.providers.longbridge_provider.LongbridgeMarketDataProvider._map_period"
    )
    async def test_get_kline_unsupported_interval(self, mock_map):
        mock_map.return_value = None
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        provider._ctx = MagicMock()

        with self.assertRaises(ValueError):
            await provider.get_kline("AAPL", "US", "3m", 10)


class LongbridgeProviderCurveTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_curve_returns_points(self):
        provider = LongbridgeMarketDataProvider(_make_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.intraday.return_value = [
            _make_intraday_line(price=149.5, volume=80_000),
            _make_intraday_line(
                price=150.5,
                volume=120_000,
                timestamp=datetime(2026, 2, 20, 10, 1, 0, tzinfo=timezone.utc),
            ),
        ]
        provider._ctx = mock_ctx

        points = await provider.get_curve("AAPL", "US", "1d")

        mock_ctx.intraday.assert_called_once_with("AAPL.US")
        self.assertEqual(len(points), 2)
        self.assertAlmostEqual(points[0].price, 149.5)
        self.assertAlmostEqual(points[1].price, 150.5)
        self.assertEqual(points[0].source, "longbridge")


class LongbridgeProviderCurrencyTest(unittest.TestCase):
    def test_currency_by_market(self):
        self.assertEqual(LongbridgeMarketDataProvider._currency_by_market("CN"), "CNY")
        self.assertEqual(LongbridgeMarketDataProvider._currency_by_market("HK"), "HKD")
        self.assertEqual(LongbridgeMarketDataProvider._currency_by_market("US"), "USD")
        self.assertEqual(LongbridgeMarketDataProvider._currency_by_market("JP"), "")


if __name__ == "__main__":
    unittest.main()
