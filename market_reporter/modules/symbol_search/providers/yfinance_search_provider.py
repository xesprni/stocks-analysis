from __future__ import annotations

import asyncio
from typing import List

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class YahooFinanceSearchProvider:
    provider_id = "yfinance"

    async def search(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        return await asyncio.to_thread(self._search_sync, query, market, limit)

    def _search_sync(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        import yfinance as yf

        target_market = market.upper()
        search = yf.Search(query=query, max_results=max(limit * 2, 20))
        quotes = getattr(search, "quotes", []) or []

        results: List[StockSearchResult] = []
        for item in quotes:
            symbol_raw = str(item.get("symbol") or "").strip().upper()
            if not symbol_raw:
                continue
            inferred_market = self._infer_market(symbol_raw)
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
    def _infer_market(symbol: str) -> str:
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.endswith(".SS") or symbol.endswith(".SZ") or symbol.endswith(".SH"):
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
            return 0.99
        if symbol_u.startswith(q):
            return 0.95
        if q in symbol_u:
            return 0.9
        if q in name_u:
            return 0.8
        return 0.6
