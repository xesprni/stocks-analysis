from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent trace & evidence schemas
# ---------------------------------------------------------------------------


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
    # Visualization fields
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Literal["success", "error", "timeout"] = "success"
    source: Literal["builtin", "mcp", "skill"] = "builtin"


# ---------------------------------------------------------------------------
# Runtime draft & report schemas
# ---------------------------------------------------------------------------


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
    question: str
    conclusions: List[str] = Field(default_factory=list)
    data_sources: List[AgentEvidence] = Field(default_factory=list)
    guardrail_issues: List[GuardrailIssue] = Field(default_factory=list)
    confidence: float = 0.5
    markdown: str
    raw: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent run request & result
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    question: str = ""
    symbol: Optional[str] = None
    market: Optional[str] = None
    # Backward-compatible fields (not required by new agent)
    mode: Literal["stock", "market"] = "stock"
    skill_id: Optional[str] = None
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
