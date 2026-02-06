from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import NewsItem
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.news.providers.rss_provider import RSSNewsProvider
from market_reporter.modules.news.schemas import NewsFeedItem


class NewsService:
    MODULE_NAME = "news"

    def __init__(self, config: AppConfig, client: HttpClient, registry: ProviderRegistry) -> None:
        self.config = config
        self.client = client
        self.registry = registry
        self.registry.register(self.MODULE_NAME, "rss", self._build_rss_provider)

    def _build_rss_provider(self):
        return RSSNewsProvider(config=self.config, client=self.client)

    async def collect(self, limit: int) -> Tuple[List[NewsItem], List[str]]:
        provider_id = self.config.modules.news.default_provider
        warnings: List[str] = []
        try:
            provider = self.registry.resolve(self.MODULE_NAME, provider_id)
            data, provider_warnings = await self._collect_with_provider(
                provider=provider,
                limit=limit,
                source_id=None,
            )
            warnings.extend(provider_warnings)
            return data, warnings
        except Exception as exc:
            warnings.append(f"News provider failed [{provider_id}]: {exc}")
            return [], warnings

    async def collect_feed(
        self,
        limit: int,
        source_id: str = "ALL",
    ) -> Tuple[List[NewsFeedItem], List[str], str]:
        provider_id = self.config.modules.news.default_provider
        warnings: List[str] = []
        normalized_source_id = source_id.strip()
        if not normalized_source_id:
            normalized_source_id = "ALL"
        source_filter = None if normalized_source_id.upper() == "ALL" else normalized_source_id
        try:
            provider = self.registry.resolve(self.MODULE_NAME, provider_id)
            data, provider_warnings = await self._collect_with_provider(
                provider=provider,
                limit=limit,
                source_id=source_filter,
            )
            warnings.extend(provider_warnings)
        except Exception as exc:
            warnings.append(f"News provider failed [{provider_id}]: {exc}")
            data = []

        fetched_at = datetime.now(timezone.utc)
        items = [
            NewsFeedItem(
                source_id=item.source_id,
                source_name=item.source,
                category=item.category,
                title=item.title,
                link=item.link,
                published=item.published,
                fetched_at=fetched_at,
            )
            for item in data
        ]
        selected_source_id = source_filter if source_filter else "ALL"
        return items, warnings, selected_source_id

    def provider_status(self) -> Dict[str, List[str]]:
        return {
            "module": [self.MODULE_NAME],
            "providers": self.registry.list_ids(self.MODULE_NAME),
        }

    @staticmethod
    async def _collect_with_provider(
        provider: object,
        limit: int,
        source_id: str | None,
    ) -> Tuple[List[NewsItem], List[str]]:
        if hasattr(provider, "collect_filtered"):
            data, warnings = await provider.collect_filtered(limit=limit, source_id=source_id)
            return list(data), list(warnings)

        data = await provider.collect(limit=limit)
        if source_id:
            data = [item for item in data if item.source_id == source_id]
        return list(data), []
