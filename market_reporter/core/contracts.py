from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from market_reporter.core.types import AnalysisInput, AnalysisOutput, CurvePoint, FlowPoint, KLineBar, NewsItem, Quote


class NewsProvider(Protocol):
    provider_id: str

    async def collect(self, limit: int) -> List[NewsItem]:
        ...


class FundFlowProvider(Protocol):
    provider_id: str

    async def collect(self, periods: int) -> Dict[str, List[FlowPoint]]:
        ...


class MarketDataProvider(Protocol):
    provider_id: str

    async def get_quote(self, symbol: str, market: str) -> Quote:
        ...

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        ...

    async def get_curve(self, symbol: str, market: str, window: str) -> List[CurvePoint]:
        ...


class AnalysisProvider(Protocol):
    provider_id: str

    async def analyze(self, payload: AnalysisInput, model: str, api_key: Optional[str] = None) -> AnalysisOutput:
        ...


class SymbolSearchProvider(Protocol):
    provider_id: str

    async def search(self, query: str, market: str, limit: int) -> List[dict]:
        ...
