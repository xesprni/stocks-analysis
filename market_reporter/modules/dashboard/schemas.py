from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PaginationView(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class DashboardIndexMetricView(BaseModel):
    symbol: str
    market: str
    alias: Optional[str] = None
    ts: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[float] = None
    currency: str = ""
    source: str


class DashboardWatchlistMetricView(BaseModel):
    id: int
    symbol: str
    market: str
    alias: Optional[str] = None
    display_name: Optional[str] = None
    enabled: bool
    ts: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[float] = None
    currency: str = ""
    source: str


class DashboardSnapshotView(BaseModel):
    generated_at: datetime
    auto_refresh_enabled: bool
    auto_refresh_seconds: int
    indices: list[DashboardIndexMetricView]
    watchlist: list[DashboardWatchlistMetricView]
    pagination: PaginationView


class DashboardIndicesSnapshotView(BaseModel):
    generated_at: datetime
    auto_refresh_enabled: bool
    auto_refresh_seconds: int
    indices: list[DashboardIndexMetricView]


class DashboardWatchlistSnapshotView(BaseModel):
    generated_at: datetime
    auto_refresh_enabled: bool
    auto_refresh_seconds: int
    watchlist: list[DashboardWatchlistMetricView]
    pagination: PaginationView


class DashboardAutoRefreshUpdateRequest(BaseModel):
    auto_refresh_enabled: bool


class DashboardAutoRefreshView(BaseModel):
    auto_refresh_enabled: bool
    auto_refresh_seconds: int
