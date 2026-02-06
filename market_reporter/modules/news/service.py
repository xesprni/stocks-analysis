from __future__ import annotations

from typing import Dict, List, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import NewsItem
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.news.providers.rss_provider import RSSNewsProvider


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
            data = await provider.collect(limit=limit)
            return data, warnings
        except Exception as exc:
            warnings.append(f"News provider failed [{provider_id}]: {exc}")
            return [], warnings

    def provider_status(self) -> Dict[str, List[str]]:
        return {
            "module": [self.MODULE_NAME],
            "providers": self.registry.list_ids(self.MODULE_NAME),
        }
