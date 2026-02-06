from __future__ import annotations

import json
from typing import List, Optional

from market_reporter.config import AppConfig
from market_reporter.core.errors import ValidationError
from market_reporter.infra.db.repos import WatchlistRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.watchlist.schemas import WatchlistItem


class WatchlistService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def list_items(self) -> List[WatchlistItem]:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistRepo(session)
            return [self._to_schema(item) for item in repo.list_all()]

    def list_enabled_items(self) -> List[WatchlistItem]:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistRepo(session)
            return [self._to_schema(item) for item in repo.list_enabled()]

    def add_item(
        self,
        symbol: str,
        market: str,
        alias: Optional[str],
        display_name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> WatchlistItem:
        market = market.upper()
        if market not in self.config.watchlist.default_market_scope:
            raise ValidationError(f"Market not allowed by config: {market}")
        normalized = normalize_symbol(symbol=symbol, market=market)
        keywords_json = self._serialize_keywords(keywords)
        with session_scope(self.config.database.url) as session:
            repo = WatchlistRepo(session)
            item = repo.add(
                symbol=normalized,
                market=market,
                alias=alias,
                display_name=display_name,
                keywords_json=keywords_json,
            )
            return self._to_schema(item)

    def update_item(
        self,
        item_id: int,
        alias: Optional[str],
        enabled: Optional[bool],
        display_name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> WatchlistItem:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistRepo(session)
            item = repo.get(item_id)
            if item is None:
                raise ValidationError(f"Watchlist item not found: {item_id}")
            updated = repo.update(
                item=item,
                alias=alias,
                enabled=enabled,
                display_name=display_name,
                keywords_json=self._serialize_keywords(keywords),
            )
            return self._to_schema(updated)

    def delete_item(self, item_id: int) -> bool:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistRepo(session)
            return repo.delete(item_id=item_id)

    def _to_schema(self, item) -> WatchlistItem:
        return WatchlistItem(
            id=item.id,
            symbol=item.symbol,
            market=item.market,
            alias=item.alias,
            display_name=item.display_name,
            keywords=self._deserialize_keywords(item.keywords_json),
            enabled=item.enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _serialize_keywords(keywords: Optional[List[str]]) -> Optional[str]:
        if keywords is None:
            return None
        cleaned = [entry.strip() for entry in keywords if entry and entry.strip()]
        return json.dumps(cleaned, ensure_ascii=False)

    @staticmethod
    def _deserialize_keywords(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return [str(item) for item in payload if str(item).strip()]
