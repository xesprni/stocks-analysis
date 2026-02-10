from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

from market_reporter.core.types import CurvePoint, KLineBar, Quote
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol, strip_market_suffix


class AkshareMarketDataProvider:
    provider_id = "akshare"

    async def get_quote(self, symbol: str, market: str) -> Quote:
        # akshare calls are sync and can be slow; isolate them in worker threads.
        return await asyncio.to_thread(self._get_quote_sync, symbol, market)

    async def get_kline(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        return await asyncio.to_thread(self._get_kline_sync, symbol, market, interval, limit)

    async def get_curve(self, symbol: str, market: str, window: str) -> List[CurvePoint]:
        bars = await self.get_kline(symbol=symbol, market=market, interval="1m", limit=300)
        return [
            CurvePoint(
                symbol=bar.symbol,
                market=bar.market,
                ts=bar.ts,
                price=bar.close,
                volume=bar.volume,
                source=self.provider_id,
            )
            for bar in bars
        ]

    def _get_quote_sync(self, symbol: str, market: str) -> Quote:
        import akshare as ak

        market = market.upper()
        normalized = normalize_symbol(symbol, market)
        code = strip_market_suffix(normalized)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if market == "CN":
            # CN/HK/US use different akshare spot endpoints.
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code].head(1)
            if row.empty:
                raise ValueError(f"CN quote not found: {symbol}")
            r = row.iloc[0]
            return Quote(
                symbol=normalized,
                market=market,
                ts=now,
                price=float(r["最新价"]),
                change=float(r["涨跌额"]),
                change_percent=float(r["涨跌幅"]),
                volume=float(r["成交量"]),
                currency="CNY",
                source=self.provider_id,
            )

        if market == "HK":
            df = ak.stock_hk_spot_em()
            row = df[df["代码"].astype(str).str.zfill(4) == code.zfill(4)].head(1)
            if row.empty:
                raise ValueError(f"HK quote not found: {symbol}")
            r = row.iloc[0]
            return Quote(
                symbol=normalized,
                market=market,
                ts=now,
                price=float(r["最新价"]),
                change=float(r.get("涨跌额", 0.0)),
                change_percent=float(r.get("涨跌幅", 0.0)),
                volume=float(r.get("成交量", 0.0)),
                currency="HKD",
                source=self.provider_id,
            )

        df = ak.stock_us_spot_em()
        row = df[df["代码"].astype(str).str.upper() == code.upper()].head(1)
        if row.empty:
            raise ValueError(f"US quote not found: {symbol}")
        r = row.iloc[0]
        return Quote(
            symbol=normalized,
            market=market,
            ts=now,
            price=float(r["最新价"]),
            change=float(r.get("涨跌额", 0.0)),
            change_percent=float(r.get("涨跌幅", 0.0)),
            volume=float(r.get("成交量", 0.0)),
            currency="USD",
            source=self.provider_id,
        )

    def _get_kline_sync(self, symbol: str, market: str, interval: str, limit: int) -> List[KLineBar]:
        import akshare as ak

        market = market.upper()
        normalized = normalize_symbol(symbol, market)
        code = strip_market_suffix(normalized)
        rows: List[KLineBar] = []

        if market == "CN" and interval in {"1m", "5m"}:
            period = "1" if interval == "1m" else "5"
            df = ak.stock_zh_a_hist_min_em(symbol=code, period=period, adjust="")
            for _, row in df.tail(limit).iterrows():
                rows.append(
                    KLineBar(
                        symbol=normalized,
                        market=market,
                        interval=interval,
                        ts=str(row["时间"]),
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row.get("成交量", 0.0)),
                        source=self.provider_id,
                    )
                )
            return rows

        if market == "CN" and interval == "1d":
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="")
            for _, row in df.tail(limit).iterrows():
                rows.append(
                    KLineBar(
                        symbol=normalized,
                        market=market,
                        interval=interval,
                        ts=str(row["日期"]),
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row.get("成交量", 0.0)),
                        source=self.provider_id,
                    )
                )
            return rows

        # Current provider implementation intentionally limits scope to CN bars.
        raise ValueError(f"Akshare kline unsupported for market={market}, interval={interval}")
