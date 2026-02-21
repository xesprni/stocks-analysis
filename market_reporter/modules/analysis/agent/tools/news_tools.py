from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

from market_reporter.config import LongbridgeConfig
from market_reporter.core.types import NewsItem
from market_reporter.modules.analysis.agent.schemas import (
    NewsSearchItem,
    NewsSearchResult,
)
from market_reporter.modules.analysis.agent.tools.market_tools import (
    infer_market_from_symbol,
)
from market_reporter.modules.market_data.symbol_mapper import (
    normalize_symbol,
    strip_market_suffix,
    to_longbridge_symbol,
)
from market_reporter.modules.news.service import NewsService

logger = logging.getLogger(__name__)


class NewsTools:
    def __init__(
        self,
        news_service: NewsService,
        lb_config: Optional[LongbridgeConfig] = None,
    ) -> None:
        self.news_service = news_service
        self._lb_config = lb_config
        self._alias_cache: Dict[str, List[str]] = {}

    async def search_news(
        self,
        query: str,
        from_date: str,
        to_date: str,
        limit: int = 50,
        symbol: str = "",
        market: str = "",
    ) -> NewsSearchResult:
        items, warnings = await self.news_service.collect(limit=max(limit, 100))
        from_dt = self._parse_range_start(from_date)
        to_dt = self._parse_range_end(to_date)
        filtered = self._apply_date_filter(items=items, from_dt=from_dt, to_dt=to_dt)

        if (symbol or "").strip():
            selected_rows, strict_hit = await self._search_stock_news(
                filtered_items=filtered,
                query=query,
                symbol=symbol,
                market=market,
                limit=limit,
            )
            selected = self._to_search_items(rows=selected_rows, limit=limit)
            extra_warnings = list(warnings)
            if not strict_hit:
                extra_warnings.append("no_news_matched")
                extra_warnings.append("news_fallback_recent_headlines")
        else:
            words = [token for token in (query or "").lower().split() if token]
            selected_rows = [
                row for row, _ in filtered if self._match_query_words(row, words)
            ]
            selected = self._to_search_items(rows=selected_rows, limit=limit)
            extra_warnings = list(warnings)
            if not selected:
                extra_warnings.append("no_news_matched")

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = selected[0].published_at if selected else retrieved_at
        return NewsSearchResult(
            query=query,
            items=selected,
            as_of=as_of,
            source="rss",
            retrieved_at=retrieved_at,
            warnings=list(dict.fromkeys(extra_warnings)),
        )

    async def _search_stock_news(
        self,
        filtered_items: List[Tuple[NewsItem, Optional[datetime]]],
        query: str,
        symbol: str,
        market: str,
        limit: int,
    ) -> Tuple[List[NewsItem], bool]:
        ticker_terms, name_terms = await self._build_stock_terms(
            query=query,
            symbol=symbol,
            market=market,
        )
        strict_rows = [
            row
            for row, _ in filtered_items
            if self._match_stock_terms(
                item=row,
                ticker_terms=ticker_terms,
                name_terms=name_terms,
            )
        ]
        if strict_rows:
            return strict_rows[:limit], True
        fallback_rows = self._fallback_recent_headlines(filtered_items=filtered_items)
        return fallback_rows[:limit], False

    async def _build_stock_terms(
        self,
        query: str,
        symbol: str,
        market: str,
    ) -> Tuple[List[str], List[str]]:
        query_text = (query or "").strip()
        symbol_text = (symbol or "").strip()
        resolved_symbol = symbol_text or query_text
        resolved_market = infer_market_from_symbol(
            resolved_symbol,
            fallback=market or "US",
        )
        normalized_symbol = (
            normalize_symbol(resolved_symbol, resolved_market)
            if resolved_symbol
            else ""
        )
        stripped_symbol = strip_market_suffix(normalized_symbol)

        ticker_terms: List[str] = []
        name_terms: List[str] = []
        if query_text:
            if self._looks_like_ticker(query_text):
                ticker_terms.append(query_text.upper())
                ticker_terms.append(strip_market_suffix(query_text.upper()))
            else:
                name_terms.append(query_text)
                name_terms.extend([token for token in query_text.split() if token])

        if normalized_symbol:
            ticker_terms.append(normalized_symbol.upper())
        if stripped_symbol:
            ticker_terms.append(stripped_symbol.upper())

        aliases = await self._resolve_company_aliases(
            symbol=normalized_symbol or resolved_symbol,
            market=resolved_market,
        )
        name_terms.extend(aliases)

        ticker_terms = self._dedup_terms(ticker_terms, upper=True)
        name_terms = self._dedup_terms(name_terms, upper=False)
        ticker_lower = {item.lower() for item in ticker_terms}
        name_terms = [item for item in name_terms if item.lower() not in ticker_lower]
        return ticker_terms, name_terms

    async def _resolve_company_aliases(self, symbol: str, market: str) -> List[str]:
        normalized_symbol = (symbol or "").strip().upper()
        if not normalized_symbol:
            return []
        resolved_market = (market or "US").strip().upper() or "US"
        cache_key = f"{normalized_symbol}:{resolved_market}"
        cached = self._alias_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        try:
            aliases = await asyncio.to_thread(
                self._load_company_aliases_longbridge,
                normalized_symbol,
                resolved_market,
            )
        except Exception as exc:
            logger.warning(
                "Longbridge company aliases failed for %s: %s",
                normalized_symbol,
                exc,
            )
            aliases = []

        self._alias_cache[cache_key] = list(aliases)
        return aliases

    def _load_company_aliases_longbridge(self, symbol: str, market: str) -> List[str]:
        """Resolve company name aliases via Longbridge static_info API."""
        from longbridge.openapi import Config, QuoteContext

        assert self._lb_config is not None
        config = Config(
            app_key=self._lb_config.app_key,
            app_secret=self._lb_config.app_secret,
            access_token=self._lb_config.access_token,
        )
        ctx = QuoteContext(config)

        lb_symbol = to_longbridge_symbol(symbol, market)
        static_list = ctx.static_info([lb_symbol])
        if not static_list:
            return []

        aliases: List[str] = []
        si = static_list[0]
        for attr in ("name_cn", "name_en", "name_hk"):
            value = getattr(si, attr, None)
            if isinstance(value, str) and value.strip():
                aliases.append(value.strip())
        return NewsTools._dedup_aliases(aliases)

    @staticmethod
    def _dedup_aliases(aliases: List[str]) -> List[str]:
        dedup: List[str] = []
        seen: set[str] = set()
        for alias in aliases:
            token = alias.lower()
            if token in seen:
                continue
            seen.add(token)
            dedup.append(alias)
        return dedup

    @staticmethod
    def _match_stock_terms(
        item: NewsItem,
        ticker_terms: List[str],
        name_terms: List[str],
    ) -> bool:
        text = f"{item.title} {item.source} {item.category} {item.content}"
        text_lower = text.lower()
        for ticker in ticker_terms:
            if NewsTools._contains_ticker(text, ticker):
                return True
        for phrase in name_terms:
            if phrase.lower() in text_lower:
                return True
        return False

    @staticmethod
    def _match_query_words(item: NewsItem, words: List[str]) -> bool:
        if not words:
            return True
        text = f"{item.title} {item.source} {item.category} {item.content}".lower()
        return any(word in text for word in words)

    @staticmethod
    def _contains_ticker(text: str, ticker: str) -> bool:
        token = (ticker or "").strip()
        if not token:
            return False
        pattern = rf"\b{re.escape(token)}\b"
        return bool(re.search(pattern, text, flags=re.IGNORECASE))

    @staticmethod
    def _looks_like_ticker(value: str) -> bool:
        token = (value or "").strip().upper()
        if not token:
            return False
        return bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", token))

    @staticmethod
    def _dedup_terms(values: List[str], upper: bool) -> List[str]:
        output: List[str] = []
        seen = set()
        for item in values:
            text = (item or "").strip()
            if not text:
                continue
            text = text.upper() if upper else text
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(text)
        return output

    @staticmethod
    def _apply_date_filter(
        items: List[NewsItem],
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> List[Tuple[NewsItem, Optional[datetime]]]:
        selected: List[Tuple[NewsItem, Optional[datetime]]] = []
        for row in items:
            published_dt = NewsTools._parse_date(row.published)
            if published_dt and from_dt and published_dt < from_dt:
                continue
            if published_dt and to_dt and published_dt > to_dt:
                continue
            selected.append((row, published_dt))
        return selected

    @staticmethod
    def _fallback_recent_headlines(
        filtered_items: List[Tuple[NewsItem, Optional[datetime]]],
    ) -> List[NewsItem]:
        sorted_items = sorted(
            filtered_items,
            key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return [row for row, _ in sorted_items]

    @staticmethod
    def _to_search_items(rows: List[NewsItem], limit: int) -> List[NewsSearchItem]:
        dedup = set()
        output: List[NewsSearchItem] = []
        for row in rows:
            key = f"{row.title.strip()}::{row.link.strip()}"
            if key in dedup:
                continue
            dedup.add(key)
            output.append(
                NewsSearchItem(
                    title=row.title,
                    media=row.source,
                    published_at=row.published,
                    summary=NewsTools._summary_text(row=row),
                    link=row.link,
                )
            )
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _summary_text(row: NewsItem) -> str:
        content = (row.content or "").strip()
        if content:
            return content[:160]
        return row.title[:160]

    @staticmethod
    def _parse_range_start(value: Optional[str]) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = datetime.strptime(text, "%Y-%m-%d").date()
            return datetime.combine(day, time.min, tzinfo=timezone.utc)
        return NewsTools._parse_date(text)

    @staticmethod
    def _parse_range_end(value: Optional[str]) -> Optional[datetime]:
        text = (value or "").strip()
        if not text:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = datetime.strptime(text, "%Y-%m-%d").date()
            return datetime.combine(day, time.max, tzinfo=timezone.utc)
        return NewsTools._parse_date(text)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
