from __future__ import annotations

import asyncio
from typing import List

import feedparser

from market_reporter.config import AppConfig, NewsSource
from market_reporter.core.types import NewsItem
from market_reporter.infra.http.client import HttpClient


class RSSNewsProvider:
    provider_id = "rss"

    def __init__(self, config: AppConfig, client: HttpClient) -> None:
        self.config = config
        self.client = client

    async def collect(self, limit: int) -> List[NewsItem]:
        tasks = [self._collect_from_source(source=source, limit=limit) for source in self.config.news_sources]
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        items: List[NewsItem] = []
        dedup: set[str] = set()
        for result in settled:
            if isinstance(result, Exception):
                continue
            for item in result:
                key = f"{item.title}::{item.link}"
                if key in dedup:
                    continue
                dedup.add(key)
                items.append(item)
        return items

    async def _collect_from_source(self, source: NewsSource, limit: int) -> List[NewsItem]:
        body = await self.client.get_text(source.url)
        parsed = feedparser.parse(body)
        output: List[NewsItem] = []
        for entry in parsed.entries[: max(1, limit)]:
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            output.append(
                NewsItem(
                    category=source.category,
                    source=source.name,
                    title=title,
                    link=str(entry.get("link", "")).strip(),
                    published=str(entry.get("published", "") or entry.get("updated", "")).strip(),
                )
            )
        return output
