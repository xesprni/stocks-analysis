import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.symbol_search.providers.longbridge_search_provider import (
    LongbridgeSearchProvider,
)


def _lb_config(**overrides) -> LongbridgeConfig:
    defaults = {
        "enabled": True,
        "app_key": "test_key",
        "app_secret": "test_secret",
        "access_token": "test_token",
    }
    defaults.update(overrides)
    return LongbridgeConfig(**defaults)


def _security(symbol: str, **overrides):
    payload = {
        "symbol": symbol,
        "name_cn": "",
        "name_hk": "",
        "name_en": "",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class LongbridgeSymbolSearchProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_search_requires_enabled_credentials(self):
        provider = LongbridgeSearchProvider(LongbridgeConfig(enabled=False))

        with self.assertRaises(RuntimeError):
            await provider.search(query="AAPL", market="US", limit=10)

    async def test_search_rejects_redacted_credentials(self):
        provider = LongbridgeSearchProvider(
            _lb_config(app_secret="***", access_token="***")
        )

        with self.assertRaises(RuntimeError):
            await provider.search(query="AAPL", market="US", limit=10)

    async def test_search_us_symbol_normalizes_suffix(self):
        provider = LongbridgeSearchProvider(_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_security("AAPL.US")]
        mock_ctx.static_info.return_value = [_security("AAPL.US", name_en="Apple Inc.")]

        with patch.object(
            provider,
            "_ensure_ctx",
            return_value=mock_ctx,
        ):
            rows = await provider.search(query="AAPL", market="US", limit=10)

        mock_ctx.quote.assert_called_once_with(["AAPL.US"])
        mock_ctx.static_info.assert_called_once_with(["AAPL.US"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "AAPL")
        self.assertEqual(rows[0].market, "US")
        self.assertEqual(rows[0].name, "Apple Inc.")
        self.assertEqual(rows[0].source, "longbridge")

    async def test_search_hk_code_normalizes(self):
        provider = LongbridgeSearchProvider(_lb_config())
        mock_ctx = MagicMock()
        mock_ctx.quote.return_value = [_security("0700.HK")]
        mock_ctx.static_info.return_value = [_security("0700.HK", name_hk="腾讯控股")]

        with patch.object(provider, "_ensure_ctx", return_value=mock_ctx):
            rows = await provider.search(query="700", market="ALL", limit=10)

        mock_ctx.quote.assert_called_once_with(["0700.HK"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "0700.HK")
        self.assertEqual(rows[0].market, "HK")

    async def test_search_name_query_raises_for_fallback(self):
        provider = LongbridgeSearchProvider(_lb_config())

        with self.assertRaises(RuntimeError):
            await provider.search(query="腾讯", market="ALL", limit=10)


if __name__ == "__main__":
    unittest.main()
