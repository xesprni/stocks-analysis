from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, delete, select

from market_reporter.core.types import CurvePoint, KLineBar
from market_reporter.infra.db.models import (
    AnalysisProviderAccountTable,
    AnalysisProviderAuthStateTable,
    AnalysisProviderSecretTable,
    NewsListenerRunTable,
    StockAnalysisRunTable,
    StockCurvePointTable,
    StockKLineBarTable,
    WatchlistNewsAlertTable,
    WatchlistItemTable,
)


class WatchlistRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> List[WatchlistItemTable]:
        return list(self.session.exec(select(WatchlistItemTable).order_by(WatchlistItemTable.id.desc())).all())

    def list_enabled(self) -> List[WatchlistItemTable]:
        return list(
            self.session.exec(
                select(WatchlistItemTable)
                .where(WatchlistItemTable.enabled.is_(True))
                .order_by(WatchlistItemTable.id.desc())
            ).all()
        )

    def add(
        self,
        symbol: str,
        market: str,
        alias: Optional[str],
        display_name: Optional[str],
        keywords_json: Optional[str],
    ) -> WatchlistItemTable:
        item = WatchlistItemTable(
            symbol=symbol,
            market=market,
            alias=alias,
            display_name=display_name,
            keywords_json=keywords_json,
            enabled=True,
        )
        self.session.add(item)
        # Flush + refresh makes generated fields (for example, id/timestamps) immediately available.
        self.session.flush()
        self.session.refresh(item)
        return item

    def get_by_symbol_market(self, symbol: str, market: str) -> Optional[WatchlistItemTable]:
        return self.session.exec(
            select(WatchlistItemTable)
            .where(WatchlistItemTable.symbol == symbol)
            .where(WatchlistItemTable.market == market)
        ).first()

    def get(self, item_id: int) -> Optional[WatchlistItemTable]:
        return self.session.get(WatchlistItemTable, item_id)

    def update(
        self,
        item: WatchlistItemTable,
        alias: Optional[str],
        enabled: Optional[bool],
        display_name: Optional[str],
        keywords_json: Optional[str],
    ) -> WatchlistItemTable:
        if alias is not None:
            item.alias = alias
        if enabled is not None:
            item.enabled = enabled
        if display_name is not None:
            item.display_name = display_name
        if keywords_json is not None:
            item.keywords_json = keywords_json
        item.updated_at = datetime.utcnow()
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def delete(self, item_id: int) -> bool:
        item = self.session.get(WatchlistItemTable, item_id)
        if item is None:
            return False
        self.session.delete(item)
        self.session.flush()
        return True


class MarketDataRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_kline(self, bars: List[KLineBar]) -> None:
        # Keep upsert behavior portable across engines without vendor-specific SQL.
        for bar in bars:
            existing = self.session.exec(
                select(StockKLineBarTable)
                .where(StockKLineBarTable.symbol == bar.symbol)
                .where(StockKLineBarTable.market == bar.market)
                .where(StockKLineBarTable.interval == bar.interval)
                .where(StockKLineBarTable.ts == bar.ts)
            ).first()
            if existing is None:
                existing = StockKLineBarTable(
                    symbol=bar.symbol,
                    market=bar.market,
                    interval=bar.interval,
                    ts=bar.ts,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    source=bar.source,
                )
            else:
                existing.open = bar.open
                existing.high = bar.high
                existing.low = bar.low
                existing.close = bar.close
                existing.volume = bar.volume
                existing.source = bar.source
            self.session.add(existing)

    def save_curve_points(self, points: List[CurvePoint], max_points: int = 2000) -> None:
        for point in points:
            row = StockCurvePointTable(
                symbol=point.symbol,
                market=point.market,
                ts=point.ts,
                price=point.price,
                volume=point.volume,
                source=point.source,
            )
            self.session.add(row)

        if not points:
            return

        symbol = points[0].symbol
        market = points[0].market
        # Read newest first so rows beyond retention can be dropped in one pass.
        rows = list(
            self.session.exec(
                select(StockCurvePointTable)
                .where(StockCurvePointTable.symbol == symbol)
                .where(StockCurvePointTable.market == market)
                .order_by(StockCurvePointTable.id.desc())
            ).all()
        )
        for stale in rows[max_points:]:
            self.session.delete(stale)

    def list_curve_points(self, symbol: str, market: str, limit: int = 500) -> List[StockCurvePointTable]:
        rows = list(
            self.session.exec(
                select(StockCurvePointTable)
                .where(StockCurvePointTable.symbol == symbol)
                .where(StockCurvePointTable.market == market)
                .order_by(StockCurvePointTable.id.desc())
                .limit(limit)
            ).all()
        )
        # Queries run descending for efficiency; API returns ascending for chart rendering.
        rows.reverse()
        return rows

    def list_kline(self, symbol: str, market: str, interval: str, limit: int = 500) -> List[StockKLineBarTable]:
        rows = list(
            self.session.exec(
                select(StockKLineBarTable)
                .where(StockKLineBarTable.symbol == symbol)
                .where(StockKLineBarTable.market == market)
                .where(StockKLineBarTable.interval == interval)
                .order_by(StockKLineBarTable.id.desc())
                .limit(limit)
            ).all()
        )
        # Queries run descending for efficiency; API returns ascending for chart rendering.
        rows.reverse()
        return rows


class AnalysisProviderSecretRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, provider_id: str, ciphertext: str, nonce: str) -> AnalysisProviderSecretTable:
        row = self.session.exec(
            select(AnalysisProviderSecretTable).where(AnalysisProviderSecretTable.provider_id == provider_id)
        ).first()
        if row is None:
            row = AnalysisProviderSecretTable(
                provider_id=provider_id,
                key_ciphertext=ciphertext,
                nonce=nonce,
            )
        else:
            row.key_ciphertext = ciphertext
            row.nonce = nonce
            row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def get(self, provider_id: str) -> Optional[AnalysisProviderSecretTable]:
        return self.session.exec(
            select(AnalysisProviderSecretTable).where(AnalysisProviderSecretTable.provider_id == provider_id)
        ).first()

    def delete(self, provider_id: str) -> bool:
        row = self.get(provider_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True


class AnalysisProviderAccountRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        provider_id: str,
        account_type: str,
        credential_ciphertext: str,
        nonce: str,
        expires_at: Optional[datetime],
    ) -> AnalysisProviderAccountTable:
        row = self.session.exec(
            select(AnalysisProviderAccountTable).where(AnalysisProviderAccountTable.provider_id == provider_id)
        ).first()
        if row is None:
            row = AnalysisProviderAccountTable(
                provider_id=provider_id,
                account_type=account_type,
                credential_ciphertext=credential_ciphertext,
                nonce=nonce,
                expires_at=expires_at,
            )
        else:
            row.account_type = account_type
            row.credential_ciphertext = credential_ciphertext
            row.nonce = nonce
            row.expires_at = expires_at
            row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def get(self, provider_id: str) -> Optional[AnalysisProviderAccountTable]:
        return self.session.exec(
            select(AnalysisProviderAccountTable).where(AnalysisProviderAccountTable.provider_id == provider_id)
        ).first()

    def delete(self, provider_id: str) -> bool:
        row = self.get(provider_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True


class AnalysisProviderAuthStateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        state: str,
        provider_id: str,
        redirect_to: Optional[str],
        expires_at: datetime,
    ) -> AnalysisProviderAuthStateTable:
        row = AnalysisProviderAuthStateTable(
            state=state,
            provider_id=provider_id,
            redirect_to=redirect_to,
            expires_at=expires_at,
            used=False,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def get_valid(self, state: str, provider_id: str, now: datetime) -> Optional[AnalysisProviderAuthStateTable]:
        return self.session.exec(
            select(AnalysisProviderAuthStateTable)
            .where(AnalysisProviderAuthStateTable.state == state)
            .where(AnalysisProviderAuthStateTable.provider_id == provider_id)
            .where(AnalysisProviderAuthStateTable.used.is_(False))
            .where(AnalysisProviderAuthStateTable.expires_at >= now)
        ).first()

    def mark_used(self, row: AnalysisProviderAuthStateTable) -> AnalysisProviderAuthStateTable:
        row.used = True
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def delete_expired(self, now: datetime) -> int:
        # Bulk-delete in Python to keep behavior predictable on SQLite.
        expired_rows = list(
            self.session.exec(
                select(AnalysisProviderAuthStateTable).where(AnalysisProviderAuthStateTable.expires_at < now)
            ).all()
        )
        for row in expired_rows:
            self.session.delete(row)
        self.session.flush()
        return len(expired_rows)


class StockAnalysisRunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        symbol: str,
        market: str,
        provider_id: str,
        model: str,
        status: str,
        input_json: str,
        output_json: str,
        markdown: str,
    ) -> StockAnalysisRunTable:
        row = StockAnalysisRunTable(
            symbol=symbol,
            market=market,
            provider_id=provider_id,
            model=model,
            status=status,
            input_json=input_json,
            output_json=output_json,
            markdown=markdown,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def list_by_symbol(self, symbol: str, market: str, limit: int = 20) -> List[StockAnalysisRunTable]:
        return list(
            self.session.exec(
                select(StockAnalysisRunTable)
                .where(StockAnalysisRunTable.symbol == symbol)
                .where(StockAnalysisRunTable.market == market)
                .order_by(StockAnalysisRunTable.id.desc())
                .limit(limit)
            ).all()
        )

    def get(self, run_id: int) -> Optional[StockAnalysisRunTable]:
        return self.session.get(StockAnalysisRunTable, run_id)

    def list_recent(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        market: Optional[str] = None,
    ) -> List[StockAnalysisRunTable]:
        statement = select(StockAnalysisRunTable).order_by(
            StockAnalysisRunTable.id.desc()
        )
        if symbol:
            statement = statement.where(StockAnalysisRunTable.symbol == symbol)
        if market:
            statement = statement.where(StockAnalysisRunTable.market == market)
        statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

    def delete(self, run_id: int) -> bool:
        row = self.get(run_id=run_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True


class NewsListenerRunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        scanned_news_count: int,
        matched_news_count: int,
        alerts_count: int,
        error_message: Optional[str] = None,
    ) -> NewsListenerRunTable:
        row = NewsListenerRunTable(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            scanned_news_count=scanned_news_count,
            matched_news_count=matched_news_count,
            alerts_count=alerts_count,
            error_message=error_message,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def list_recent(self, limit: int = 50) -> List[NewsListenerRunTable]:
        return list(self.session.exec(select(NewsListenerRunTable).order_by(NewsListenerRunTable.id.desc()).limit(limit)).all())


class WatchlistNewsAlertRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_many(
        self,
        rows: List[WatchlistNewsAlertTable],
    ) -> None:
        for row in rows:
            self.session.add(row)
        self.session.flush()

    def list_recent(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        market: Optional[str] = None,
        limit: int = 50,
    ) -> List[WatchlistNewsAlertTable]:
        # Build filters incrementally so callers can combine status/symbol/market constraints.
        statement = select(WatchlistNewsAlertTable).order_by(WatchlistNewsAlertTable.id.desc()).limit(limit)
        if status and status != "ALL":
            statement = statement.where(WatchlistNewsAlertTable.status == status)
        if symbol:
            statement = statement.where(WatchlistNewsAlertTable.symbol == symbol)
        if market:
            statement = statement.where(WatchlistNewsAlertTable.market == market)
        return list(self.session.exec(statement).all())

    def get(self, alert_id: int) -> Optional[WatchlistNewsAlertTable]:
        return self.session.get(WatchlistNewsAlertTable, alert_id)

    def update_status(self, row: WatchlistNewsAlertTable, status: str) -> WatchlistNewsAlertTable:
        row.status = status
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def mark_all_read(self) -> int:
        rows = list(
            self.session.exec(
                select(WatchlistNewsAlertTable).where(WatchlistNewsAlertTable.status == "UNREAD")
            ).all()
        )
        for row in rows:
            row.status = "READ"
            self.session.add(row)
        self.session.flush()
        return len(rows)
