from __future__ import annotations

import asyncio
from typing import List

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class AkshareSearchProvider:
    provider_id = "akshare"

    async def search(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        return await asyncio.to_thread(self._search_sync, query, market, limit)

    def _search_sync(self, query: str, market: str, limit: int) -> List[StockSearchResult]:
        import akshare as ak

        target_market = market.upper()
        q = query.strip().upper()
        results: List[StockSearchResult] = []

        if target_market in {"ALL", "CN"}:
            try:
                df = ak.stock_zh_a_spot_em()
                code_col = df["代码"].astype(str)
                name_col = df["名称"].astype(str)
                matched = df[(code_col.str.upper().str.contains(q)) | (name_col.str.upper().str.contains(q))]
                for _, row in matched.head(limit).iterrows():
                    symbol = normalize_symbol(str(row["代码"]), "CN")
                    results.append(
                        StockSearchResult(
                            symbol=symbol,
                            market="CN",
                            name=str(row["名称"]),
                            exchange="CN",
                            source=self.provider_id,
                            score=self._score(q, symbol, str(row["名称"])),
                        )
                    )
            except Exception:
                pass

        if target_market in {"ALL", "HK"} and len(results) < limit:
            try:
                df = ak.stock_hk_spot_em()
                code_col = df["代码"].astype(str).str.zfill(4)
                name_col = df["名称"].astype(str)
                matched = df[(code_col.str.upper().str.contains(q)) | (name_col.str.upper().str.contains(q))]
                for _, row in matched.head(limit).iterrows():
                    symbol = normalize_symbol(str(row["代码"]).zfill(4), "HK")
                    results.append(
                        StockSearchResult(
                            symbol=symbol,
                            market="HK",
                            name=str(row["名称"]),
                            exchange="HKEX",
                            source=self.provider_id,
                            score=self._score(q, symbol, str(row["名称"])),
                        )
                    )
                    if len(results) >= limit:
                        break
            except Exception:
                pass

        if target_market in {"ALL", "US"} and len(results) < limit:
            try:
                df = ak.stock_us_spot_em()
                code_col = df["代码"].astype(str)
                name_col = df["名称"].astype(str)
                matched = df[(code_col.str.upper().str.contains(q)) | (name_col.str.upper().str.contains(q))]
                for _, row in matched.head(limit).iterrows():
                    symbol = normalize_symbol(str(row["代码"]), "US")
                    results.append(
                        StockSearchResult(
                            symbol=symbol,
                            market="US",
                            name=str(row["名称"]),
                            exchange="US",
                            source=self.provider_id,
                            score=self._score(q, symbol, str(row["名称"])),
                        )
                    )
                    if len(results) >= limit:
                        break
            except Exception:
                pass

        return results[:limit]

    @staticmethod
    def _score(query_upper: str, symbol: str, name: str) -> float:
        symbol_upper = symbol.upper()
        name_upper = name.upper()
        if query_upper == symbol_upper:
            return 0.99
        if symbol_upper.startswith(query_upper):
            return 0.95
        if query_upper in symbol_upper:
            return 0.9
        if query_upper in name_upper:
            return 0.8
        return 0.6
