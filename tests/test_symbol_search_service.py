import unittest

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.symbol_search.schemas import StockSearchResult
from market_reporter.modules.symbol_search.service import CompositeSymbolSearchProvider, SymbolSearchService


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


class _ResolveFallbackRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module == "symbol_search" and provider_id == "composite":
            return _OkProvider()
        raise ValueError(f"provider missing: {provider_id}")


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

    async def test_composite_all_failed_returns_empty(self):
        provider = CompositeSymbolSearchProvider(
            providers={
                "yfinance": _FailProvider(),
                "akshare": _FailProvider(),
            }
        )
        rows = await provider.search(query="AAPL", market="US", limit=5)
        self.assertEqual(rows, [])

    async def test_search_fallback_when_configured_provider_missing(self):
        config = AppConfig()
        config.symbol_search.default_provider = "broken-provider"
        service = SymbolSearchService(config=config, registry=_ResolveFallbackRegistry())
        rows = await service.search(query="AAPL", market="US", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")


if __name__ == "__main__":
    unittest.main()
