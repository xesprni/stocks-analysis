from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import Quote
from market_reporter.modules.dashboard.service import DashboardService
from market_reporter.modules.watchlist.schemas import WatchlistItem


class _FakeMarketDataService:
    def __init__(self, fail_keys: set[tuple[str, str]] | None = None) -> None:
        self.fail_keys = fail_keys or set()

    async def get_quote(self, symbol: str, market: str) -> Quote:
        key = (symbol, market)
        if key in self.fail_keys:
            raise RuntimeError("quote failed")
        return Quote(
            symbol=symbol,
            market=market,
            ts="2026-02-13T00:00:00+00:00",
            price=123.45,
            change=1.2,
            change_percent=0.98,
            volume=1000,
            currency="USD" if market == "US" else "CNY",
            source="mock",
        )


class _FakeWatchlistService:
    def __init__(self, items: list[WatchlistItem]) -> None:
        self.items = items

    def list_items(self) -> list[WatchlistItem]:
        return list(self.items)

    def list_enabled_items(self) -> list[WatchlistItem]:
        return [item for item in self.items if item.enabled]


class DashboardServiceTest(unittest.IsolatedAsyncioTestCase):
    def _build_config(self) -> AppConfig:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            return AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database={"url": f"sqlite:///{root / 'data' / 'market_reporter.db'}"},
            )

    def _build_item(self, idx: int, enabled: bool = True) -> WatchlistItem:
        return WatchlistItem(
            id=idx,
            symbol=f"T{idx}",
            market="US",
            alias=f"Alias-{idx}",
            display_name=f"Name-{idx}",
            keywords=[],
            enabled=enabled,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    async def test_pagination_total_zero_and_overflow_page(self):
        config = self._build_config()
        service = DashboardService(
            config=config,
            registry=ProviderRegistry(),
            market_data_service=_FakeMarketDataService(),
            watchlist_service=_FakeWatchlistService(items=[]),
        )
        empty_snapshot = await service.get_snapshot(page=1, page_size=10, enabled_only=True)
        self.assertEqual(empty_snapshot.pagination.total, 0)
        self.assertEqual(empty_snapshot.pagination.total_pages, 0)
        self.assertEqual(empty_snapshot.watchlist, [])

        items = [self._build_item(idx=i + 1) for i in range(13)]
        paged_service = DashboardService(
            config=config,
            registry=ProviderRegistry(),
            market_data_service=_FakeMarketDataService(),
            watchlist_service=_FakeWatchlistService(items=items),
        )
        page2 = await paged_service.get_snapshot(page=2, page_size=10, enabled_only=True)
        overflow = await paged_service.get_snapshot(page=3, page_size=10, enabled_only=True)
        self.assertEqual(page2.pagination.total, 13)
        self.assertEqual(page2.pagination.total_pages, 2)
        self.assertEqual(len(page2.watchlist), 3)
        self.assertEqual(len(overflow.watchlist), 0)

    async def test_split_index_and_watchlist_snapshots(self):
        config = self._build_config()
        items = [self._build_item(idx=i + 1) for i in range(5)]
        service = DashboardService(
            config=config,
            registry=ProviderRegistry(),
            market_data_service=_FakeMarketDataService(),
            watchlist_service=_FakeWatchlistService(items=items),
        )

        index_snapshot = await service.get_index_snapshot(enabled_only=True)
        watchlist_snapshot = await service.get_watchlist_snapshot(
            page=2,
            page_size=2,
            enabled_only=True,
        )

        self.assertGreaterEqual(len(index_snapshot.indices), 1)
        self.assertEqual(index_snapshot.auto_refresh_enabled, config.dashboard.auto_refresh_enabled)
        self.assertEqual(watchlist_snapshot.pagination.total, 5)
        self.assertEqual(watchlist_snapshot.pagination.total_pages, 3)
        self.assertEqual(len(watchlist_snapshot.watchlist), 2)

    async def test_enabled_only_filters_watchlist(self):
        config = self._build_config()
        service = DashboardService(
            config=config,
            registry=ProviderRegistry(),
            market_data_service=_FakeMarketDataService(),
            watchlist_service=_FakeWatchlistService(
                items=[self._build_item(1, enabled=True), self._build_item(2, enabled=False)]
            ),
        )
        enabled_snapshot = await service.get_snapshot(page=1, page_size=10, enabled_only=True)
        all_snapshot = await service.get_snapshot(page=1, page_size=10, enabled_only=False)
        self.assertEqual(len(enabled_snapshot.watchlist), 1)
        self.assertEqual(enabled_snapshot.watchlist[0].id, 1)
        self.assertEqual(len(all_snapshot.watchlist), 2)

    async def test_index_and_watchlist_quote_fallback_to_unavailable(self):
        config = self._build_config()
        service = DashboardService(
            config=config,
            registry=ProviderRegistry(),
            market_data_service=_FakeMarketDataService(
                fail_keys={("^GSPC", "US"), ("T1", "US")}
            ),
            watchlist_service=_FakeWatchlistService(items=[self._build_item(1, enabled=True)]),
        )
        snapshot = await service.get_snapshot(page=1, page_size=10, enabled_only=True)
        self.assertEqual(snapshot.indices[0].source, "unavailable")
        self.assertEqual(snapshot.indices[0].symbol, "^GSPC")
        self.assertEqual(snapshot.watchlist[0].source, "unavailable")
        self.assertEqual(snapshot.watchlist[0].id, 1)


if __name__ == "__main__":
    unittest.main()
