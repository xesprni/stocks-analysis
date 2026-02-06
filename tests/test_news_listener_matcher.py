import unittest
from datetime import datetime, timedelta, timezone

from market_reporter.core.types import CurvePoint, NewsItem
from market_reporter.modules.news_listener.matcher import (
    calculate_window_change_percent,
    choose_severity,
    find_symbol_news_matches,
)
from market_reporter.modules.watchlist.schemas import WatchlistItem


class NewsListenerMatcherTest(unittest.TestCase):
    def test_match_news_for_watchlist_symbol(self):
        now = datetime.now(timezone.utc)
        item = WatchlistItem(
            id=1,
            symbol="AAPL",
            market="US",
            alias="苹果",
            display_name="Apple",
            keywords=["iphone"],
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        news_items = [
            NewsItem(
                category="finance",
                source="test",
                title="Apple launches new iPhone production line",
                link="",
                published="",
            ),
            NewsItem(
                category="finance",
                source="test",
                title="Macro policy update",
                link="",
                published="",
            ),
        ]

        result = find_symbol_news_matches(news_items=news_items, watch_items=[item])
        self.assertIn(("AAPL", "US"), result)
        self.assertEqual(len(result[("AAPL", "US")]["news"]), 1)

    def test_change_percent_and_severity(self):
        base = datetime.now(timezone.utc)
        points = [
            CurvePoint(symbol="AAPL", market="US", ts=(base - timedelta(minutes=20)).isoformat(), price=100, source="x"),
            CurvePoint(symbol="AAPL", market="US", ts=(base - timedelta(minutes=10)).isoformat(), price=101, source="x"),
            CurvePoint(symbol="AAPL", market="US", ts=base.isoformat(), price=103, source="x"),
        ]
        change = calculate_window_change_percent(points=points, window_minutes=15)
        assert change is not None
        self.assertGreater(change, 1.9)
        self.assertEqual(choose_severity(change_percent=change, threshold_percent=2.0), "MEDIUM")
        self.assertEqual(choose_severity(change_percent=3.5, threshold_percent=2.0), "MEDIUM")
        self.assertEqual(choose_severity(change_percent=5.0, threshold_percent=2.0), "HIGH")


if __name__ == "__main__":
    unittest.main()
