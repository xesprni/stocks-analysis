import unittest

from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    strip_market_suffix,
    to_yfinance_symbol,
)


class SymbolMapperTest(unittest.TestCase):
    def test_normalize_cn_symbol(self):
        self.assertEqual(normalize_symbol("600519", "CN"), "600519.SH")
        self.assertEqual(normalize_symbol("000001", "CN"), "000001.SZ")
        self.assertEqual(normalize_symbol("430047", "CN"), "430047.BJ")
        self.assertEqual(normalize_symbol("600519.SS", "CN"), "600519.SH")

    def test_normalize_hk_symbol(self):
        self.assertEqual(normalize_symbol("700", "HK"), "0700.HK")

    def test_yfinance_mapping(self):
        self.assertEqual(to_yfinance_symbol("600519", "CN"), "600519.SS")
        self.assertEqual(to_yfinance_symbol("430047.BJ", "CN"), "430047.BJ")
        self.assertEqual(to_yfinance_symbol("AAPL", "US"), "AAPL")

    def test_strip_market_suffix(self):
        self.assertEqual(strip_market_suffix("600519.SH"), "600519")
        self.assertEqual(strip_market_suffix("430047.BJ"), "430047")
        self.assertEqual(strip_market_suffix("0700.HK"), "0700")


if __name__ == "__main__":
    unittest.main()
