from __future__ import annotations

import asyncio
import html
import re
from typing import List, Optional, Sequence, Tuple

import feedparser
import httpx

from market_reporter.config import AppConfig, NewsSource
from market_reporter.core.types import NewsItem
from market_reporter.infra.http.client import HttpClient


class RSSNewsProvider:
    provider_id = "rss"

    def __init__(
        self,
        config: AppConfig,
        client: HttpClient,
        news_sources: List[NewsSource] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self._news_sources = news_sources

    @property
    def news_sources(self) -> List[NewsSource]:
        if self._news_sources is not None:
            return self._news_sources
        # Fallback path keeps legacy callers working when sources are not injected.
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

    async def collect(self, limit: int) -> List[NewsItem]:
        items, _ = await self.collect_filtered(limit=limit, source_id=None)
        return items

    async def collect_filtered(
        self,
        limit: int,
        source_id: Optional[str] = None,
    ) -> Tuple[List[NewsItem], List[str]]:
        selected_sources = self._select_sources(source_id=source_id)
        if source_id and not selected_sources:
            return [], [f"News source not found or disabled: {source_id}"]

        # Fetch each source concurrently; failures are folded into warnings per source.
        tasks = [
            self._collect_from_source(source=source, limit=limit)
            for source in selected_sources
        ]
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        items: List[NewsItem] = []
        warnings: List[str] = []
        dedup: set[str] = set()
        for source, result in zip(selected_sources, settled):
            if isinstance(result, Exception):
                if isinstance(result, httpx.HTTPStatusError):
                    status_code = result.response.status_code
                    warnings.append(
                        f"News source failed [id={source.source_id};name={source.name};status={status_code}]: {result}"
                    )
                else:
                    warnings.append(
                        f"News source failed [id={source.source_id};name={source.name};status=error]: {result}"
                    )
                continue
            for item in result:
                # Title + link dedup avoids duplicate entries across mirrored feeds.
                key = f"{item.title}::{item.link}"
                if key in dedup:
                    continue
                dedup.add(key)
                items.append(item)
        return items, warnings

    def _select_sources(self, source_id: Optional[str] = None) -> Sequence[NewsSource]:
        # Disabled sources are filtered at provider layer for all callers.
        sources = [source for source in self.news_sources if source.enabled]
        if source_id:
            return [source for source in sources if source.source_id == source_id]
        return sources

    async def _collect_from_source(
        self, source: NewsSource, limit: int
    ) -> List[NewsItem]:
        body = await self.client.get_text(source.url)
        parsed = feedparser.parse(body)
        output: List[NewsItem] = []
        for entry in parsed.entries[: max(1, limit)]:
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            # Keep parser tolerant: only require title; other fields are optional.
            output.append(
                NewsItem(
                    source_id=source.source_id or "",
                    category=source.category,
                    source=source.name,
                    title=title,
                    link=str(entry.get("link", "")).strip(),
                    published=str(
                        entry.get("published", "") or entry.get("updated", "")
                    ).strip(),
                    content=self._entry_content_text(entry),
                )
            )
        return output

    @staticmethod
    def _entry_content_text(entry: object) -> str:
        if not isinstance(entry, dict):
            return ""
        chunks: List[str] = []
        for key in ("summary", "description"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())
        rich_content = entry.get("content")
        if isinstance(rich_content, list):
            for item in rich_content:
                if not isinstance(item, dict):
                    continue
                value = item.get("value")
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
        if not chunks:
            return ""
        text = " ".join(chunks)
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 2000:
            return text[:2000]
        return text
