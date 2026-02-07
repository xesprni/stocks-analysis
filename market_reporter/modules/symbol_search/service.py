from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.providers.akshare_search_provider import AkshareSearchProvider
from market_reporter.modules.symbol_search.providers.yfinance_search_provider import YahooFinanceSearchProvider
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class SymbolSearchService:
    MODULE_NAME = "symbol_search"

    def __init__(self, config: AppConfig, registry: ProviderRegistry) -> None:
        self.config = config
        self.registry = registry
        self.registry.register(self.MODULE_NAME, "yfinance", self._build_yfinance)
        self.registry.register(self.MODULE_NAME, "akshare", self._build_akshare)
        self.registry.register(self.MODULE_NAME, "composite", self._build_composite)

    def _build_yfinance(self):
        return YahooFinanceSearchProvider()

    def _build_akshare(self):
        return AkshareSearchProvider()

    def _build_composite(self):
        return CompositeSymbolSearchProvider(
            providers={
                "yfinance": self._build_yfinance(),
                "akshare": self._build_akshare(),
            }
        )

    async def search(
        self,
        query: str,
        market: str = "ALL",
        limit: Optional[int] = None,
        provider_id: Optional[str] = None,
    ) -> List[StockSearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        resolved_limit = limit or self.config.symbol_search.max_results
        chosen_provider = (
            provider_id
            or self.config.symbol_search.default_provider
            or self.config.modules.symbol_search.default_provider
        )
        provider = self._resolve_provider_with_fallback(chosen_provider=chosen_provider)
        try:
            rows = await provider.search(query=normalized_query, market=market.upper(), limit=resolved_limit)
        except Exception:
            if chosen_provider != "composite":
                fallback = self._resolve_provider_with_fallback(chosen_provider="composite")
                try:
                    rows = await fallback.search(query=normalized_query, market=market.upper(), limit=resolved_limit)
                except Exception:
                    rows = []
            else:
                rows = []
        dedup: Dict[Tuple[str, str], StockSearchResult] = {}
        for item in rows:
            key = (item.symbol, item.market)
            current = dedup.get(key)
            if current is None or item.score > current.score:
                dedup[key] = item
        merged = sorted(dedup.values(), key=lambda item: item.score, reverse=True)
        if merged:
            return merged[:resolved_limit]
        return self._heuristic_results(query=normalized_query, market=market.upper(), limit=resolved_limit)

    def _resolve_provider_with_fallback(self, chosen_provider: str):
        provider_id = (chosen_provider or "").strip() or "composite"
        try:
            return self.registry.resolve(self.MODULE_NAME, provider_id)
        except Exception:
            return self.registry.resolve(self.MODULE_NAME, "composite")

    @staticmethod
    def _heuristic_results(query: str, market: str, limit: int) -> List[StockSearchResult]:
        q = query.strip().upper()
        if not q:
            return []

        candidates: List[StockSearchResult] = []
        if market in {"US", "ALL"} and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", q):
            candidates.append(
                StockSearchResult(
                    symbol=normalize_symbol(q, "US"),
                    market="US",
                    name=f"{q} (manual)",
                    exchange="US",
                    source="heuristic",
                    score=0.35,
                )
            )
        if market in {"HK", "ALL"} and re.fullmatch(r"\d{1,5}(\.HK)?", q):
            code = q.replace(".HK", "").zfill(4)
            candidates.append(
                StockSearchResult(
                    symbol=normalize_symbol(code, "HK"),
                    market="HK",
                    name=f"{code} (manual)",
                    exchange="HKEX",
                    source="heuristic",
                    score=0.35,
                )
            )
        if market in {"CN", "ALL"} and re.fullmatch(r"\d{6}(\.(SH|SZ))?", q):
            code = q.split(".")[0]
            candidates.append(
                StockSearchResult(
                    symbol=normalize_symbol(code, "CN"),
                    market="CN",
                    name=f"{code} (manual)",
                    exchange="CN",
                    source="heuristic",
                    score=0.35,
                )
            )

        if not candidates:
            fallback_market = market if market in {"CN", "HK", "US"} else "US"
            candidates.append(
                StockSearchResult(
                    symbol=normalize_symbol(q, fallback_market),
                    market=fallback_market,
                    name=f"{q} (manual)",
                    exchange=fallback_market,
                    source="heuristic",
                    score=0.2,
                )
            )
        return candidates[:limit]


class CompositeSymbolSearchProvider:
    provider_id = "composite"

    def __init__(self, providers: Dict[str, object]) -> None:
        self.providers = providers

    async def search(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        merged: List[StockSearchResult] = []
        for provider in self._ordered(market=market):
            try:
                rows = await provider.search(query=query, market=market, limit=limit)
                merged.extend(rows)
            except Exception:
                continue
        if not merged:
            return []
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged[:limit]

    def _ordered(self, market: str):
        market = market.upper()
        if market in {"CN", "HK"}:
            return [self.providers["akshare"], self.providers["yfinance"]]
        return [self.providers["yfinance"], self.providers["akshare"]]
