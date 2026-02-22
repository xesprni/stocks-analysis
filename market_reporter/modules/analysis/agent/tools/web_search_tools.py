from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote_plus, urlparse

import feedparser

from market_reporter.modules.analysis.agent.schemas import (
    WebSearchItem,
    WebSearchResult,
)


class WebSearchTools:
    async def search_web(
        self,
        query: str,
        limit: int = 10,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> WebSearchResult:
        return await asyncio.to_thread(
            self._search_web_sync,
            query,
            limit,
            from_date,
            to_date,
        )

    def _search_web_sync(
        self,
        query: str,
        limit: int,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> WebSearchResult:
        q = (query or "").strip()
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not q:
            return WebSearchResult(
                query="",
                items=[],
                as_of=retrieved_at,
                source="bing_rss",
                retrieved_at=retrieved_at,
                warnings=["empty_query"],
            )

        warnings: List[str] = []
        entries = []
        try:
            url = f"https://www.bing.com/search?q={quote_plus(q)}&format=rss"
            feed = feedparser.parse(url)
            entries = list(feed.entries or [])
            if getattr(feed, "bozo", False):
                warnings.append("web_search_feed_parse_warning")
        except Exception as exc:
            warnings.append(f"web_search_failed:{exc}")
            entries = []

        from_dt = self._parse_range_start(from_date)
        to_dt = self._parse_range_end(to_date)
        items: List[WebSearchItem] = []
        for entry in entries:
            title = str(getattr(entry, "title", "") or "").strip()
            link = str(getattr(entry, "link", "") or "").strip()
            if not title and not link:
                continue

            published = self._entry_published(entry)
            if published and from_dt and published < from_dt:
                continue
            if published and to_dt and published > to_dt:
                continue

            snippet = str(
                getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            ).strip()
            source = self._source_from_entry(entry=entry, link=link)
            items.append(
                WebSearchItem(
                    title=title,
                    source=source,
                    link=link,
                    published_at=published.isoformat(timespec="seconds")
                    if published
                    else "",
                    snippet=snippet[:240],
                )
            )
            if len(items) >= max(limit, 1):
                break

        if not items:
            warnings.append("no_web_results")

        as_of = (
            items[0].published_at if items and items[0].published_at else retrieved_at
        )
        return WebSearchResult(
            query=q,
            items=items,
            as_of=as_of,
            source="bing_rss",
            retrieved_at=retrieved_at,
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _entry_published(entry: object) -> Optional[datetime]:
        value = str(
            getattr(entry, "published", "") or getattr(entry, "updated", "") or ""
        ).strip()
        return WebSearchTools._parse_date(value)

    @staticmethod
    def _source_from_entry(entry: object, link: str) -> str:
        source = getattr(entry, "source", None)
        if source is not None:
            title = str(getattr(source, "title", "") or "").strip()
            if title:
                return title
        host = urlparse(link).netloc.strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    @staticmethod
    def _parse_range_start(value: Optional[str]) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        if len(text) == 10:
            try:
                day = datetime.strptime(text, "%Y-%m-%d").date()
                return datetime.combine(day, time.min, tzinfo=timezone.utc)
            except Exception:
                return None
        return WebSearchTools._parse_date(text)

    @staticmethod
    def _parse_range_end(value: Optional[str]) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        if len(text) == 10:
            try:
                day = datetime.strptime(text, "%Y-%m-%d").date()
                return datetime.combine(day, time.max, tzinfo=timezone.utc)
            except Exception:
                return None
        return WebSearchTools._parse_date(text)

    @staticmethod
    def _parse_date(value: str) -> Optional[datetime]:
        text = (value or "").strip()
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
