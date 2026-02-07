from __future__ import annotations

from typing import List

import httpx

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class FinnhubSearchProvider:
    """Symbol search via Finnhub free API — fast HTTP lookup, no API key required for basic search."""

    provider_id = "finnhub"

    SEARCH_URL = "https://finnhub.io/api/v1/search"

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    async def search(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        target_market = market.upper()
        q = query.strip()
        if not q:
            return []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        params: dict = {"q": q}
        if self._api_key:
            params["token"] = self._api_key

        try:
            async with httpx.AsyncClient(
                timeout=8.0, headers=headers, follow_redirects=True
            ) as client:
                response = await client.get(self.SEARCH_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        results_list = payload.get("result")
        if not isinstance(results_list, list):
            return []

        results: List[StockSearchResult] = []
        for item in results_list:
            if not isinstance(item, dict):
                continue
            symbol_raw = str(item.get("symbol") or "").strip().upper()
            if not symbol_raw:
                continue
            display_symbol = str(item.get("displaySymbol") or symbol_raw)
            description = str(item.get("description") or display_symbol)
            item_type = str(item.get("type") or "")

            # Only include common stocks / ADR / ETF
            if item_type and item_type not in {
                "Common Stock",
                "ADR",
                "ETF",
                "ETP",
                "REIT",
                "",
            }:
                continue

            inferred_market = self._infer_market(symbol_raw)
            if target_market != "ALL" and inferred_market != target_market:
                continue

            normalized = self._normalize_for_market(symbol_raw, inferred_market)
            score = self._score(query=q, symbol=normalized, name=description)

            results.append(
                StockSearchResult(
                    symbol=normalized,
                    market=inferred_market,
                    name=description,
                    exchange=item_type or "Stock",
                    source=self.provider_id,
                    score=score,
                )
            )
            if len(results) >= limit:
                break

        return results[:limit]

    @staticmethod
    def _infer_market(symbol: str) -> str:
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.endswith(".SS") or symbol.endswith(".SZ") or symbol.endswith(".SH"):
            return "CN"
        # Finnhub uses special suffixes for Shanghai/Shenzhen
        if symbol.endswith(".SS") or symbol.endswith(".SZ"):
            return "CN"
        return "US"

    @staticmethod
    def _normalize_for_market(symbol: str, market: str) -> str:
        if market == "CN":
            symbol = symbol.replace(".SS", ".SH")
        return normalize_symbol(symbol, market)

    @staticmethod
    def _score(query: str, symbol: str, name: str) -> float:
        q = query.strip().upper()
        symbol_u = symbol.upper()
        name_u = name.upper()
        if q == symbol_u:
            return 0.98
        if symbol_u.startswith(q):
            return 0.94
        if q in symbol_u:
            return 0.88
        if q in name_u:
            return 0.78
        return 0.55
