from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from market_reporter.modules.analysis.agent.schemas import (
    IndicatorsResult,
    PeerCompareResult,
    PeerCompareRow,
)
from market_reporter.modules.analysis.agent.tools.fundamentals_tools import (
    FundamentalsTools,
)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


class ComputeTools:
    def __init__(self, fundamentals_tools: FundamentalsTools) -> None:
        self.fundamentals_tools = fundamentals_tools

    def compute_indicators(
        self,
        price_df: Any,
        indicators: Optional[List[str]] = None,
        symbol: str = "",
        indicator_profile: str = "balanced",
    ) -> IndicatorsResult:
        wanted = [
            item.strip().upper()
            for item in (indicators or ["RSI", "MACD", "MA", "ATR", "VOL"])
            if item and item.strip()
        ]
        timeframe_payload = self._normalize_price_payload(price_df)
        warnings: List[str] = []
        if not timeframe_payload:
            warnings.append("empty_price_df")

        ordered_timeframes = self._ordered_timeframes(list(timeframe_payload.keys()))
        timeframe_results: Dict[str, Dict[str, Any]] = {}
        signal_timeline: List[Dict[str, Any]] = []
        resolved_backends: List[str] = []
        for timeframe in ordered_timeframes:
            rows = timeframe_payload.get(timeframe) or []
            result = self._analyze_timeframe(
                rows=rows,
                timeframe=timeframe,
                wanted=wanted,
            )
            timeframe_results[timeframe] = result
            if isinstance(result.get("signal_timeline"), list):
                signal_timeline.extend(result["signal_timeline"])
            if isinstance(result.get("warnings"), list):
                warnings.extend([str(item) for item in result["warnings"]])
            backend = str(result.get("indicator_backend") or "").strip()
            if backend:
                resolved_backends.append(backend)

        signal_timeline.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)

        primary_timeframe = (
            "1d"
            if "1d" in timeframe_results
            else (ordered_timeframes[0] if ordered_timeframes else "")
        )
        primary = timeframe_results.get(primary_timeframe, {})

        trend = self._merge_category(timeframe_results, "trend")
        momentum = self._merge_category(timeframe_results, "momentum")
        volume_price = self._merge_category(timeframe_results, "volume_price")
        patterns = self._merge_category(timeframe_results, "patterns")
        support_resistance = self._merge_category(
            timeframe_results, "support_resistance"
        )

        strategy = self._build_strategy(
            timeframe_results=timeframe_results,
            profile=indicator_profile,
            primary_timeframe=primary_timeframe,
        )

        values = dict(primary.get("values") or {})
        as_of = str(
            primary.get("as_of")
            or datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dedup_warnings = list(
            dict.fromkeys([str(item) for item in warnings if str(item).strip()])
        )
        backend = self._resolve_backend(primary=primary, candidates=resolved_backends)

        return IndicatorsResult(
            symbol=symbol,
            values=values,
            trend=trend,
            momentum=momentum,
            volume_price=volume_price,
            patterns=patterns,
            support_resistance=support_resistance,
            strategy=strategy,
            signal_timeline=signal_timeline,
            timeframes=timeframe_results,
            as_of=as_of,
            source=f"{backend}/computed",
            retrieved_at=retrieved_at,
            warnings=dedup_warnings,
        )

    async def peer_compare(
        self,
        symbol: str,
        peer_list: List[str],
        metrics: Optional[List[str]] = None,
        market: str = "US",
    ) -> PeerCompareResult:
        resolved_metrics = metrics or [
            "market_cap",
            "trailing_pe",
            "revenue",
            "net_income",
            "net_margin",
        ]

        rows: List[PeerCompareRow] = []
        warnings: List[str] = []
        if not peer_list:
            warnings.append("peer_list_missing")

        targets = [symbol] + [item for item in peer_list if item]
        for ticker in targets:
            try:
                result = await self.fundamentals_tools.get_fundamentals(
                    symbol=ticker,
                    market=market,
                )
                metrics_payload: Dict[str, Optional[float]] = {}
                for key in resolved_metrics:
                    if key == "net_margin":
                        revenue = result.metrics.get("revenue")
                        net_income = result.metrics.get("net_income")
                        if revenue and net_income is not None and revenue != 0:
                            metrics_payload[key] = float(net_income) / float(revenue)
                        else:
                            metrics_payload[key] = None
                    else:
                        metrics_payload[key] = result.metrics.get(key)
                rows.append(
                    PeerCompareRow(symbol=result.symbol, metrics=metrics_payload)
                )
            except Exception as exc:
                warnings.append(f"peer_compare_failed:{ticker}:{exc}")

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return PeerCompareResult(
            symbol=symbol,
            rows=rows,
            as_of=retrieved_at,
            source="yfinance/computed",
            retrieved_at=retrieved_at,
            warnings=warnings,
        )

    def _analyze_timeframe(
        self,
        rows: List[Dict[str, Any]],
        timeframe: str,
        wanted: List[str],
    ) -> Dict[str, Any]:
        del wanted
        normalized_rows = self._normalize_rows(rows)
        warnings: List[str] = []
        if len(normalized_rows) < 30:
            warnings.append(f"insufficient_bars:{timeframe}")

        if not normalized_rows:
            as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return {
                "as_of": as_of,
                "indicator_backend": "builtin",
                "values": {},
                "trend": {},
                "momentum": {},
                "volume_price": {},
                "patterns": {},
                "support_resistance": {
                    "supports": [],
                    "resistances": [],
                    "pivot_meta": {
                        "method": "swing_cluster",
                        "touch_counts": {},
                    },
                },
                "signal_timeline": [],
                "warnings": warnings,
            }

        closes = [item["close"] for item in normalized_rows]
        highs = [item["high"] for item in normalized_rows]
        lows = [item["low"] for item in normalized_rows]
        volumes = [item.get("volume") for item in normalized_rows]
        ts_list = [item.get("ts") or "" for item in normalized_rows]

        ta_values, indicator_backend, ta_warnings = self._compute_indicator_backend(
            closes=closes,
            highs=highs,
            lows=lows,
        )
        warnings.extend(ta_warnings)

        ma5 = self._first_not_none(ta_values.get("ma_5"), self._sma(closes, 5))
        ma10 = self._first_not_none(ta_values.get("ma_10"), self._sma(closes, 10))
        ma20 = self._first_not_none(ta_values.get("ma_20"), self._sma(closes, 20))
        ma60 = self._first_not_none(ta_values.get("ma_60"), self._sma(closes, 60))

        fallback_macd_series = self._macd_series(closes)
        macd_series = self._as_float_list(
            ta_values.get("macd_series"),
            fallback_macd_series[0],
        )
        macd_signal_series = self._as_float_list(
            ta_values.get("macd_signal_series"),
            fallback_macd_series[1],
        )
        macd_hist_series = self._as_float_list(
            ta_values.get("macd_hist_series"),
            fallback_macd_series[2],
        )

        macd_line = self._first_not_none(
            ta_values.get("macd"),
            macd_series[-1] if macd_series else None,
        )
        macd_signal = self._first_not_none(
            ta_values.get("macd_signal"),
            macd_signal_series[-1] if macd_signal_series else None,
        )
        macd_hist = self._first_not_none(
            ta_values.get("macd_hist"),
            macd_hist_series[-1] if macd_hist_series else None,
        )

        boll_low_fallback, boll_up_fallback = self._bollinger_band(closes, 20, 2.0)
        boll_mid = self._first_not_none(
            ta_values.get("boll_mid"), self._sma(closes, 20)
        )
        boll_up = self._first_not_none(ta_values.get("boll_up"), boll_up_fallback)
        boll_low = self._first_not_none(ta_values.get("boll_low"), boll_low_fallback)

        rsi_series = self._as_float_list(
            ta_values.get("rsi_series"), self._rsi_series(closes, 14)
        )
        rsi = self._first_not_none(
            ta_values.get("rsi_14"),
            rsi_series[-1] if rsi_series else self._rsi(closes, 14),
        )

        k_series_fallback, d_series_fallback = self._stoch_series(
            closes, highs, lows, period=9
        )
        k_series = self._as_float_list(
            ta_values.get("stoch_k_series"), k_series_fallback
        )
        d_series = self._as_float_list(
            ta_values.get("stoch_d_series"), d_series_fallback
        )
        stoch_k = self._first_not_none(
            ta_values.get("stoch_k"),
            k_series[-1] if k_series else None,
        )
        stoch_d = self._first_not_none(
            ta_values.get("stoch_d"),
            d_series[-1] if d_series else None,
        )
        kdj_j_series = self._compute_kdj_j_series(k_series, d_series)
        kdj_j = kdj_j_series[-1] if kdj_j_series else None

        atr = self._first_not_none(
            ta_values.get("atr_14"), self._atr(highs, lows, closes, 14)
        )
        volatility = self._volatility(closes, 20)
        max_drawdown = self._max_drawdown(closes)

        close = closes[-1] if closes else None
        prev_close = closes[-2] if len(closes) >= 2 else None

        ma_state = self._ma_state(ma5, ma10, ma20, ma60)
        macd_cross = self._macd_cross(macd_series, macd_signal_series)
        boll_status = self._bollinger_status(close, boll_up, boll_low, boll_mid)

        rsi_status = self._rsi_status(rsi)
        kdj_status = self._kdj_status(stoch_k, stoch_d, kdj_j)

        rsi_divergence = self._detect_divergence_pair(
            closes=closes,
            oscillator=rsi_series,
            oscillator_name="rsi",
        )
        kdj_divergence = self._detect_divergence_pair(
            closes=closes,
            oscillator=kdj_j_series,
            oscillator_name="kdj",
        )
        divergence = (
            rsi_divergence
            if rsi_divergence.get("status") == "detected"
            else kdj_divergence
        )

        sr = self._support_resistance(closes=closes, highs=highs, lows=lows)

        volume_ratio = self._volume_ratio(volumes)
        avg_volume_20 = self._volume_average(volumes, 20)
        shrink_pullback = self._is_shrink_pullback(
            close=close,
            prev_close=prev_close,
            ma20=ma20,
            volume_ratio=volume_ratio,
        )
        resistance_1 = self._level_price(sr.get("resistances"), 0)
        volume_breakout = self._is_volume_breakout(
            closes=closes,
            highs=highs,
            volume_ratio=volume_ratio,
            resistance_level=resistance_1,
        )

        pattern_hits = self._detect_patterns(normalized_rows)

        as_of = (
            ts_list[-1]
            if ts_list
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        signals = self._build_signal_timeline(
            timeframe=timeframe,
            as_of=as_of,
            ma_state=ma_state,
            macd_cross=macd_cross,
            boll_status=boll_status,
            rsi_status=rsi_status,
            kdj_status=kdj_status,
            divergence=divergence,
            volume_breakout=volume_breakout,
            shrink_pullback=shrink_pullback,
            pattern_hits=pattern_hits,
        )

        trend = {
            "ma": {
                "ma_5": ma5,
                "ma_10": ma10,
                "ma_20": ma20,
                "ma_60": ma60,
                "state": ma_state,
            },
            "macd": {
                "macd": macd_line,
                "signal": macd_signal,
                "hist": macd_hist,
                "cross": macd_cross,
            },
            "bollinger": {
                "upper": boll_up,
                "middle": boll_mid,
                "lower": boll_low,
                "status": boll_status,
            },
        }
        momentum = {
            "rsi": {
                "value": rsi,
                "status": rsi_status,
            },
            "kdj": {
                "k": stoch_k,
                "d": stoch_d,
                "j": kdj_j,
                "status": kdj_status,
            },
            "divergence": divergence,
        }
        volume_price = {
            "volume_ratio": volume_ratio,
            "avg_volume_20": avg_volume_20,
            "shrink_pullback": shrink_pullback,
            "volume_breakout": volume_breakout,
            "volatility_20": volatility,
            "max_drawdown": max_drawdown,
            "atr_14": atr,
        }
        patterns = {
            "hammer": [item for item in pattern_hits if item.get("type") == "hammer"],
            "engulfing": [
                item for item in pattern_hits if item.get("type") == "engulfing"
            ],
            "doji": [item for item in pattern_hits if item.get("type") == "doji"],
            "recent": pattern_hits[:8],
        }

        values = {
            "close": close,
            "rsi_14": rsi,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "ma_5": ma5,
            "ma_20": ma20,
            "ma_60": ma60,
            "atr_14": atr,
            "volatility_20": volatility,
            "max_drawdown": max_drawdown,
            "volume_ratio": volume_ratio,
            "support_1": self._level_price(sr.get("supports"), 0),
            "resistance_1": resistance_1,
        }

        return {
            "as_of": as_of,
            "indicator_backend": indicator_backend,
            "values": values,
            "trend": trend,
            "momentum": momentum,
            "volume_price": volume_price,
            "patterns": patterns,
            "support_resistance": sr,
            "signal_timeline": signals,
            "warnings": warnings,
        }

    @staticmethod
    def _ordered_timeframes(raw: List[str]) -> List[str]:
        if not raw:
            return []
        preferred = ["1d", "5m", "1m"]
        seen: List[str] = []
        for timeframe in preferred + raw:
            tf = str(timeframe)
            if tf in raw and tf not in seen:
                seen.append(tf)
        return seen

    @staticmethod
    def _normalize_price_payload(price_df: Any) -> Dict[str, List[Dict[str, Any]]]:
        if isinstance(price_df, dict):
            result: Dict[str, List[Dict[str, Any]]] = {}
            for key, value in price_df.items():
                if not isinstance(value, list):
                    continue
                rows = [item for item in value if isinstance(item, dict)]
                if rows:
                    result[str(key)] = rows
            return result
        if isinstance(price_df, list):
            rows = [item for item in price_df if isinstance(item, dict)]
            if rows:
                return {"1d": rows}
        return {}

    @staticmethod
    def _normalize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            open_v = _safe_float(row.get("open"))
            high_v = _safe_float(row.get("high"))
            low_v = _safe_float(row.get("low"))
            close_v = _safe_float(row.get("close"))
            volume_v = _safe_float(row.get("volume"))
            if open_v is None or high_v is None or low_v is None or close_v is None:
                continue
            normalized.append(
                {
                    "ts": str(row.get("ts") or ""),
                    "open": open_v,
                    "high": high_v,
                    "low": low_v,
                    "close": close_v,
                    "volume": volume_v,
                }
            )
        return normalized

    def _compute_indicator_backend(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Tuple[Dict[str, Any], str, List[str]]:
        warnings: List[str] = []

        talib_values, talib_warnings = self._compute_with_talib(closes, highs, lows)
        warnings.extend(talib_warnings)
        if talib_values:
            return talib_values, "ta-lib", warnings

        pandas_values, pandas_warnings = self._compute_with_pandas_ta(
            closes=closes,
            highs=highs,
            lows=lows,
        )
        warnings.extend(pandas_warnings)
        if pandas_values:
            return pandas_values, "pandas-ta", warnings

        warnings.append("indicator_backend_builtin_fallback")
        return {}, "builtin", warnings

    def _compute_with_talib(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Tuple[Dict[str, Any], List[str]]:
        warnings: List[str] = []
        try:
            import numpy as np
            import talib
        except Exception:
            return {}, ["talib_unavailable_fallback"]

        if not closes:
            return {}, warnings

        output: Dict[str, Any] = {}
        try:
            close_arr = np.asarray(closes, dtype="float64")
            high_arr = np.asarray(highs, dtype="float64")
            low_arr = np.asarray(lows, dtype="float64")

            output["ma_5"] = self._tail_finite(talib.SMA(close_arr, timeperiod=5))
            output["ma_10"] = self._tail_finite(talib.SMA(close_arr, timeperiod=10))
            output["ma_20"] = self._tail_finite(talib.SMA(close_arr, timeperiod=20))
            output["ma_60"] = self._tail_finite(talib.SMA(close_arr, timeperiod=60))

            macd_line, macd_signal, macd_hist = talib.MACD(
                close_arr,
                fastperiod=12,
                slowperiod=26,
                signalperiod=9,
            )
            macd_series = self._to_finite_series(macd_line)
            signal_series = self._to_finite_series(macd_signal)
            hist_series = self._to_finite_series(macd_hist)
            if macd_series:
                output["macd_series"] = macd_series
                output["macd"] = macd_series[-1]
            if signal_series:
                output["macd_signal_series"] = signal_series
                output["macd_signal"] = signal_series[-1]
            if hist_series:
                output["macd_hist_series"] = hist_series
                output["macd_hist"] = hist_series[-1]

            upper, middle, lower = talib.BBANDS(
                close_arr,
                timeperiod=20,
                nbdevup=2.0,
                nbdevdn=2.0,
                matype=0,
            )
            output["boll_up"] = self._tail_finite(upper)
            output["boll_mid"] = self._tail_finite(middle)
            output["boll_low"] = self._tail_finite(lower)

            rsi_values = self._to_finite_series(talib.RSI(close_arr, timeperiod=14))
            if rsi_values:
                output["rsi_series"] = rsi_values
                output["rsi_14"] = rsi_values[-1]

            stoch_k, stoch_d = talib.STOCH(
                high_arr,
                low_arr,
                close_arr,
                fastk_period=9,
                slowk_period=3,
                slowk_matype=0,
                slowd_period=3,
                slowd_matype=0,
            )
            k_values = self._to_finite_series(stoch_k)
            d_values = self._to_finite_series(stoch_d)
            if k_values:
                output["stoch_k_series"] = k_values
                output["stoch_k"] = k_values[-1]
            if d_values:
                output["stoch_d_series"] = d_values
                output["stoch_d"] = d_values[-1]

            output["atr_14"] = self._tail_finite(
                talib.ATR(high_arr, low_arr, close_arr, timeperiod=14)
            )
        except Exception as exc:
            warnings.append(f"talib_compute_failed:{exc}")
        return output, warnings

    def _compute_with_pandas_ta(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Tuple[Dict[str, Any], List[str]]:
        warnings: List[str] = []
        try:
            import pandas as pd
            import pandas_ta as ta
        except Exception:
            return {}, ["pandas_ta_unavailable_fallback"]

        if not closes:
            return {}, warnings

        series_close = pd.Series(closes, dtype="float64")
        series_high = pd.Series(highs, dtype="float64")
        series_low = pd.Series(lows, dtype="float64")

        output: Dict[str, Any] = {}
        try:
            output["ma_5"] = _safe_float(ta.sma(series_close, length=5).iloc[-1])
            output["ma_10"] = _safe_float(ta.sma(series_close, length=10).iloc[-1])
            output["ma_20"] = _safe_float(ta.sma(series_close, length=20).iloc[-1])
            output["ma_60"] = _safe_float(ta.sma(series_close, length=60).iloc[-1])

            macd_df = ta.macd(series_close, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                macd_col = next(
                    (col for col in macd_df.columns if col.startswith("MACD_")),
                    "",
                )
                signal_col = next(
                    (col for col in macd_df.columns if col.startswith("MACDs_")),
                    "",
                )
                hist_col = next(
                    (col for col in macd_df.columns if col.startswith("MACDh_")),
                    "",
                )
                if macd_col and signal_col and hist_col:
                    macd_series = [
                        float(item) for item in macd_df[macd_col].dropna().tolist()
                    ]
                    signal_series = [
                        float(item) for item in macd_df[signal_col].dropna().tolist()
                    ]
                    hist_series = [
                        float(item) for item in macd_df[hist_col].dropna().tolist()
                    ]
                    output["macd_series"] = macd_series
                    output["macd_signal_series"] = signal_series
                    output["macd_hist_series"] = hist_series
                    output["macd"] = macd_series[-1] if macd_series else None
                    output["macd_signal"] = signal_series[-1] if signal_series else None
                    output["macd_hist"] = hist_series[-1] if hist_series else None

            bb_df = ta.bbands(series_close, length=20, std=2.0)
            if bb_df is not None and not bb_df.empty:
                low_col = next(
                    (col for col in bb_df.columns if col.startswith("BBL_")),
                    "",
                )
                mid_col = next(
                    (col for col in bb_df.columns if col.startswith("BBM_")),
                    "",
                )
                up_col = next(
                    (col for col in bb_df.columns if col.startswith("BBU_")),
                    "",
                )
                if low_col and mid_col and up_col:
                    output["boll_low"] = _safe_float(bb_df[low_col].iloc[-1])
                    output["boll_mid"] = _safe_float(bb_df[mid_col].iloc[-1])
                    output["boll_up"] = _safe_float(bb_df[up_col].iloc[-1])

            rsi_series = ta.rsi(series_close, length=14)
            if rsi_series is not None and not rsi_series.empty:
                rsi_values = [float(item) for item in rsi_series.dropna().tolist()]
                output["rsi_series"] = rsi_values
                output["rsi_14"] = rsi_values[-1] if rsi_values else None

            stoch_df = ta.stoch(
                series_high, series_low, series_close, k=9, d=3, smooth_k=3
            )
            if stoch_df is not None and not stoch_df.empty:
                k_col = next(
                    (col for col in stoch_df.columns if col.startswith("STOCHk_")),
                    "",
                )
                d_col = next(
                    (col for col in stoch_df.columns if col.startswith("STOCHd_")),
                    "",
                )
                if k_col and d_col:
                    k_values = [
                        float(item) for item in stoch_df[k_col].dropna().tolist()
                    ]
                    d_values = [
                        float(item) for item in stoch_df[d_col].dropna().tolist()
                    ]
                    output["stoch_k_series"] = k_values
                    output["stoch_d_series"] = d_values
                    output["stoch_k"] = k_values[-1] if k_values else None
                    output["stoch_d"] = d_values[-1] if d_values else None

            atr_series = ta.atr(series_high, series_low, series_close, length=14)
            if atr_series is not None and not atr_series.empty:
                output["atr_14"] = _safe_float(atr_series.iloc[-1])
        except Exception as exc:
            warnings.append(f"pandas_ta_compute_failed:{exc}")
        return output, warnings

    @staticmethod
    def _resolve_backend(primary: Dict[str, Any], candidates: Sequence[str]) -> str:
        value = str(primary.get("indicator_backend") or "").strip()
        if value:
            return value
        for item in candidates:
            current = str(item or "").strip()
            if current:
                return current
        return "builtin"

    @staticmethod
    def _to_finite_series(values: Any) -> List[float]:
        if values is None:
            return []
        raw_values = values.tolist() if hasattr(values, "tolist") else values
        if not isinstance(raw_values, list):
            return []
        output: List[float] = []
        for item in raw_values:
            number = _safe_float(item)
            if number is None or not math.isfinite(number):
                continue
            output.append(number)
        return output

    @classmethod
    def _tail_finite(cls, values: Any) -> Optional[float]:
        series = cls._to_finite_series(values)
        return series[-1] if series else None

    @staticmethod
    def _first_not_none(*values: Optional[float]) -> Optional[float]:
        for value in values:
            if value is not None:
                return value
        return None

    @staticmethod
    def _as_float_list(*candidates: Any) -> List[float]:
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            values: List[float] = []
            for item in candidate:
                number = _safe_float(item)
                if number is not None:
                    values.append(number)
            if values:
                return values
        return []

    @staticmethod
    def _merge_category(
        timeframe_results: Dict[str, Dict[str, Any]],
        category: str,
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for timeframe, payload in timeframe_results.items():
            row = payload.get(category)
            if isinstance(row, dict):
                merged[timeframe] = row
        if "1d" in merged:
            merged["primary"] = merged["1d"]
        elif merged:
            merged["primary"] = merged[next(iter(merged))]
        return merged

    @staticmethod
    def _ma_state(
        ma5: Optional[float],
        ma10: Optional[float],
        ma20: Optional[float],
        ma60: Optional[float],
    ) -> str:
        if None in (ma5, ma10, ma20, ma60):
            return "mixed"
        if ma5 > ma10 > ma20 > ma60:
            return "bullish"
        if ma5 < ma10 < ma20 < ma60:
            return "bearish"
        return "mixed"

    @staticmethod
    def _macd_cross(macd_series: List[float], signal_series: List[float]) -> str:
        if len(macd_series) < 2 or len(signal_series) < 2:
            return "none"
        prev_diff = macd_series[-2] - signal_series[-2]
        curr_diff = macd_series[-1] - signal_series[-1]
        if prev_diff <= 0 < curr_diff:
            return "golden_cross"
        if prev_diff >= 0 > curr_diff:
            return "dead_cross"
        return "none"

    @staticmethod
    def _bollinger_status(
        close: Optional[float],
        upper: Optional[float],
        lower: Optional[float],
        middle: Optional[float],
    ) -> str:
        if close is None or upper is None or lower is None:
            return "unknown"
        if close > upper:
            return "breakout_up"
        if close < lower:
            return "breakout_down"
        if middle is not None and abs(close - middle) / max(abs(middle), 1e-9) <= 0.01:
            return "revert_mid"
        if middle is not None and close > middle:
            return "above_mid"
        return "inside_band"

    @staticmethod
    def _rsi_status(rsi: Optional[float]) -> str:
        if rsi is None:
            return "unknown"
        if rsi >= 70:
            return "overbought"
        if rsi <= 30:
            return "oversold"
        return "neutral"

    @staticmethod
    def _kdj_status(k: Optional[float], d: Optional[float], j: Optional[float]) -> str:
        if k is None or d is None:
            return "unknown"
        if k >= 80 and d >= 80:
            return "high_blunting"
        if k <= 20 and d <= 20:
            return "low_blunting"
        if j is not None and j > 100:
            return "extreme_up"
        if j is not None and j < 0:
            return "extreme_down"
        return "neutral"

    def _detect_divergence_pair(
        self,
        closes: List[float],
        oscillator: List[float],
        oscillator_name: str,
    ) -> Dict[str, Any]:
        if len(closes) < 20 or len(oscillator) < 20:
            return {"status": "none", "type": "none", "oscillator": oscillator_name}

        price_high_idx = self._last_two_pivots(closes, mode="high")
        price_low_idx = self._last_two_pivots(closes, mode="low")
        osc_high_idx = self._last_two_pivots(oscillator, mode="high")
        osc_low_idx = self._last_two_pivots(oscillator, mode="low")

        if price_high_idx and osc_high_idx:
            p1, p2 = price_high_idx
            o1, o2 = osc_high_idx
            if closes[p2] > closes[p1] and oscillator[o2] < oscillator[o1]:
                return {
                    "status": "detected",
                    "type": "bearish",
                    "oscillator": oscillator_name,
                    "price_points": [closes[p1], closes[p2]],
                    "osc_points": [oscillator[o1], oscillator[o2]],
                }

        if price_low_idx and osc_low_idx:
            p1, p2 = price_low_idx
            o1, o2 = osc_low_idx
            if closes[p2] < closes[p1] and oscillator[o2] > oscillator[o1]:
                return {
                    "status": "detected",
                    "type": "bullish",
                    "oscillator": oscillator_name,
                    "price_points": [closes[p1], closes[p2]],
                    "osc_points": [oscillator[o1], oscillator[o2]],
                }

        return {"status": "none", "type": "none", "oscillator": oscillator_name}

    @staticmethod
    def _volume_ratio(
        volumes: List[Optional[float]], window: int = 20
    ) -> Optional[float]:
        clean = [item for item in volumes if item is not None]
        if len(clean) < 2:
            return None
        base = clean[-window:] if len(clean) >= window else clean
        avg = sum(base) / len(base)
        if avg == 0:
            return None
        return clean[-1] / avg

    @staticmethod
    def _volume_average(
        volumes: List[Optional[float]], window: int = 20
    ) -> Optional[float]:
        clean = [item for item in volumes if item is not None]
        if not clean:
            return None
        base = clean[-window:] if len(clean) >= window else clean
        return sum(base) / len(base)

    @staticmethod
    def _is_shrink_pullback(
        close: Optional[float],
        prev_close: Optional[float],
        ma20: Optional[float],
        volume_ratio: Optional[float],
    ) -> bool:
        if close is None or prev_close is None or ma20 is None or volume_ratio is None:
            return False
        if ma20 == 0:
            return False
        near_ma = abs(close - ma20) / abs(ma20) <= 0.025
        return close < prev_close and near_ma and volume_ratio < 0.85

    @staticmethod
    def _is_volume_breakout(
        closes: List[float],
        highs: List[float],
        volume_ratio: Optional[float],
        resistance_level: Optional[float],
    ) -> bool:
        if len(closes) < 21 or len(highs) < 21 or volume_ratio is None:
            return False
        recent_resistance = max(highs[-21:-1])
        threshold = (
            resistance_level if resistance_level is not None else recent_resistance
        )
        return closes[-1] > threshold and volume_ratio > 1.5

    def _detect_patterns(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        start = max(1, len(rows) - 40)
        for idx in range(start, len(rows)):
            row = rows[idx]
            ts = str(row.get("ts") or "")
            open_v = row["open"]
            high_v = row["high"]
            low_v = row["low"]
            close_v = row["close"]
            body = abs(close_v - open_v)
            full_range = max(high_v - low_v, 1e-9)
            upper_shadow = high_v - max(open_v, close_v)
            lower_shadow = min(open_v, close_v) - low_v

            if (
                lower_shadow >= body * 2
                and upper_shadow <= body * 0.7
                and body / full_range <= 0.45
            ):
                hits.append({"ts": ts, "type": "hammer", "direction": "bullish"})

            if body / full_range <= 0.08:
                hits.append({"ts": ts, "type": "doji", "direction": "neutral"})

            if idx > 0:
                prev = rows[idx - 1]
                prev_open = prev["open"]
                prev_close = prev["close"]
                bullish_engulfing = (
                    prev_close < prev_open
                    and close_v > open_v
                    and close_v >= prev_open
                    and open_v <= prev_close
                )
                bearish_engulfing = (
                    prev_close > prev_open
                    and close_v < open_v
                    and open_v >= prev_close
                    and close_v <= prev_open
                )
                if bullish_engulfing:
                    hits.append({"ts": ts, "type": "engulfing", "direction": "bullish"})
                if bearish_engulfing:
                    hits.append({"ts": ts, "type": "engulfing", "direction": "bearish"})

        hits.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
        return hits

    def _support_resistance(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Dict[str, Any]:
        if not closes:
            return {
                "supports": [],
                "resistances": [],
                "pivot_meta": {
                    "method": "swing_cluster",
                    "touch_counts": {},
                },
            }

        current = closes[-1]
        high_levels = self._pivot_levels(highs, mode="high")
        low_levels = self._pivot_levels(lows, mode="low")

        supports = [
            level
            for level in self._cluster_levels(low_levels, current)
            if level["price"] < current
        ]
        resistances = [
            level
            for level in self._cluster_levels(high_levels, current)
            if level["price"] > current
        ]

        supports = sorted(supports, key=lambda row: row["price"], reverse=True)[:3]
        resistances = sorted(resistances, key=lambda row: row["price"])[:3]

        support_levels: List[Dict[str, Any]] = []
        resistance_levels: List[Dict[str, Any]] = []
        touch_counts: Dict[str, int] = {}

        for idx, item in enumerate(supports):
            label = f"S{idx + 1}"
            row = {
                "level": label,
                "price": item["price"],
                "touches": item["touches"],
            }
            support_levels.append(row)
            touch_counts[label] = item["touches"]

        for idx, item in enumerate(resistances):
            label = f"R{idx + 1}"
            row = {
                "level": label,
                "price": item["price"],
                "touches": item["touches"],
            }
            resistance_levels.append(row)
            touch_counts[label] = item["touches"]

        return {
            "supports": support_levels,
            "resistances": resistance_levels,
            "pivot_meta": {
                "method": "swing_cluster",
                "touch_counts": touch_counts,
                "current_price": current,
            },
        }

    @staticmethod
    def _pivot_levels(values: List[float], mode: str) -> List[float]:
        levels: List[float] = []
        for idx in range(2, len(values) - 2):
            center = values[idx]
            window = values[idx - 2 : idx + 3]
            if mode == "high" and center >= max(window):
                levels.append(center)
            if mode == "low" and center <= min(window):
                levels.append(center)
        return levels

    @staticmethod
    def _cluster_levels(levels: List[float], anchor: float) -> List[Dict[str, Any]]:
        if not levels:
            return []
        tolerance = max(anchor * 0.005, 1e-6)
        sorted_levels = sorted(levels)
        clusters: List[List[float]] = [[sorted_levels[0]]]
        for value in sorted_levels[1:]:
            if abs(value - clusters[-1][-1]) <= tolerance:
                clusters[-1].append(value)
            else:
                clusters.append([value])
        result = []
        for cluster in clusters:
            result.append(
                {
                    "price": sum(cluster) / len(cluster),
                    "touches": len(cluster),
                }
            )
        return result

    def _build_strategy(
        self,
        timeframe_results: Dict[str, Dict[str, Any]],
        profile: str,
        primary_timeframe: str,
    ) -> Dict[str, Any]:
        primary = timeframe_results.get(primary_timeframe, {})
        trend = primary.get("trend", {}) if isinstance(primary, dict) else {}
        momentum = primary.get("momentum", {}) if isinstance(primary, dict) else {}
        volume_price = (
            primary.get("volume_price", {}) if isinstance(primary, dict) else {}
        )
        patterns = primary.get("patterns", {}) if isinstance(primary, dict) else {}
        sr = primary.get("support_resistance", {}) if isinstance(primary, dict) else {}

        trend_score = self._trend_score(trend)
        momentum_score = self._momentum_score(momentum)
        volume_score = self._volume_score(volume_price)
        pattern_score = self._pattern_score(patterns)
        sr_score = self._sr_score(sr, primary)

        weights = {
            "balanced": {
                "trend": 0.30,
                "momentum": 0.25,
                "volume": 0.25,
                "patterns": 0.10,
                "sr": 0.10,
            },
            "trend": {
                "trend": 0.45,
                "momentum": 0.20,
                "volume": 0.20,
                "patterns": 0.05,
                "sr": 0.10,
            },
            "momentum": {
                "trend": 0.20,
                "momentum": 0.40,
                "volume": 0.20,
                "patterns": 0.10,
                "sr": 0.10,
            },
        }.get(
            profile,
            {
                "trend": 0.30,
                "momentum": 0.25,
                "volume": 0.25,
                "patterns": 0.10,
                "sr": 0.10,
            },
        )

        score = (
            trend_score * weights["trend"]
            + momentum_score * weights["momentum"]
            + volume_score * weights["volume"]
            + pattern_score * weights["patterns"]
            + sr_score * weights["sr"]
        )
        score = max(0.0, min(100.0, score))

        if score >= 65:
            stance = "bullish"
            position_size = int(max(55, min(100, score)))
        elif score <= 35:
            stance = "bearish"
            position_size = int(max(0, min(30, score * 0.8)))
        else:
            stance = "neutral"
            position_size = int(35 + ((score - 35) / 30) * 20)

        values = primary.get("values") if isinstance(primary, dict) else {}
        close = _safe_float((values or {}).get("close"))
        atr = _safe_float((values or {}).get("atr_14"))
        supports = sr.get("supports") if isinstance(sr, dict) else []
        resistances = sr.get("resistances") if isinstance(sr, dict) else []

        support_1 = self._level_price(supports, 0)
        support_2 = self._level_price(supports, 1)
        resistance_1 = self._level_price(resistances, 0)

        entry_zone = self._entry_zone(support_1, close)
        if support_2 is not None:
            stop_loss = support_2 * 0.99
        elif close is not None and atr is not None:
            stop_loss = close - atr * 2.0
        elif close is not None:
            stop_loss = close * 0.97
        else:
            stop_loss = None

        if resistance_1 is not None:
            take_profit = resistance_1
        elif close is not None and atr is not None:
            take_profit = close + atr * 2.5
        elif close is not None:
            take_profit = close * 1.06
        else:
            take_profit = None

        return {
            "score": round(score, 2),
            "stance": stance,
            "position_size": position_size,
            "entry_zone": entry_zone,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_controls": {
                "entry_zone": entry_zone,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
            "component_scores": {
                "trend": round(trend_score, 2),
                "momentum": round(momentum_score, 2),
                "volume_price": round(volume_score, 2),
                "patterns": round(pattern_score, 2),
                "support_resistance": round(sr_score, 2),
            },
            "profile": profile,
        }

    @staticmethod
    def _level_price(levels: Any, index: int) -> Optional[float]:
        if not isinstance(levels, list) or len(levels) <= index:
            return None
        row = levels[index]
        if not isinstance(row, dict):
            return None
        return _safe_float(row.get("price"))

    @staticmethod
    def _entry_zone(
        support: Optional[float],
        fallback: Optional[float],
    ) -> Dict[str, Optional[float]]:
        base = support if support is not None else fallback
        if base is None:
            return {"low": None, "high": None}
        return {
            "low": base * 0.995,
            "high": base * 1.005,
        }

    @staticmethod
    def _trend_score(trend: Dict[str, Any]) -> float:
        score = 50.0
        ma_state = (
            (trend.get("ma") or {}).get("state") if isinstance(trend, dict) else ""
        ) or ""
        macd_cross = (
            (trend.get("macd") or {}).get("cross") if isinstance(trend, dict) else ""
        ) or ""
        boll = (
            (trend.get("bollinger") or {}).get("status")
            if isinstance(trend, dict)
            else ""
        ) or ""

        if ma_state == "bullish":
            score += 20
        elif ma_state == "bearish":
            score -= 20

        if macd_cross == "golden_cross":
            score += 15
        elif macd_cross == "dead_cross":
            score -= 15

        if boll == "breakout_up":
            score += 10
        elif boll == "breakout_down":
            score -= 10
        elif boll == "revert_mid":
            score += 5

        return max(0.0, min(100.0, score))

    @staticmethod
    def _momentum_score(momentum: Dict[str, Any]) -> float:
        score = 50.0
        rsi_status = (
            (momentum.get("rsi") or {}).get("status")
            if isinstance(momentum, dict)
            else ""
        ) or ""
        kdj_status = (
            (momentum.get("kdj") or {}).get("status")
            if isinstance(momentum, dict)
            else ""
        ) or ""
        divergence_type = (
            (momentum.get("divergence") or {}).get("type")
            if isinstance(momentum, dict)
            else ""
        ) or ""

        if rsi_status == "oversold":
            score += 15
        elif rsi_status == "overbought":
            score -= 15

        if kdj_status == "low_blunting":
            score += 10
        elif kdj_status == "high_blunting":
            score -= 10

        if divergence_type == "bullish":
            score += 15
        elif divergence_type == "bearish":
            score -= 15

        return max(0.0, min(100.0, score))

    @staticmethod
    def _volume_score(volume_price: Dict[str, Any]) -> float:
        score = 50.0
        ratio = (
            _safe_float(volume_price.get("volume_ratio"))
            if isinstance(volume_price, dict)
            else None
        )
        if volume_price.get("volume_breakout"):
            score += 20
        if volume_price.get("shrink_pullback"):
            score += 10
        if ratio is not None:
            if ratio > 1.8:
                score += 10
            elif ratio > 1.2:
                score += 5
            elif ratio < 0.6:
                score -= 8
        return max(0.0, min(100.0, score))

    @staticmethod
    def _pattern_score(patterns: Dict[str, Any]) -> float:
        score = 50.0
        recent = patterns.get("recent") if isinstance(patterns, dict) else []
        if isinstance(recent, list):
            for row in recent[:5]:
                if not isinstance(row, dict):
                    continue
                direction = str(row.get("direction") or "")
                if direction == "bullish":
                    score += 4
                elif direction == "bearish":
                    score -= 4
        return max(0.0, min(100.0, score))

    @staticmethod
    def _sr_score(sr: Dict[str, Any], primary: Dict[str, Any]) -> float:
        score = 50.0
        values = primary.get("values") if isinstance(primary, dict) else {}
        close = _safe_float((values or {}).get("close"))
        if close is None:
            return score

        supports = sr.get("supports") if isinstance(sr, dict) else []
        resistances = sr.get("resistances") if isinstance(sr, dict) else []
        if isinstance(supports, list) and supports:
            s1 = _safe_float(
                supports[0].get("price") if isinstance(supports[0], dict) else None
            )
            if s1 and s1 != 0 and abs(close - s1) / s1 <= 0.01:
                score += 10

        if isinstance(resistances, list) and resistances:
            r1 = _safe_float(
                resistances[0].get("price")
                if isinstance(resistances[0], dict)
                else None
            )
            if r1 and r1 != 0 and abs(close - r1) / r1 <= 0.01:
                score -= 10

        return max(0.0, min(100.0, score))

    @staticmethod
    def _build_signal_timeline(
        timeframe: str,
        as_of: str,
        ma_state: str,
        macd_cross: str,
        boll_status: str,
        rsi_status: str,
        kdj_status: str,
        divergence: Dict[str, Any],
        volume_breakout: bool,
        shrink_pullback: bool,
        pattern_hits: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        timeline: List[Dict[str, Any]] = []

        def add(
            signal: str, direction: str, strength: str, ts: Optional[str] = None
        ) -> None:
            event_ts = ts or as_of
            timeline.append(
                {
                    "ts": event_ts,
                    "timeframe": timeframe,
                    "signal": signal,
                    "direction": direction,
                    "strength": strength,
                    "evidence": f"{timeframe} {signal} {direction}",
                }
            )

        if ma_state in {"bullish", "bearish"}:
            add("ma_alignment", ma_state, "medium")
        if macd_cross != "none":
            add(
                "macd_cross",
                "bullish" if macd_cross == "golden_cross" else "bearish",
                "high",
            )
        if boll_status in {"breakout_up", "breakout_down", "revert_mid"}:
            direction = "neutral"
            if boll_status == "breakout_up":
                direction = "bullish"
            elif boll_status == "breakout_down":
                direction = "bearish"
            add("bollinger_signal", direction, "medium")

        if rsi_status in {"overbought", "oversold"}:
            add(
                "rsi_extreme",
                "bearish" if rsi_status == "overbought" else "bullish",
                "medium",
            )

        if kdj_status in {"high_blunting", "low_blunting"}:
            add(
                "kdj_blunting",
                "bearish" if kdj_status == "high_blunting" else "bullish",
                "medium",
            )

        if divergence.get("status") == "detected":
            add(
                "divergence",
                str(divergence.get("type") or "neutral"),
                "high",
            )

        if volume_breakout:
            add("volume_breakout", "bullish", "high")
        if shrink_pullback:
            add("shrink_pullback", "bullish", "medium")

        for row in pattern_hits[:3]:
            signal_type = str(row.get("type") or "pattern")
            direction = str(row.get("direction") or "neutral")
            add(
                signal=f"pattern_{signal_type}",
                direction=direction,
                strength="medium",
                ts=str(row.get("ts") or as_of),
            )

        return timeline

    @staticmethod
    def _last_two_pivots(values: List[float], mode: str) -> Optional[Tuple[int, int]]:
        pivots: List[int] = []
        for idx in range(2, len(values) - 2):
            center = values[idx]
            window = values[idx - 2 : idx + 3]
            if mode == "high" and center >= max(window):
                pivots.append(idx)
            if mode == "low" and center <= min(window):
                pivots.append(idx)
        if len(pivots) < 2:
            return None
        return pivots[-2], pivots[-1]

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period or period <= 0:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _ema(values: List[float], period: int) -> Optional[float]:
        if len(values) < period or period <= 0:
            return None
        multiplier = 2 / (period + 1)
        ema_value = sum(values[:period]) / period
        for value in values[period:]:
            ema_value = (value - ema_value) * multiplier + ema_value
        return ema_value

    def _macd_series(
        self, values: List[float]
    ) -> Tuple[List[float], List[float], List[float]]:
        if len(values) < 35:
            return [], [], []
        macd_series: List[float] = []
        for idx in range(26, len(values)):
            short = self._ema(values[: idx + 1], 12)
            long = self._ema(values[: idx + 1], 26)
            if short is None or long is None:
                continue
            macd_series.append(short - long)
        signal_series: List[float] = []
        for idx in range(9, len(macd_series) + 1):
            ema_value = self._ema(macd_series[:idx], 9)
            if ema_value is not None:
                signal_series.append(ema_value)
        if len(signal_series) < len(macd_series):
            diff = len(macd_series) - len(signal_series)
            signal_series = (
                [signal_series[0]] * diff + signal_series
                if signal_series
                else [0.0] * len(macd_series)
            )
        hist_series = [m - s for m, s in zip(macd_series, signal_series)]
        return macd_series, signal_series, hist_series

    def _rsi(self, values: List[float], period: int) -> Optional[float]:
        series = self._rsi_series(values, period)
        return series[-1] if series else None

    @staticmethod
    def _rsi_series(values: List[float], period: int = 14) -> List[float]:
        if len(values) <= period:
            return []
        rsis: List[float] = []
        for cursor in range(period, len(values)):
            window = values[cursor - period : cursor + 1]
            gains: List[float] = []
            losses: List[float] = []
            for idx in range(1, len(window)):
                delta = window[idx] - window[idx - 1]
                gains.append(max(delta, 0.0))
                losses.append(abs(min(delta, 0.0)))
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                rsis.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsis.append(100 - (100 / (1 + rs)))
        return rsis

    def _stoch_series(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        period: int = 9,
    ) -> Tuple[List[float], List[float]]:
        if len(closes) < period:
            return [], []

        k_series: List[float] = []
        for idx in range(period - 1, len(closes)):
            h = max(highs[idx - period + 1 : idx + 1])
            l = min(lows[idx - period + 1 : idx + 1])
            if h == l:
                continue
            k_series.append((closes[idx] - l) / (h - l) * 100)

        d_series: List[float] = []
        for idx in range(2, len(k_series)):
            d_series.append(sum(k_series[idx - 2 : idx + 1]) / 3)

        if len(d_series) < len(k_series):
            if d_series:
                fill = [d_series[0]] * (len(k_series) - len(d_series))
                d_series = fill + d_series
            else:
                d_series = [50.0] * len(k_series)

        return k_series, d_series

    @staticmethod
    def _compute_kdj_j_series(
        k_series: List[float], d_series: List[float]
    ) -> List[float]:
        length = min(len(k_series), len(d_series))
        if length == 0:
            return []
        return [3 * k_series[idx] - 2 * d_series[idx] for idx in range(length)]

    @staticmethod
    def _atr(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int,
    ) -> Optional[float]:
        if (
            len(highs) < period + 1
            or len(lows) < period + 1
            or len(closes) < period + 1
        ):
            return None
        tr_values = []
        for idx in range(1, min(len(highs), len(lows), len(closes))):
            high = highs[idx]
            low = lows[idx]
            prev_close = closes[idx - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        if len(tr_values) < period:
            return None
        return sum(tr_values[-period:]) / period

    @staticmethod
    def _volatility(values: List[float], period: int) -> Optional[float]:
        if len(values) < period + 1:
            return None
        rets = []
        for idx in range(-period, 0):
            prev = values[idx - 1]
            curr = values[idx]
            if prev == 0:
                continue
            rets.append((curr - prev) / prev)
        if len(rets) < 2:
            return None
        return pstdev(rets)

    @staticmethod
    def _max_drawdown(values: List[float]) -> Optional[float]:
        if not values:
            return None
        peak = values[0]
        max_dd = 0.0
        for price in values:
            if price > peak:
                peak = price
            if peak == 0:
                continue
            drawdown = (peak - price) / peak
            if drawdown > max_dd:
                max_dd = drawdown
        return max_dd

    def _bollinger_band(
        self,
        values: List[float],
        period: int,
        std_factor: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        if len(values) < period:
            return None, None
        window = values[-period:]
        mean = sum(window) / period
        variance = sum((item - mean) ** 2 for item in window) / period
        std = math.sqrt(variance)
        return mean - std_factor * std, mean + std_factor * std
