import unittest

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, to_yfinance_symbol


class SymbolMapperTest(unittest.TestCase):
    def test_normalize_cn_symbol(self):
        self.assertEqual(normalize_symbol("600519", "CN"), "600519.SH")
        self.assertEqual(normalize_symbol("000001", "CN"), "000001.SZ")

    def test_normalize_hk_symbol(self):
        self.assertEqual(normalize_symbol("700", "HK"), "0700.HK")

    def test_yfinance_mapping(self):
        self.assertEqual(to_yfinance_symbol("600519", "CN"), "600519.SS")
        self.assertEqual(to_yfinance_symbol("AAPL", "US"), "AAPL")


if __name__ == "__main__":
    unittest.main()
