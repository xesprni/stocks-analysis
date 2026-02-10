from __future__ import annotations

import asyncio
from typing import List

import httpx

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class YahooFinanceSearchProvider:
    provider_id = "yfinance"

    async def search(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        target_market = market.upper()
        try:
            # Prefer public HTTP endpoint because it is faster and avoids heavy local objects.
            remote = await self._search_http(query=query, market=target_market, limit=limit)
            if remote:
                return remote[:limit]
        except Exception:
            pass
        try:
            # Fallback to yfinance SDK path when HTTP search is unavailable.
            return await asyncio.to_thread(self._search_sync, query, target_market, limit)
        except Exception:
            return []

    async def _search_http(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        params = {
            "q": query.strip(),
            "quotesCount": str(max(limit * 3, 20)),
            "newsCount": "0",
            "enableFuzzyQuery": "true",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
            response = await client.get("https://query2.finance.yahoo.com/v1/finance/search", params=params)
            response.raise_for_status()
            payload = response.json()
        quotes = payload.get("quotes")
        if not isinstance(quotes, list):
            return []
        return self._build_results(rows=quotes, query=query, target_market=market, limit=limit)

    def _search_sync(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        import yfinance as yf

        search = yf.Search(query=query, max_results=max(limit * 2, 20))
        quotes = getattr(search, "quotes", []) or []
        return self._build_results(rows=quotes, query=query, target_market=market, limit=limit)

    def _build_results(
        self,
        rows: List[object],
        query: str,
        target_market: str,
        limit: int,
    ) -> List[StockSearchResult]:
        results: List[StockSearchResult] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol_raw = str(item.get("symbol") or "").strip().upper()
            if not symbol_raw:
                continue
            # Infer market from symbol/exchange fields before normalization.
            inferred_market = self._infer_market(symbol=symbol_raw, exchange=str(item.get("exchange") or item.get("exchDisp") or ""))
            if target_market != "ALL" and inferred_market != target_market:
                continue

            normalized = self._normalize_for_market(symbol_raw, inferred_market)
            name = str(item.get("shortname") or item.get("longname") or normalized)
            exchange = str(item.get("exchange") or item.get("fullExchangeName") or "")
            score = self._score(query=query, symbol=normalized, name=name)

            results.append(
                StockSearchResult(
                    symbol=normalized,
                    market=inferred_market,
                    name=name,
                    exchange=exchange,
                    source=self.provider_id,
                    score=score,
                )
            )

        return results[:limit]

    @staticmethod
    def _infer_market(symbol: str, exchange: str = "") -> str:
        exchange_u = exchange.upper()
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.endswith(".SS") or symbol.endswith(".SZ") or symbol.endswith(".SH"):
            return "CN"
        if exchange_u in {"SHH", "SHZ", "SSE", "SZE", "SHE"}:
            return "CN"
        if exchange_u in {"HKG", "HKEX", "HKE"} or "HONG KONG" in exchange_u:
            return "HK"
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
            return 0.99
        if symbol_u.startswith(q):
            return 0.95
        if q in symbol_u:
            return 0.9
        if q in name_u:
            return 0.8
        return 0.6
