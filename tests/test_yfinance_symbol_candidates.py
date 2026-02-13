import unittest

from market_reporter.modules.market_data.providers.yfinance_provider import (
    YahooFinanceMarketDataProvider,
)


class YFinanceSymbolCandidatesTest(unittest.TestCase):
    def test_hk_index_candidate_fallbacks(self):
        candidates = YahooFinanceMarketDataProvider._yfinance_symbol_candidates(
            symbol="^HSTECH", market="HK"
        )
        self.assertEqual(candidates[0], "^HSTECH")
        self.assertIn("HSTECH", candidates)
        self.assertIn("HSTECH.HK", candidates)

    def test_us_symbol_keeps_single_candidate(self):
        candidates = YahooFinanceMarketDataProvider._yfinance_symbol_candidates(
            symbol="AAPL", market="US"
        )
        self.assertEqual(candidates, ["AAPL"])


if __name__ == "__main__":
    unittest.main()
