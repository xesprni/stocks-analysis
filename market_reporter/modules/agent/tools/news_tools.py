from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

from market_reporter.core.types import NewsItem
from market_reporter.modules.agent.schemas import NewsSearchItem, NewsSearchResult
from market_reporter.modules.news.service import NewsService


class NewsTools:
    def __init__(self, news_service: NewsService) -> None:
        self.news_service = news_service

    async def search_news(
        self,
        query: str,
        from_date: str,
        to_date: str,
        limit: int = 50,
    ) -> NewsSearchResult:
        items, warnings = await self.news_service.collect(limit=max(limit, 100))
        from_dt = self._parse_date(from_date)
        to_dt = self._parse_date(to_date)
        words = [token for token in (query or "").lower().split() if token]

        dedup = set()
        selected: List[NewsSearchItem] = []
        for row in items:
            if not self._match_query(row, words):
                continue
            published_dt = self._parse_date(row.published)
            if published_dt and from_dt and published_dt < from_dt:
                continue
            if published_dt and to_dt and published_dt > to_dt:
                continue
            key = f"{row.title.strip()}::{row.link.strip()}"
            if key in dedup:
                continue
            dedup.add(key)
            selected.append(
                NewsSearchItem(
                    title=row.title,
                    media=row.source,
                    published_at=row.published,
                    summary=row.title[:160],
                    link=row.link,
                )
            )
            if len(selected) >= limit:
                break

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = selected[0].published_at if selected else retrieved_at
        extra_warnings = list(warnings)
        if not selected:
            extra_warnings.append("no_news_matched")
        return NewsSearchResult(
            query=query,
            items=selected,
            as_of=as_of,
            source="rss",
            retrieved_at=retrieved_at,
            warnings=extra_warnings,
        )

    @staticmethod
    def _match_query(item: NewsItem, words: List[str]) -> bool:
        if not words:
            return True
        text = f"{item.title} {item.source} {item.category}".lower()
        return any(word in text for word in words)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
