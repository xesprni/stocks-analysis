from __future__ import annotations

import asyncio
import contextlib
import os
import re
from typing import List

from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class AkshareSearchProvider:
    provider_id = "akshare"

    async def search(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        # akshare APIs are sync; offload scanning to thread worker.
        return await asyncio.to_thread(self._search_sync, query, market, limit)

    def _search_sync(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        import akshare as ak

        target_market = market.upper()
        q = query.strip().upper()
        results: List[StockSearchResult] = []

        for scope in self._scopes(target_market=target_market, query_upper=q):
            if len(results) >= limit:
                break

            if scope == "CN":
                try:
                    with self._silence_console():
                        df = ak.stock_zh_a_spot_em()
                    code_col = df["代码"].astype(str)
                    name_col = df["名称"].astype(str)
                    matched = df[
                        (code_col.str.upper().str.contains(q))
                        | (name_col.str.upper().str.contains(q))
                    ]
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
                        if len(results) >= limit:
                            break
                except Exception:
                    # Keep partial results from other markets/providers.
                    pass
            elif scope == "HK":
                try:
                    with self._silence_console():
                        df = ak.stock_hk_spot_em()
                    code_col = df["代码"].astype(str).str.zfill(4)
                    name_col = df["名称"].astype(str)
                    matched = df[
                        (code_col.str.upper().str.contains(q))
                        | (name_col.str.upper().str.contains(q))
                    ]
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
            elif scope == "US":
                try:
                    with self._silence_console():
                        df = ak.stock_us_spot_em()
                    code_col = df["代码"].astype(str)
                    name_col = df["名称"].astype(str)
                    matched = df[
                        (code_col.str.upper().str.contains(q))
                        | (name_col.str.upper().str.contains(q))
                    ]
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
    def _scopes(target_market: str, query_upper: str) -> List[str]:
        if target_market in {"CN", "HK", "US"}:
            return [target_market]
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", query_upper):
            return ["US"]
        if re.fullmatch(r"\d{6}(\.(SH|SZ|SS|BJ))?", query_upper):
            return ["CN"]
        if re.fullmatch(r"\d{1,5}(\.HK)?", query_upper):
            return ["HK"]
        if re.search(r"[\u4e00-\u9fff]", query_upper):
            return ["CN", "HK"]
        return ["CN", "HK", "US"]

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

    @staticmethod
    @contextlib.contextmanager
    def _silence_console():
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
