from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ToolEnvelope(BaseModel):
    as_of: str = ""
    source: str = ""
    retrieved_at: str = ""
    warnings: List[str] = Field(default_factory=list)


class PriceBar(BaseModel):
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class PriceHistoryResult(ToolEnvelope):
    symbol: str
    market: str
    interval: str
    adjusted: bool
    bars: List[PriceBar] = Field(default_factory=list)


class FundamentalsResult(ToolEnvelope):
    symbol: str
    market: str
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict)


class FilingItem(BaseModel):
    form_type: str
    filed_at: str = ""
    title: str = ""
    link: str = ""
    content: str = ""


class FilingsResult(ToolEnvelope):
    symbol_or_cik: str
    form_type: str
    filings: List[FilingItem] = Field(default_factory=list)


class NewsSearchItem(BaseModel):
    title: str
    media: str
    published_at: str = ""
    summary: str = ""
    link: str = ""


class NewsSearchResult(ToolEnvelope):
    query: str
    items: List[NewsSearchItem] = Field(default_factory=list)


class MacroSeriesItem(BaseModel):
    series_key: str
    series_name: str
    date: str
    value: float
    unit: str
    market: str


class MacroResult(ToolEnvelope):
    points: List[MacroSeriesItem] = Field(default_factory=list)


class IndicatorsResult(ToolEnvelope):
    symbol: str
    values: Dict[str, Optional[float]] = Field(default_factory=dict)
    trend: Dict[str, Any] = Field(default_factory=dict)
    momentum: Dict[str, Any] = Field(default_factory=dict)
    volume_price: Dict[str, Any] = Field(default_factory=dict)
    patterns: Dict[str, Any] = Field(default_factory=dict)
    support_resistance: Dict[str, Any] = Field(default_factory=dict)
    strategy: Dict[str, Any] = Field(default_factory=dict)
    signal_timeline: List[Dict[str, Any]] = Field(default_factory=list)
    timeframes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class PeerCompareRow(BaseModel):
    symbol: str
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict)


class PeerCompareResult(ToolEnvelope):
    symbol: str
    rows: List[PeerCompareRow] = Field(default_factory=list)


class GuardrailIssue(BaseModel):
    code: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AgentEvidence(BaseModel):
    evidence_id: str
    statement: str
    source: str
    as_of: str
    pointer: str = ""


class ToolCallTrace(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result_preview: Dict[str, Any] = Field(default_factory=dict)


class RuntimeDraft(BaseModel):
    summary: str = ""
    sentiment: str = "neutral"
    key_levels: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    conclusions: List[str] = Field(default_factory=list)
    scenario_assumptions: Dict[str, str] = Field(default_factory=dict)
    markdown: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)


class AgentFinalReport(BaseModel):
    mode: Literal["stock", "market"]
    question: str
    conclusions: List[str] = Field(default_factory=list)
    market_technical: str = ""
    fundamentals: str = ""
    catalysts_risks: str = ""
    valuation_scenarios: str = ""
    data_sources: List[AgentEvidence] = Field(default_factory=list)
    guardrail_issues: List[GuardrailIssue] = Field(default_factory=list)
    confidence: float = 0.5
    markdown: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    mode: Literal["stock", "market"]
    symbol: Optional[str] = None
    market: Optional[str] = None
    question: str = ""
    peer_list: List[str] = Field(default_factory=list)
    indicators: List[str] = Field(default_factory=list)
    news_from: Optional[str] = None
    news_to: Optional[str] = None
    filing_from: Optional[str] = None
    filing_to: Optional[str] = None
    timeframes: List[str] = Field(default_factory=list)
    indicator_profile: Literal["balanced", "trend", "momentum"] = "balanced"


class AgentRunResult(BaseModel):
    analysis_input: Dict[str, Any] = Field(default_factory=dict)
    runtime_draft: RuntimeDraft
    final_report: AgentFinalReport
    tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    guardrail_issues: List[GuardrailIssue] = Field(default_factory=list)
    evidence_map: List[AgentEvidence] = Field(default_factory=list)
