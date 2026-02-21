from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional, Set, Tuple

from market_reporter.config import LongbridgeConfig
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    to_longbridge_symbol,
)
from market_reporter.modules.symbol_search.schemas import StockSearchResult


class LongbridgeSearchProvider:
    provider_id = "longbridge"

    def __init__(self, lb_config: LongbridgeConfig) -> None:
        self._lb_config = lb_config
        self._ctx: Optional[object] = None

    async def search(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        return await asyncio.to_thread(self._search_sync, query, market, limit)

    def _search_sync(
        self, query: str, market: str, limit: int
    ) -> List[StockSearchResult]:
        if not self._is_usable():
            raise RuntimeError("Longbridge credentials are not configured")

        target_market = market.strip().upper()
        query_text = query.strip()
        if not query_text:
            return []

        candidates = self._build_candidates(query=query_text, market=target_market)
        if not candidates:
            # Let caller fallback to composite providers for name-based lookup.
            raise RuntimeError("Longbridge supports ticker-like queries only")

        ctx = self._ensure_ctx()
        lb_by_candidate: Dict[Tuple[str, str], str] = {}
        for symbol, candidate_market in candidates:
            try:
                lb_by_candidate[(symbol, candidate_market)] = to_longbridge_symbol(
                    symbol=symbol,
                    market=candidate_market,
                )
            except Exception:
                continue
        if not lb_by_candidate:
            return []

        lb_symbols = list(dict.fromkeys(lb_by_candidate.values()))
        names_by_lb = self._fetch_static_names(ctx=ctx, lb_symbols=lb_symbols)
        quote_symbols = self._fetch_quote_symbols(ctx=ctx, lb_symbols=lb_symbols)

        query_upper = query_text.upper()
        rows: List[StockSearchResult] = []
        for (symbol, candidate_market), lb_symbol in lb_by_candidate.items():
            if quote_symbols:
                if lb_symbol not in quote_symbols and lb_symbol not in names_by_lb:
                    continue
            elif lb_symbol not in names_by_lb:
                continue

            name = names_by_lb.get(lb_symbol) or symbol
            score = self._score(
                query=query_upper,
                symbol=symbol,
                lb_symbol=lb_symbol,
                name=name,
            )
            if score <= 0:
                continue
            rows.append(
                StockSearchResult(
                    symbol=symbol,
                    market=candidate_market,
                    name=name,
                    exchange=self._exchange_by_market(candidate_market),
                    source=self.provider_id,
                    score=score,
                )
            )

        if not rows:
            return []
        rows.sort(key=lambda item: item.score, reverse=True)
        return rows[:limit]

    def _fetch_quote_symbols(self, ctx, lb_symbols: List[str]) -> Set[str]:
        try:
            rows = ctx.quote(lb_symbols) or []
        except Exception:
            return set()
        symbols: Set[str] = set()
        for row in rows:
            value = str(getattr(row, "symbol", "") or "").strip().upper()
            if value:
                symbols.add(value)
        return symbols

    def _fetch_static_names(self, ctx, lb_symbols: List[str]) -> Dict[str, str]:
        try:
            rows = ctx.static_info(lb_symbols) or []
        except Exception:
            return {}
        names: Dict[str, str] = {}
        for row in rows:
            symbol = str(getattr(row, "symbol", "") or "").strip().upper()
            if not symbol:
                continue
            names[symbol] = self._pick_name(row, fallback=symbol)
        return names

    def _ensure_ctx(self):
        if self._ctx is not None:
            return self._ctx
        try:
            from longbridge.openapi import Config, QuoteContext
        except Exception as exc:
            raise RuntimeError("Longbridge SDK is unavailable") from exc

        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        self._ctx = QuoteContext(config)
        return self._ctx

    @staticmethod
    def _candidate_markets(query_upper: str, market: str) -> List[str]:
        if market in {"CN", "HK", "US"}:
            return [market]
        if re.fullmatch(r"\d{1,5}(\.HK)?", query_upper):
            return ["HK"]
        if re.fullmatch(r"\d{6}(\.(SH|SZ|SS|BJ))?", query_upper):
            return ["CN"]
        if re.fullmatch(r"\^\d{6}(\.(SH|SZ|SS|BJ))?", query_upper):
            return ["CN"]
        if query_upper.endswith(".HK") or query_upper in {"^HSI", "^HSCE", "^HSTECH"}:
            return ["HK"]
        if query_upper.endswith(".US") or re.fullmatch(
            r"\^?[A-Z][A-Z0-9.\-]{0,14}", query_upper
        ):
            return ["US"]
        return []

    @classmethod
    def _build_candidates(cls, query: str, market: str) -> List[Tuple[str, str]]:
        q = query.strip().upper()
        markets = cls._candidate_markets(q, market)
        if not markets:
            return []

        candidates: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()

        def add(raw_symbol: str, candidate_market: str) -> None:
            normalized = normalize_symbol(raw_symbol, candidate_market)
            key = (normalized, candidate_market)
            if key in seen:
                return
            seen.add(key)
            candidates.append(key)

        for candidate_market in markets:
            if candidate_market == "US":
                if re.fullmatch(r"\^?[A-Z][A-Z0-9.\-]{0,14}(\.US)?", q):
                    add(q[:-3] if q.endswith(".US") else q, "US")
            elif candidate_market == "HK":
                if q.startswith("^"):
                    add(q[:-3] if q.endswith(".HK") else q, "HK")
                elif re.fullmatch(r"\d{1,5}(\.HK)?", q):
                    add(q.replace(".HK", ""), "HK")
            elif candidate_market == "CN":
                if q.startswith("^"):
                    add(q.replace(".SS", ".SH"), "CN")
                elif re.fullmatch(r"\d{6}(\.(SH|SZ|SS|BJ))?", q):
                    add(q.replace(".SS", ".SH"), "CN")
        return candidates

    @staticmethod
    def _pick_name(security: object, fallback: str) -> str:
        for field in ("name_cn", "name_hk", "name_en", "name"):
            value = str(getattr(security, field, "") or "").strip()
            if value:
                return value
        return fallback

    @staticmethod
    def _score(query: str, symbol: str, lb_symbol: str, name: str) -> float:
        symbol_upper = symbol.upper()
        lb_symbol_upper = lb_symbol.upper()
        name_upper = name.upper()

        if query in {symbol_upper, lb_symbol_upper}:
            return 0.99
        if symbol_upper.startswith(query) or lb_symbol_upper.startswith(query):
            return 0.95
        if query in symbol_upper or query in lb_symbol_upper:
            return 0.9
        if query in name_upper:
            return 0.8
        return 0.0

    def _is_usable(self) -> bool:
        app_key = str(self._lb_config.app_key or "").strip()
        app_secret = str(self._lb_config.app_secret or "").strip()
        access_token = str(self._lb_config.access_token or "").strip()
        return bool(
            self._lb_config.enabled
            and app_key
            and app_secret
            and access_token
            and app_secret != "***"
            and access_token != "***"
        )

    @staticmethod
    def _exchange_by_market(market: str) -> str:
        return {
            "CN": "CN",
            "HK": "HKEX",
            "US": "US",
        }.get(market.upper(), "")
