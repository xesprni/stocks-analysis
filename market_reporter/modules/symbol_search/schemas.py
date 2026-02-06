from __future__ import annotations

from pydantic import BaseModel, Field


class StockSearchResult(BaseModel):
    symbol: str
    market: str = Field(pattern="^(CN|HK|US)$")
    name: str
    exchange: str = ""
    source: str
    score: float = Field(default=0.5, ge=0.0, le=1.0)
