import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.core.errors import ValidationError
from market_reporter.infra.db.session import init_db
from market_reporter.modules.watchlist.service import WatchlistService


class WatchlistServiceTest(unittest.TestCase):
    def _create_service(self):
        tmpdir = tempfile.TemporaryDirectory()
        root = Path(tmpdir.name)
        (root / "data").mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
        config = AppConfig(
            output_root=root / "output",
            config_file=root / "config" / "settings.yaml",
            database={"url": db_url},
        )
        init_db(config.database.url)
        return WatchlistService(config), tmpdir

    def test_add_item_normalizes_cn_bj_symbol(self):
        service, tmpdir = self._create_service()
        self.addCleanup(tmpdir.cleanup)

        item = service.add_item(
            symbol="430047",
            market="cn",
            alias="test",
        )

        self.assertEqual(item.symbol, "430047.BJ")
        self.assertEqual(item.market, "CN")

    def test_add_item_rejects_duplicate_symbol_in_same_market(self):
        service, tmpdir = self._create_service()
        self.addCleanup(tmpdir.cleanup)

        service.add_item(symbol="600519", market="CN", alias=None)

        with self.assertRaises(ValidationError):
            service.add_item(symbol="600519.SS", market="CN", alias=None)

    def test_add_item_allows_same_input_in_different_markets(self):
        service, tmpdir = self._create_service()
        self.addCleanup(tmpdir.cleanup)

        cn = service.add_item(symbol="000001", market="CN", alias=None)
        hk = service.add_item(symbol="000001", market="HK", alias=None)

        self.assertEqual(cn.symbol, "000001.SZ")
        self.assertEqual(hk.symbol, "000001.HK")


if __name__ == "__main__":
    unittest.main()
