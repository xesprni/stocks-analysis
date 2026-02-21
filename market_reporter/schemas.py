from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from market_reporter.config import AppConfig


class ReportRunSummary(BaseModel):
    run_id: str
    generated_at: str
    report_path: Path
    raw_data_path: Path
    warnings_count: int = 0
    news_total: int = 0
    provider_id: str = ""
    model: str = ""
    confidence: Optional[float] = None
    sentiment: Optional[str] = None
    mode: Optional[str] = None


class ReportRunDetail(BaseModel):
    summary: ReportRunSummary
    report_markdown: str
    raw_data: Dict[str, Any]


class RunRequest(BaseModel):
    skill_id: Optional[str] = None
    news_limit: Optional[int] = Field(default=None, ge=1, le=100)
    flow_periods: Optional[int] = Field(default=None, ge=1, le=120)
    timezone: Optional[str] = None
    provider_id: Optional[str] = None
    model: Optional[str] = None
    mode: str = Field(default="market", pattern="^(market|stock|watchlist)$")
    symbol: Optional[str] = None
    market: Optional[str] = Field(default=None, pattern="^(CN|HK|US)$")
    question: Optional[str] = None
    peer_list: Optional[List[str]] = None
    watchlist_limit: Optional[int] = Field(default=None, ge=1, le=50)


class RunResult(BaseModel):
    summary: ReportRunSummary
    warnings: List[str]


class ReportTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ReportRunTaskView(BaseModel):
    task_id: str
    status: ReportTaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[RunResult] = None


class ConfigUpdateRequest(BaseModel):
    output_root: Path
    timezone: str
    news_limit: int = Field(ge=1, le=100)
    flow_periods: int = Field(ge=1, le=120)
    request_timeout_seconds: int = Field(ge=3, le=120)
    user_agent: str
    modules: Dict[str, Any]
    analysis: Dict[str, Any]
    watchlist: Dict[str, Any]
    news_listener: Optional[Dict[str, Any]] = None
    symbol_search: Optional[Dict[str, Any]] = None
    dashboard: Optional[Dict[str, Any]] = None
    agent: Optional[Dict[str, Any]] = None
    longbridge: Optional[Dict[str, Any]] = None
    database: Dict[str, Any]

    def to_config(self, current: AppConfig) -> AppConfig:
        payload = current.model_dump(mode="python")
        patch_data = {
            "output_root": self.output_root,
            "timezone": self.timezone,
            "news_limit": self.news_limit,
            "flow_periods": self.flow_periods,
            "request_timeout_seconds": self.request_timeout_seconds,
            "user_agent": self.user_agent,
            "modules": self.modules,
            "analysis": self.analysis,
            "watchlist": self.watchlist,
            "database": self.database,
        }
        if self.news_listener is not None:
            patch_data["news_listener"] = self.news_listener
        if self.symbol_search is not None:
            patch_data["symbol_search"] = self.symbol_search
        if self.dashboard is not None:
            patch_data["dashboard"] = self.dashboard
        if self.agent is not None:
            patch_data["agent"] = self.agent
        if self.longbridge is not None:
            next_lb = dict(self.longbridge)
            current_lb = current.longbridge
            if str(next_lb.get("app_secret") or "").strip() == "***":
                next_lb["app_secret"] = current_lb.app_secret
            if str(next_lb.get("access_token") or "").strip() == "***":
                next_lb["access_token"] = current_lb.access_token
            app_key = str(next_lb.get("app_key") or "").strip()
            app_secret = str(next_lb.get("app_secret") or "").strip()
            access_token = str(next_lb.get("access_token") or "").strip()
            next_lb["enabled"] = bool(app_key and app_secret and access_token)
            patch_data["longbridge"] = next_lb
        payload.update(patch_data)
        return AppConfig.model_validate(payload)


class UIOptionsResponse(BaseModel):
    markets: List[str]
    intervals: List[str]
    timezones: List[str]
    news_providers: List[str]
    fund_flow_providers: List[str]
    market_data_providers: List[str]
    analysis_providers: List[str]
    analysis_models_by_provider: Dict[str, List[str]]
    listener_threshold_presets: List[float]
    listener_intervals: List[int]
