from __future__ import annotations

import asyncio
from typing import List, Optional, Set, Tuple

import feedparser

from market_reporter.config import AppConfig, NewsSource
from market_reporter.models import NewsItem

from .http_client import HttpClient


class NewsCollector:
    def __init__(
        self,
        config: AppConfig,
        client: HttpClient,
        news_sources: Optional[List[NewsSource]] = None,
    ) -> None:
        self.config = config
        self.client = client
        self._news_sources = news_sources

    @property
    def news_sources(self) -> List[NewsSource]:
        if self._news_sources is not None:
            return self._news_sources
        # Fallback: load from DB
        from sqlmodel import Session, select

        from market_reporter.infra.db.models import NewsSourceTable
        from market_reporter.infra.db.session import get_engine

        engine = get_engine(self.config.database.url)
        with Session(engine) as session:
            rows = session.exec(select(NewsSourceTable)).all()
            return [
                NewsSource(
                    source_id=row.source_id,
                    name=row.name,
                    category=row.category,
                    url=row.url,
                    enabled=row.enabled,
                )
                for row in rows
            ]

    async def collect(
        self, limit_per_source: int = 20
    ) -> Tuple[List[NewsItem], List[str]]:
        results: List[NewsItem] = []
        errors: List[str] = []
        seen_keys: Set[str] = set()
        sources = self.news_sources

        tasks = [
            self._collect_from_source(source=source, limit_per_source=limit_per_source)
            for source in sources
        ]
        settled = await asyncio.gather(*tasks, return_exceptions=True)

        for source, settled_item in zip(sources, settled):
            if isinstance(settled_item, Exception):
                errors.append(f"News source failed [{source.name}]: {settled_item}")
                continue
            for item in settled_item:
                dedup_key = f"{item.title}::{item.link}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                results.append(item)

        return results, errors

    async def _collect_from_source(
        self, source: NewsSource, limit_per_source: int
    ) -> List[NewsItem]:
        feed_text = await self.client.get_text(source.url)
        parsed = feedparser.parse(feed_text)
        items: List[NewsItem] = []

        for entry in parsed.entries[: max(1, limit_per_source)]:
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            link = str(entry.get("link", "")).strip()
            published = str(
                entry.get("published", "")
                or entry.get("updated", "")
                or entry.get("created", "")
            ).strip()

            items.append(
                NewsItem(
                    category=source.category,
                    source=source.name,
                    title=title,
                    link=link,
                    published=published,
                )
            )

        return items
