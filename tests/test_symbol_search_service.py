import unittest

from market_reporter.modules.symbol_search.schemas import StockSearchResult
from market_reporter.modules.symbol_search.service import CompositeSymbolSearchProvider


class _FailProvider:
    async def search(self, query: str, market: str, limit: int):
        raise RuntimeError("provider failed")


class _OkProvider:
    async def search(self, query: str, market: str, limit: int):
        return [
            StockSearchResult(
                symbol="AAPL",
                market="US",
                name="Apple",
                exchange="NASDAQ",
                source="ok",
                score=0.95,
            )
        ]


class SymbolSearchServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_composite_fallback(self):
        provider = CompositeSymbolSearchProvider(
            providers={
                "yfinance": _FailProvider(),
                "akshare": _OkProvider(),
            }
        )
        rows = await provider.search(query="AAPL", market="US", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")


if __name__ == "__main__":
    unittest.main()
