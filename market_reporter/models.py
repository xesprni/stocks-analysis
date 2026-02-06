from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class NewsItem:
    category: str
    source: str
    title: str
    link: str
    published: str


@dataclass
class FlowPoint:
    market: str
    series_key: str
    series_name: str
    date: str
    value: float
    unit: str


@dataclass
class AnalysisFlowSummary:
    series_name: str
    market: str
    unit: str
    latest_date: Optional[str]
    latest_value: Optional[float]
    recent_average: Optional[float]
    change_vs_previous: Optional[float]
    direction: str


@dataclass
class AnalysisResult:
    generated_at: str
    news_total: int
    news_by_category: Dict[str, int]
    top_keywords: List[Tuple[str, int]]
    sentiment_label: str
    sentiment_score: int
    flow_summary: Dict[str, AnalysisFlowSummary] = field(default_factory=dict)
    highlights: List[str] = field(default_factory=list)
