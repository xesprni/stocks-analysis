from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from market_reporter.core.types import AnalysisInput, AnalysisOutput, CurvePoint, FlowPoint, KLineBar, NewsItem, Quote

# 这个文件定义了 5 个 Protocol 类，它们是 Python 的接口协议，用于定义数据提供者的契约/接口规范。
# Protocol 是 Python 3.8+ 引入的结构化子类型（Structural Subtyping）机制，类似于其他语言中的 Interface（接口）。它定义了一组方法签名，任何实现了这些方法的类都会自动被视为该 Protocol 的实现者，无需显式继承。
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
