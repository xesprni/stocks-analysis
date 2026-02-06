from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class WatchlistItemTable(SQLModel, table=True):
    __tablename__ = "watchlist_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    alias: Optional[str] = None
    display_name: Optional[str] = None
    keywords_json: Optional[str] = None
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StockKLineBarTable(SQLModel, table=True):
    __tablename__ = "stock_kline_bars"
    __table_args__ = (UniqueConstraint("symbol", "market", "interval", "ts", name="uq_kline_symbol_market_interval_ts"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    interval: str = Field(index=True)
    ts: str = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    source: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StockCurvePointTable(SQLModel, table=True):
    __tablename__ = "stock_curve_points"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    ts: str = Field(index=True)
    price: float
    volume: Optional[float] = None
    source: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisProviderSecretTable(SQLModel, table=True):
    __tablename__ = "analysis_provider_secrets"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider_id: str = Field(index=True, unique=True)
    key_ciphertext: str
    nonce: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StockAnalysisRunTable(SQLModel, table=True):
    __tablename__ = "stock_analysis_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    provider_id: str = Field(index=True)
    model: str
    status: str = Field(index=True)
    input_json: str
    output_json: str
    markdown: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class NewsListenerRunTable(SQLModel, table=True):
    __tablename__ = "news_listener_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(index=True)
    scanned_news_count: int = 0
    matched_news_count: int = 0
    alerts_count: int = 0
    error_message: Optional[str] = None


class WatchlistNewsAlertTable(SQLModel, table=True):
    __tablename__ = "watchlist_news_alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="news_listener_runs.id", index=True)
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    news_title: str
    news_link: Optional[str] = None
    news_source: Optional[str] = None
    published_at: Optional[str] = None
    move_window_minutes: int
    price_change_percent: float
    threshold_percent: float
    severity: str = Field(index=True)
    analysis_summary: str
    analysis_markdown: str
    analysis_json: str
    status: str = Field(default="UNREAD", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
