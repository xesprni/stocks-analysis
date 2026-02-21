import unittest

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.symbol_search.schemas import StockSearchResult
from market_reporter.modules.symbol_search.service import (
    CompositeSymbolSearchProvider,
    SymbolSearchService,
)


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


class _EmptyProvider:
    async def search(self, query: str, market: str, limit: int):
        return []


class _ResolveFallbackRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module == "symbol_search" and provider_id == "composite":
            return _OkProvider()
        raise ValueError(f"provider missing: {provider_id}")


class _LongbridgeDownRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module != "symbol_search":
            raise ValueError(f"unsupported module: {module}")
        if provider_id == "longbridge":
            return _FailProvider()
        if provider_id == "finnhub":
            return _OkProvider()
        if provider_id == "composite":
            return _OkProvider()
        raise ValueError(f"provider missing: {provider_id}")


class _AliasOnlyRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module != "symbol_search":
            raise ValueError(f"unsupported module: {module}")
        if provider_id in {"composite", "longbridge", "finnhub", "yfinance", "akshare"}:
            return _EmptyProvider()
        raise ValueError(f"provider missing: {provider_id}")


class SymbolSearchServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_resolve_search_market_from_all(self):
        self.assertEqual(
            SymbolSearchService._resolve_search_market("AAPL", "ALL"), "US"
        )
        self.assertEqual(SymbolSearchService._resolve_search_market("700", "ALL"), "HK")
        self.assertEqual(
            SymbolSearchService._resolve_search_market("600519", "ALL"), "CN"
        )

    async def test_composite_fallback(self):
        provider = CompositeSymbolSearchProvider(
            providers={
                "longbridge": _OkProvider(),
                "finnhub": _FailProvider(),
            }
        )
        rows = await provider.search(query="AAPL", market="US", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")

    async def test_composite_all_failed_returns_empty(self):
        provider = CompositeSymbolSearchProvider(
            providers={
                "longbridge": _FailProvider(),
            }
        )
        rows = await provider.search(query="AAPL", market="US", limit=5)
        self.assertEqual(rows, [])

    async def test_search_fallback_when_configured_provider_missing(self):
        config = AppConfig()
        config.symbol_search.default_provider = "broken-provider"
        service = SymbolSearchService(
            config=config, registry=_ResolveFallbackRegistry()
        )
        rows = await service.search(query="AAPL", market="US", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")

    async def test_search_fallback_when_longbridge_provider_fails(self):
        config = AppConfig()
        config.symbol_search.default_provider = "longbridge"
        service = SymbolSearchService(config=config, registry=_LongbridgeDownRegistry())
        rows = await service.search(query="AAPL", market="US", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")

    async def test_search_returns_empty_for_incompatible_market_query(self):
        config = AppConfig()
        config.symbol_search.default_provider = "composite"
        service = SymbolSearchService(
            config=config, registry=_ResolveFallbackRegistry()
        )
        rows = await service.search(query="700", market="US", limit=5)
        self.assertEqual(rows, [])

    async def test_search_resolves_us_index_alias_for_cjk_query(self):
        config = AppConfig()
        config.symbol_search.default_provider = "composite"
        service = SymbolSearchService(config=config, registry=_AliasOnlyRegistry())

        rows = await service.search(query="标普", market="US", limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0].symbol, "^GSPC")
        self.assertEqual(rows[0].market, "US")

    async def test_search_resolves_us_index_alias_in_all_market(self):
        config = AppConfig()
        config.symbol_search.default_provider = "composite"
        service = SymbolSearchService(config=config, registry=_AliasOnlyRegistry())

        rows = await service.search(query="纳斯达克", market="ALL", limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0].symbol, "^IXIC")
        self.assertEqual(rows[0].market, "US")

    async def test_search_does_not_generate_invalid_cn_symbol_from_cjk_name(self):
        config = AppConfig()
        config.symbol_search.default_provider = "composite"
        service = SymbolSearchService(config=config, registry=_AliasOnlyRegistry())

        rows = await service.search(query="药明康德", market="CN", limit=5)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
