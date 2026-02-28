from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class UserTable(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, max_length=64)
    email: Optional[str] = Field(default=None, max_length=256)
    display_name: Optional[str] = Field(default=None, max_length=128)
    password_hash: str = Field(default="")
    is_admin: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ApiKeyTable(SQLModel, table=True):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    key_hash: str = Field(index=True)
    key_prefix: str = Field(max_length=16)
    name: Optional[str] = Field(default=None, max_length=128)
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WatchlistItemTable(SQLModel, table=True):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "symbol", "market", name="uq_watchlist_user_symbol_market"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
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
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "market",
            "interval",
            "ts",
            name="uq_kline_symbol_market_interval_ts",
        ),
    )

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


class LongbridgeCredentialTable(SQLModel, table=True):
    __tablename__ = "longbridge_credentials"

    id: Optional[int] = Field(default=None, primary_key=True)
    credential_ciphertext: str
    nonce: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TelegramConfigTable(SQLModel, table=True):
    __tablename__ = "telegram_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    config_ciphertext: str
    nonce: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisProviderAccountTable(SQLModel, table=True):
    __tablename__ = "analysis_provider_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider_id: str = Field(index=True, unique=True)
    account_type: str = Field(default="chatgpt")
    credential_ciphertext: str
    nonce: str
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisProviderAuthStateTable(SQLModel, table=True):
    __tablename__ = "analysis_provider_auth_states"

    id: Optional[int] = Field(default=None, primary_key=True)
    state: str = Field(index=True, unique=True)
    provider_id: str = Field(index=True)
    redirect_to: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    used: bool = Field(default=False, index=True)


class StockAnalysisRunTable(SQLModel, table=True):
    __tablename__ = "stock_analysis_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
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


class NewsSourceTable(SQLModel, table=True):
    __tablename__ = "news_sources"
    __table_args__ = (UniqueConstraint("source_id", name="uq_news_source_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(index=True)
    name: str
    category: str
    url: str
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
