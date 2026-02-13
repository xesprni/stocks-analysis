from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from market_reporter.modules.agent.schemas import PriceBar, PriceHistoryResult
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, to_yfinance_symbol


def infer_market_from_symbol(symbol: str, fallback: str = "US") -> str:
    raw = (symbol or "").strip().upper()
    if raw.endswith(".HK"):
        return "HK"
    if raw.endswith(".SH") or raw.endswith(".SZ") or raw.endswith(".BJ"):
        return "CN"
    return fallback.upper() if fallback else "US"


class MarketTools:
    async def get_price_history(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str,
        adjusted: bool,
        market: Optional[str] = None,
    ) -> PriceHistoryResult:
        return await asyncio.to_thread(
            self._get_price_history_sync,
            symbol,
            start,
            end,
            interval,
            adjusted,
            market,
        )

    def _get_price_history_sync(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str,
        adjusted: bool,
        market: Optional[str],
    ) -> PriceHistoryResult:
        import yfinance as yf

        resolved_market = infer_market_from_symbol(symbol, fallback=market or "US")
        normalized_symbol = normalize_symbol(symbol, resolved_market)
        yf_symbol = to_yfinance_symbol(normalized_symbol, resolved_market)

        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(
            start=start,
            end=end,
            interval=interval,
            auto_adjust=bool(adjusted),
        )

        bars = []
        if hist is not None and not hist.empty:
            for idx, row in hist.iterrows():
                bars.append(
                    PriceBar(
                        ts=idx.to_pydatetime().isoformat(timespec="seconds"),
                        open=float(row.get("Open") or 0.0),
                        high=float(row.get("High") or 0.0),
                        low=float(row.get("Low") or 0.0),
                        close=float(row.get("Close") or 0.0),
                        volume=float(row.get("Volume")) if row.get("Volume") is not None else None,
                    )
                )

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        as_of = bars[-1].ts if bars else retrieved_at
        return PriceHistoryResult(
            symbol=normalized_symbol,
            market=resolved_market,
            interval=interval,
            adjusted=bool(adjusted),
            bars=bars,
            as_of=as_of,
            source="yfinance",
            retrieved_at=retrieved_at,
            warnings=[] if bars else ["empty_price_history"],
        )
