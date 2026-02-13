from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from market_reporter.core.types import NewsItem
from market_reporter.modules.agent.tools.news_tools import NewsTools


class _DummyNewsService:
    def __init__(self, items: list[NewsItem], warnings: list[str] | None = None) -> None:
        self._items = items
        self._warnings = warnings or []

    async def collect(self, limit: int):
        del limit
        return list(self._items), list(self._warnings)


class NewsToolsSearchMatchingTest(unittest.TestCase):
    def test_symbol_query_matches_company_aliases(self):
        items = [
            NewsItem(
                category="finance",
                source="Reuters",
                title="Chinese ecommerce company posts strong quarter",
                link="https://example.com/pdd-earnings",
                published="2026-02-10T12:00:00+00:00",
                content="Temu owner Pinduoduo reported stronger-than-expected GMV growth.",
            ),
            NewsItem(
                category="finance",
                source="Reuters",
                title="US inflation cools in January",
                link="https://example.com/cpi",
                published="2026-02-09T12:00:00+00:00",
            ),
        ]
        tools = NewsTools(news_service=_DummyNewsService(items))

        async def scenario():
            with patch.object(
                NewsTools,
                "_resolve_company_aliases",
                new=AsyncMock(return_value=["Pinduoduo", "Temu"]),
            ):
                return await tools.search_news(
                    query="PDD",
                    symbol="PDD",
                    market="US",
                    from_date="2026-02-01",
                    to_date="2026-02-13",
                    limit=10,
                )

        result = asyncio.run(scenario())
        self.assertEqual(len(result.items), 1)
        self.assertIn("Temu owner Pinduoduo", result.items[0].summary)
        self.assertNotIn("no_news_matched", result.warnings)
        self.assertNotIn("news_fallback_recent_headlines", result.warnings)

    def test_stock_query_uses_recent_fallback_when_no_match(self):
        items = [
            NewsItem(
                category="finance",
                source="Yahoo Finance",
                title="US yields retreat as bond market rallies",
                link="https://example.com/yields",
                published="2026-02-12T10:30:00+00:00",
            ),
            NewsItem(
                category="finance",
                source="Yahoo Finance",
                title="Oil steadies after volatile session",
                link="https://example.com/oil",
                published="2026-02-11T11:00:00+00:00",
            ),
            NewsItem(
                category="policy",
                source="Federal Reserve",
                title="Fed releases policy implementation note",
                link="https://example.com/fed-note",
                published="2026-02-10T08:00:00+00:00",
            ),
        ]
        tools = NewsTools(news_service=_DummyNewsService(items))

        async def scenario():
            with patch.object(
                NewsTools,
                "_resolve_company_aliases",
                new=AsyncMock(return_value=[]),
            ):
                return await tools.search_news(
                    query="PDD",
                    symbol="PDD",
                    market="US",
                    from_date="2026-02-01",
                    to_date="2026-02-13",
                    limit=2,
                )

        result = asyncio.run(scenario())
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0].title, "US yields retreat as bond market rallies")
        self.assertEqual(result.items[1].title, "Oil steadies after volatile session")
        self.assertIn("no_news_matched", result.warnings)
        self.assertIn("news_fallback_recent_headlines", result.warnings)

    def test_fallback_respects_date_filter(self):
        items = [
            NewsItem(
                category="finance",
                source="Yahoo Finance",
                title="Old headline outside date range",
                link="https://example.com/old",
                published="2026-01-10T10:30:00+00:00",
            ),
            NewsItem(
                category="finance",
                source="Yahoo Finance",
                title="In-range headline",
                link="https://example.com/new",
                published="2026-02-12T10:30:00+00:00",
            ),
        ]
        tools = NewsTools(news_service=_DummyNewsService(items))

        async def scenario():
            with patch.object(
                NewsTools,
                "_resolve_company_aliases",
                new=AsyncMock(return_value=[]),
            ):
                return await tools.search_news(
                    query="PDD",
                    symbol="PDD",
                    market="US",
                    from_date="2026-02-01",
                    to_date="2026-02-13",
                    limit=5,
                )

        result = asyncio.run(scenario())
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "In-range headline")
        self.assertIn("no_news_matched", result.warnings)
        self.assertIn("news_fallback_recent_headlines", result.warnings)

    def test_market_query_matches_news_content(self):
        items = [
            NewsItem(
                category="policy",
                source="Central Bank",
                title="Policy briefing published",
                link="https://example.com/policy",
                published="2026-02-12T10:30:00+00:00",
                content="Officials hinted at a potential rate cut in coming meetings.",
            ),
        ]
        tools = NewsTools(news_service=_DummyNewsService(items))

        async def scenario():
            return await tools.search_news(
                query="rate cut",
                from_date="2026-02-01",
                to_date="2026-02-13",
                limit=5,
            )

        result = asyncio.run(scenario())
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "Policy briefing published")
        self.assertIn("rate cut", result.items[0].summary.lower())


if __name__ == "__main__":
    unittest.main()
