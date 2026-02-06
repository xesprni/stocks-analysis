from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NewsListenerRunView(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime
    status: str
    scanned_news_count: int
    matched_news_count: int
    alerts_count: int
    error_message: Optional[str] = None


class NewsAlertView(BaseModel):
    id: int
    run_id: int
    symbol: str
    market: str
    news_title: str
    news_link: str = ""
    news_source: str = ""
    published_at: str = ""
    move_window_minutes: int
    price_change_percent: float
    threshold_percent: float
    severity: str
    analysis_summary: str
    analysis_markdown: str
    analysis_json: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


class NewsAlertStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(READ|DISMISSED)$")


class MatchedAlertCandidate(BaseModel):
    symbol: str
    market: str
    news_title: str
    news_link: str = ""
    news_source: str = ""
    published_at: str = ""
    price_change_percent: float
    threshold_percent: float
    move_window_minutes: int
    severity: str = "MEDIUM"
    watch_keywords: List[str] = Field(default_factory=list)
