import tempfile
import unittest
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.core.errors import ValidationError
from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import hash_password, init_db, session_scope
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

    def test_user_scoped_items_are_isolated(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        (root / "data").mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{root / 'data' / 'market_reporter.db'}"
        config = AppConfig(
            output_root=root / "output",
            config_file=root / "config" / "settings.yaml",
            database={"url": db_url},
        )
        init_db(config.database.url)

        with session_scope(config.database.url) as session:
            repo = UserRepo(session)
            user1 = repo.create(
                username="watch-u1", password_hash=hash_password("pw-1")
            )
            user2 = repo.create(
                username="watch-u2", password_hash=hash_password("pw-2")
            )
            user1_id = int(user1.id or 0)
            user2_id = int(user2.id or 0)

        service_u1 = WatchlistService(config, user_id=user1_id)
        service_u2 = WatchlistService(config, user_id=user2_id)
        service_global = WatchlistService(config)

        service_u1.add_item(symbol="600519", market="CN", alias="u1")
        service_u2.add_item(symbol="AAPL", market="US", alias="u2")

        items_u1 = service_u1.list_items()
        items_u2 = service_u2.list_items()
        items_global = service_global.list_items()

        self.assertEqual(len(items_u1), 1)
        self.assertEqual(len(items_u2), 1)
        self.assertEqual(len(items_global), 0)
        self.assertEqual(items_u1[0].alias, "u1")
        self.assertEqual(items_u2[0].alias, "u2")


if __name__ == "__main__":
    unittest.main()
