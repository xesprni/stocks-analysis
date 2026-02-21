import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig, DatabaseConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.infra.db.repos import MarketDataRepo
from market_reporter.infra.db.session import init_db, session_scope
from market_reporter.modules.market_data.service import MarketDataService


class _FailQuoteProvider:
    async def get_quote(self, symbol: str, market: str):
        raise RuntimeError("quote provider down")


class _BatchPartialProvider:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.single_calls: list[tuple[str, str]] = []

    async def get_quotes(self, items: list[tuple[str, str]]):
        self.batch_calls += 1
        if not items:
            return []
        symbol, market = items[0]
        return [
            Quote(
                symbol=symbol,
                market=market,
                ts="2026-02-06T10:01:00+00:00",
                price=101.0,
                change=1.0,
                change_percent=1.0,
                volume=11.0,
                currency="USD",
                source="batch",
            )
        ]

    async def get_quote(self, symbol: str, market: str):
        self.single_calls.append((symbol, market))
        return Quote(
            symbol=symbol,
            market=market,
            ts="2026-02-06T10:01:00+00:00",
            price=99.0,
            change=None,
            change_percent=None,
            volume=None,
            currency="USD",
            source="single",
        )


class _FailAllMarketDataProvider:
    async def get_quote(self, symbol: str, market: str):
        raise RuntimeError("provider failed")

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int):
        raise RuntimeError("provider failed")

    async def get_curve(self, symbol: str, market: str, window: str):
        raise RuntimeError("provider failed")


class _CompositeOkMarketDataProvider:
    async def get_quote(self, symbol: str, market: str):
        return Quote(
            symbol=symbol,
            market=market,
            ts="2026-02-06T10:01:00+00:00",
            price=4020.0,
            change=20.0,
            change_percent=0.5,
            volume=100.0,
            currency="USD",
            source="composite-ok",
        )

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int):
        return [
            KLineBar(
                symbol=symbol,
                market=market,
                interval=interval,
                ts="2026-02-06T10:01:00+00:00",
                open=4000.0,
                high=4030.0,
                low=3990.0,
                close=4020.0,
                volume=100.0,
                source="composite-ok",
            )
        ]


class _ResolveFallbackRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module == "market_data" and provider_id == "composite":
            return _FailQuoteProvider()
        raise ValueError(f"provider missing: {provider_id}")


class _FixedCompositeRegistry(ProviderRegistry):
    def __init__(self, provider) -> None:
        super().__init__()
        self.provider = provider

    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module == "market_data" and provider_id == "composite":
            return self.provider
        raise ValueError(f"provider missing: {provider_id}")


class _LongbridgeThenCompositeRegistry(ProviderRegistry):
    def resolve(self, module: str, provider_id: str, **kwargs):  # type: ignore[override]
        if module != "market_data":
            raise ValueError(f"unsupported module: {module}")
        if provider_id == "longbridge":
            return _FailAllMarketDataProvider()
        if provider_id == "composite":
            return _CompositeOkMarketDataProvider()
        raise ValueError(f"provider missing: {provider_id}")


class MarketDataServiceQuoteFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_quote_fallback_to_unavailable_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            init_db(config.database.url)
            service = MarketDataService(config=config, registry=ProviderRegistry())
            service._provider = lambda provider_id=None: _FailQuoteProvider()  # type: ignore[method-assign]

            quote = await service.get_quote(symbol="AAPL", market="US")
            self.assertEqual(quote.symbol, "AAPL")
            self.assertEqual(quote.market, "US")
            self.assertEqual(quote.price, 0.0)
            self.assertEqual(quote.source, "unavailable")
            self.assertEqual(quote.currency, "USD")

    async def test_quote_fallback_to_cached_curve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            init_db(config.database.url)
            with session_scope(config.database.url) as session:
                repo = MarketDataRepo(session)
                repo.save_curve_points(
                    [
                        CurvePoint(
                            symbol="AAPL",
                            market="US",
                            ts="2026-02-06T10:00:00+00:00",
                            price=100.0,
                            volume=10.0,
                            source="test",
                        ),
                        CurvePoint(
                            symbol="AAPL",
                            market="US",
                            ts="2026-02-06T10:01:00+00:00",
                            price=101.0,
                            volume=12.0,
                            source="test",
                        ),
                    ]
                )

            service = MarketDataService(config=config, registry=ProviderRegistry())
            service._provider = lambda provider_id=None: _FailQuoteProvider()  # type: ignore[method-assign]
            quote = await service.get_quote(symbol="AAPL", market="US")

            self.assertEqual(quote.price, 101.0)
            self.assertAlmostEqual(quote.change_percent or 0.0, 1.0, places=4)
            self.assertEqual(quote.source, "cache:test")

    async def test_quote_fallback_when_configured_provider_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            config.modules.market_data.default_provider = "broken-provider"
            init_db(config.database.url)
            service = MarketDataService(
                config=config, registry=_ResolveFallbackRegistry()
            )

            quote = await service.get_quote(symbol="AAPL", market="US")
            self.assertEqual(quote.symbol, "AAPL")
            self.assertEqual(quote.market, "US")
            self.assertEqual(quote.price, 0.0)
            self.assertEqual(quote.source, "unavailable")

    async def test_batch_quote_uses_provider_batch_then_single_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            provider = _BatchPartialProvider()
            service = MarketDataService(
                config=config,
                registry=_FixedCompositeRegistry(provider),
            )

            rows = await service.get_quotes(items=[("AAPL", "US"), ("TSLA", "US")])

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].source, "batch")
            self.assertEqual(rows[1].symbol, "TSLA")
            self.assertEqual(rows[1].source, "single")
            self.assertEqual(provider.batch_calls, 1)
            self.assertEqual(provider.single_calls, [("TSLA", "US")])

    async def test_quote_fallback_to_composite_when_default_provider_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            config.modules.market_data.default_provider = "longbridge"
            init_db(config.database.url)

            service = MarketDataService(
                config=config,
                registry=_LongbridgeThenCompositeRegistry(),
            )
            quote = await service.get_quote(symbol="^GSPC", market="US")

            self.assertEqual(quote.symbol, "^GSPC")
            self.assertEqual(quote.market, "US")
            self.assertEqual(quote.source, "composite-ok")

    async def test_kline_fallback_to_composite_when_default_provider_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            config.modules.market_data.default_provider = "longbridge"
            init_db(config.database.url)

            service = MarketDataService(
                config=config,
                registry=_LongbridgeThenCompositeRegistry(),
            )
            rows = await service.get_kline(
                symbol="^GSPC", market="US", interval="1d", limit=20
            )

            self.assertTrue(rows)
            self.assertEqual(rows[0].symbol, "^GSPC")
            self.assertEqual(rows[0].source, "composite-ok")


if __name__ == "__main__":
    unittest.main()
