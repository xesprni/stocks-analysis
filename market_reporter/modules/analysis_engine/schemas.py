from __future__ import annotations

from datetime import datetime
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


class StockAnalysisRunRequest(BaseModel):
    market: str = Field(pattern="^(CN|HK|US)$")
    provider_id: Optional[str] = None
    model: Optional[str] = None
    interval: str = Field(default="5m", pattern="^(1m|5m|1d)$")
    lookback_bars: int = Field(default=120, ge=30, le=500)


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
