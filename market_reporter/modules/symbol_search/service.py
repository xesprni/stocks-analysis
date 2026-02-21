from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.providers.longbridge_search_provider import (
    LongbridgeSearchProvider,
)
from market_reporter.modules.symbol_search.schemas import StockSearchResult

_US_INDEX_ALIAS_MAP: List[Dict[str, str]] = [
    {
        "symbol": "^GSPC",
        "market": "US",
        "name": "S&P 500 Index",
        "exchange": "INDEX",
        "aliases": "标普|标普500|标普指数|普500|sp500|s&p500|s&p 500|gspc|spx",
    },
    {
        "symbol": "^IXIC",
        "market": "US",
        "name": "NASDAQ Composite Index",
        "exchange": "INDEX",
        "aliases": "纳斯达克|纳指|nasdaq|nasdaqcomposite|ixic",
    },
    {
        "symbol": "^DJI",
        "market": "US",
        "name": "Dow Jones Industrial Average",
        "exchange": "INDEX",
        "aliases": "道琼斯|道指|dowjones|djia|dji",
    },
]


def _normalize_alias_query(query: str) -> str:
    q = query.strip().lower()
    q = q.replace("＆", "&")
    q = q.replace("和", "")
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", q)


class SymbolSearchService:
    MODULE_NAME = "symbol_search"

    def __init__(self, config: AppConfig, registry: ProviderRegistry) -> None:
        self.config = config
        self.registry = registry
        self.registry.register(self.MODULE_NAME, "longbridge", self._build_longbridge)
        self.registry.register(self.MODULE_NAME, "composite", self._build_composite)

    def _build_longbridge(self):
        return LongbridgeSearchProvider(lb_config=self.config.longbridge)

    def _build_composite(self):
        providers = {
            "longbridge": self._build_longbridge(),
        }
        return CompositeSymbolSearchProvider(providers=providers)

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
        requested_market = market.upper()
        alias_rows = self._index_alias_results(
            query=normalized_query,
            market=requested_market,
            limit=resolved_limit,
        )
        if requested_market in {
            "CN",
            "HK",
            "US",
        } and not self._query_compatible_with_market(
            query=normalized_query,
            market=requested_market,
        ):
            return alias_rows
        resolved_market = self._resolve_search_market(
            query=normalized_query, market=market.upper()
        )
        chosen_provider = (
            provider_id
            or self.config.symbol_search.default_provider
            or self.config.modules.symbol_search.default_provider
            or "longbridge"
        )
        # Prefer requested/default provider first, then degrade to composite if it fails.
        provider = self._resolve_provider_with_fallback(chosen_provider=chosen_provider)
        try:
            rows = await provider.search(
                query=normalized_query, market=resolved_market, limit=resolved_limit
            )
        except Exception:
            if (chosen_provider or "").strip().lower() != "composite":
                fallback = self._resolve_provider_with_fallback(
                    chosen_provider="composite"
                )
                try:
                    rows = await fallback.search(
                        query=normalized_query,
                        market=resolved_market,
                        limit=resolved_limit,
                    )
                except Exception:
                    rows = []
            else:
                rows = []
        rows = alias_rows + rows
        dedup: Dict[Tuple[str, str], StockSearchResult] = {}
        # Merge same symbol-market hits by highest score across providers.
        for item in rows:
            key = (item.symbol, item.market)
            current = dedup.get(key)
            if current is None or item.score > current.score:
                dedup[key] = item
        merged = sorted(dedup.values(), key=lambda item: item.score, reverse=True)
        if merged:
            return merged[:resolved_limit]
        # If all providers return empty, still provide predictable manual candidates.
        return self._heuristic_results(
            query=normalized_query, market=resolved_market, limit=resolved_limit
        )

    def _resolve_provider_with_fallback(self, chosen_provider: str):
        provider_id = (chosen_provider or "").strip() or "longbridge"
        try:
            return self.registry.resolve(self.MODULE_NAME, provider_id)
        except Exception:
            try:
                return self.registry.resolve(self.MODULE_NAME, "composite")
            except Exception:
                return self.registry.resolve(self.MODULE_NAME, "longbridge")

    @staticmethod
    def _query_compatible_with_market(query: str, market: str) -> bool:
        q = query.strip().upper()
        if not q:
            return False

        has_cjk = re.search(r"[\u4e00-\u9fff]", query) is not None
        if market == "US":
            if has_cjk:
                return False
            return bool(re.search(r"[A-Z]", q))
        if market == "HK":
            if has_cjk:
                return True
            return bool(
                re.fullmatch(r"\d{1,5}(\.HK)?", q)
                or re.fullmatch(r"\^?[A-Z]{2,12}(\.HK)?", q)
            )
        if market == "CN":
            if has_cjk:
                return True
            return bool(re.fullmatch(r"\^?\d{6}(\.(SH|SZ|SS|BJ))?", q))
        return True

    @staticmethod
    def _index_alias_results(
        query: str,
        market: str,
        limit: int,
    ) -> List[StockSearchResult]:
        target_market = market.upper()
        if target_market not in {"ALL", "US"}:
            return []
        normalized = _normalize_alias_query(query)
        if not normalized:
            return []

        rows: List[StockSearchResult] = []
        for row in _US_INDEX_ALIAS_MAP:
            aliases = [
                _normalize_alias_query(alias)
                for alias in row.get("aliases", "").split("|")
            ]
            aliases = [alias for alias in aliases if alias]

            symbol_token = (
                str(row.get("symbol", ""))
                .strip()
                .upper()
                .replace("^", "")
                .replace(".", "")
            )
            normalized_upper = normalized.upper()

            exact_match = normalized_upper == symbol_token or normalized in aliases
            fuzzy_match = any(
                normalized in alias or alias in normalized for alias in aliases
            )
            if not exact_match and not fuzzy_match:
                continue

            rows.append(
                StockSearchResult(
                    symbol=str(row.get("symbol") or ""),
                    market="US",
                    name=str(row.get("name") or "US Index"),
                    exchange=str(row.get("exchange") or "INDEX"),
                    source="alias",
                    score=0.99 if exact_match else 0.92,
                )
            )

        rows.sort(key=lambda item: item.score, reverse=True)
        return rows[:limit]

    @staticmethod
    def _resolve_search_market(query: str, market: str) -> str:
        market_upper = market.upper()
        if market_upper != "ALL":
            return market_upper

        q = query.strip().upper()
        if SymbolSearchService._index_alias_results(query=query, market="ALL", limit=1):
            return "US"
        if re.fullmatch(r"\d{1,5}(\.HK)?", q):
            return "HK"
        if re.fullmatch(r"\d{6}(\.(SH|SZ|SS|BJ))?", q):
            return "CN"
        if re.fullmatch(r"\^\d{6}(\.(SH|SZ|SS|BJ))?", q):
            return "CN"
        if q.endswith(".HK") or q in {"^HSI", "^HSCE", "^HSTECH"}:
            return "HK"
        if q.endswith(".US") or re.fullmatch(r"\^?[A-Z][A-Z0-9.\-]{0,14}", q):
            return "US"
        return "ALL"

    @staticmethod
    def _heuristic_results(
        query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
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
        return candidates[:limit]


class CompositeSymbolSearchProvider:
    provider_id = "composite"

    def __init__(self, providers: Dict[str, Any]) -> None:
        self.providers = providers

    async def search(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        merged: List[StockSearchResult] = []
        # Try multiple providers in priority order and keep partial results.
        for provider in self._ordered(market=market, query=query):
            try:
                rows = await provider.search(query=query, market=market, limit=limit)
                merged.extend(rows)
                if len(merged) >= limit:
                    break
            except Exception:
                continue
        if not merged:
            return []
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged[:limit]

    def _ordered(self, market: str, query: str = ""):
        del market, query
        longbridge = self.providers.get("longbridge")
        order = [longbridge]
        return [p for p in order if p is not None]
