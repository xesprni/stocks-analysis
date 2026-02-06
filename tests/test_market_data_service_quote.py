import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import CurvePoint
from market_reporter.infra.db.repos import MarketDataRepo
from market_reporter.infra.db.session import init_db, session_scope
from market_reporter.modules.market_data.service import MarketDataService


class _FailQuoteProvider:
    async def get_quote(self, symbol: str, market: str):
        raise RuntimeError("quote provider down")


class MarketDataServiceQuoteFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_quote_fallback_to_unavailable_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": db_url},
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
                database={"url": db_url},
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


if __name__ == "__main__":
    unittest.main()
