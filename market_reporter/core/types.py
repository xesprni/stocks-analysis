from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    source_id: str = ""
    category: str
    source: str
    title: str
    link: str = ""
    published: str = ""
    content: str = ""


class FlowPoint(BaseModel):
    market: str
    series_key: str
    series_name: str
    date: str
    value: float
    unit: str


class Quote(BaseModel):
    symbol: str
    market: str
    ts: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[float] = None
    currency: str = ""
    source: str


class KLineBar(BaseModel):
    symbol: str
    market: str
    interval: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    source: str


class CurvePoint(BaseModel):
    symbol: str
    market: str
    ts: str
    price: float
    volume: Optional[float] = None
    source: str


class AnalysisInput(BaseModel):
    symbol: str
    market: str
    quote: Optional[Quote] = None
    kline: List[KLineBar] = Field(default_factory=list)
    curve: List[CurvePoint] = Field(default_factory=list)
    news: List[NewsItem] = Field(default_factory=list)
    fund_flow: Dict[str, List[FlowPoint]] = Field(default_factory=dict)
    watch_meta: Dict[str, Any] = Field(default_factory=dict)


class AnalysisOutput(BaseModel):
    summary: str
    sentiment: str
    key_levels: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    markdown: str
    raw: Dict[str, Any] = Field(default_factory=dict)
