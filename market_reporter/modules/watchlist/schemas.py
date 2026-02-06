from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WatchlistCreateRequest(BaseModel):
    symbol: str = Field(min_length=1)
    market: str = Field(pattern="^(CN|HK|US)$")
    alias: Optional[str] = None
    display_name: Optional[str] = None
    keywords: Optional[list[str]] = None


class WatchlistUpdateRequest(BaseModel):
    alias: Optional[str] = None
    enabled: Optional[bool] = None
    display_name: Optional[str] = None
    keywords: Optional[list[str]] = None


class WatchlistItem(BaseModel):
    id: int
    symbol: str
    market: str
    alias: Optional[str] = None
    display_name: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    enabled: bool
    created_at: datetime
    updated_at: datetime
