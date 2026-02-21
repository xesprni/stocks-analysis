from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from market_reporter.modules.market_data.providers.yfinance_provider import (
    YahooFinanceMarketDataProvider,
)


class _FakeTickerNoFastPrice:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.fast_info = {
            "last_price": None,
            "regular_market_price": None,
            "previous_close": None,
            "currency": "USD",
        }

    def history(self, period: str, interval: str):
        index = pd.to_datetime(
            [
                datetime(2026, 2, 20, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 21, 0, 0, tzinfo=timezone.utc),
            ]
        )
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 104.0],
                "Low": [99.0, 100.0],
                "Close": [101.5, 103.0],
                "Volume": [1000.0, 1200.0],
            },
            index=index,
        )


class YahooFinanceProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_quote_falls_back_to_daily_history_when_fast_info_missing(self):
        fake_module = SimpleNamespace(Ticker=_FakeTickerNoFastPrice)
        with patch.dict("sys.modules", {"yfinance": fake_module}):
            provider = YahooFinanceMarketDataProvider()
            quote = await provider.get_quote("^GSPC", "US")

        self.assertEqual(quote.symbol, "^GSPC")
        self.assertEqual(quote.market, "US")
        self.assertAlmostEqual(quote.price, 103.0)
        self.assertAlmostEqual(quote.change, 1.5)
        self.assertAlmostEqual(quote.change_percent or 0.0, (1.5 / 101.5) * 100)
        self.assertEqual(quote.volume, 1200.0)
        self.assertEqual(quote.currency, "USD")


if __name__ == "__main__":
    unittest.main()
