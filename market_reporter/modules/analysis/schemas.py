from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from market_reporter.core.types import AnalysisOutput


class ProviderModelSelectionRequest(BaseModel):
    provider_id: str
    model: str


class ProviderSecretRequest(BaseModel):
    api_key: str = Field(min_length=1)


class AnalysisProviderView(BaseModel):
    provider_id: str
    type: str
    base_url: str
    models: List[str]
    timeout: int
    enabled: bool
    has_secret: bool
    secret_required: bool
    ready: bool
    status: str
    status_message: str
    is_default: bool
    auth_mode: str = "api_key"
    connected: bool = False
    credential_expires_at: Optional[datetime] = None


class ProviderAuthStartRequest(BaseModel):
    redirect_to: Optional[str] = None


class ProviderAuthStartResponse(BaseModel):
    provider_id: str
    auth_url: str
    state: str
    expires_at: datetime


class ProviderAuthStatusView(BaseModel):
    provider_id: str
    auth_mode: str
    connected: bool
    status: str
    message: str = ""
    expires_at: Optional[datetime] = None


class ProviderModelsView(BaseModel):
    provider_id: str
    models: List[str]
    source: str = "config"


class StockAnalysisRunRequest(BaseModel):
    market: str = Field(pattern="^(CN|HK|US)$")
    provider_id: Optional[str] = None
    model: Optional[str] = None
    interval: str = Field(default="5m", pattern="^(1m|5m|1d)$")
    lookback_bars: int = Field(default=120, ge=30, le=500)
    question: Optional[str] = None
    peer_list: Optional[List[str]] = None
    indicators: Optional[List[str]] = None
    news_from: Optional[str] = None
    news_to: Optional[str] = None
    filing_from: Optional[str] = None
    filing_to: Optional[str] = None
    timeframes: Optional[List[str]] = None
    indicator_profile: Optional[str] = Field(
        default=None, pattern="^(balanced|trend|momentum)$"
    )


class StockAnalysisRunView(BaseModel):
    id: int
    symbol: str
    market: str
    provider_id: str
    model: str
    status: str
    output: AnalysisOutput
    markdown: str
    created_at: datetime


class StockAnalysisHistoryItem(BaseModel):
    id: int
    symbol: str
    market: str
    provider_id: str
    model: str
    status: str
    created_at: datetime
    markdown: str
    output_json: Dict[str, Any]


class StockAnalysisTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class StockAnalysisTaskView(BaseModel):
    task_id: str
    symbol: str
    market: str
    status: StockAnalysisTaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[StockAnalysisRunView] = None
