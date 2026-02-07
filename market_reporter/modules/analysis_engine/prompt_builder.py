from __future__ import annotations

import json
from typing import Dict, List

from market_reporter.core.types import AnalysisInput


SYSTEM_PROMPT = (
    "You are a professional equity analyst. "
    "Always return exactly one valid JSON object with keys: "
    "summary, sentiment, key_levels, risks, action_items, confidence, markdown. "
    "Do not wrap output with markdown code fences."
)


def build_user_prompt(payload: AnalysisInput) -> str:
    quote = payload.quote.model_dump(mode="json") if payload.quote else {}
    kline_tail = [
        {
            "ts": item.ts,
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
            "volume": item.volume,
        }
        for item in payload.kline[-40:]
    ]
    curve_tail = [
        {
            "ts": item.ts,
            "price": item.price,
            "volume": item.volume,
        }
        for item in payload.curve[-60:]
    ]
    news_digest = [
        {
            "source": item.source,
            "category": item.category,
            "published": item.published,
            "title": item.title[:180],
        }
        for item in payload.news[:25]
    ]
    fund_flow: Dict[str, list] = {
        key: [point.model_dump(mode="json") for point in value[-8:]]
        for key, value in payload.fund_flow.items()
    }

    request_json = {
        "task": "基于输入数据给出可执行的交易分析结论。",
        "symbol": payload.symbol,
        "market": payload.market,
        "output_contract": {
            "summary": "一句话核心结论（中文）",
            "sentiment": "bullish|neutral|bearish",
            "key_levels": ["关键价位或条件"],
            "risks": ["主要风险"],
            "action_items": ["可执行动作"],
            "confidence": "0到1之间的小数",
            "markdown": "结构化中文说明（可分点）",
        },
        "analysis_rules": [
            "优先结合最新报价、K线和新闻事件。",
            "结论要给出条件和触发阈值，避免空泛判断。",
            "如果数据不足，明确指出并降低 confidence。",
            "只返回 JSON 对象，不要输出多余文本。",
        ],
        "data": {
            "quote": quote,
            "kline_summary": _summarize_kline(payload),
            "curve_summary": _summarize_curve(payload),
            "kline_tail": kline_tail,
            "curve_tail": curve_tail,
            "news_digest": news_digest,
            "fund_flow": fund_flow,
            "watch_meta": payload.watch_meta,
        },
    }
    return json.dumps(request_json, ensure_ascii=False)


def _summarize_kline(payload: AnalysisInput) -> Dict[str, object]:
    bars = payload.kline[-120:]
    if not bars:
        return {}
    first = bars[0]
    last = bars[-1]
    highs = [item.high for item in bars]
    lows = [item.low for item in bars]
    volumes = [item.volume for item in bars if item.volume is not None]
    change_pct = 0.0
    if first.close:
        change_pct = round(((last.close - first.close) / first.close) * 100, 4)
    return {
        "bars": len(bars),
        "interval": last.interval,
        "start_ts": first.ts,
        "end_ts": last.ts,
        "first_close": first.close,
        "last_close": last.close,
        "change_pct": change_pct,
        "high_max": max(highs),
        "low_min": min(lows),
        "avg_volume": round(sum(volumes) / len(volumes), 2) if volumes else None,
    }


def _summarize_curve(payload: AnalysisInput) -> Dict[str, object]:
    points = payload.curve[-180:]
    if not points:
        return {}
    first = points[0]
    last = points[-1]
    prices: List[float] = [item.price for item in points]
    change_pct = 0.0
    if first.price:
        change_pct = round(((last.price - first.price) / first.price) * 100, 4)
    return {
        "points": len(points),
        "start_ts": first.ts,
        "end_ts": last.ts,
        "first_price": first.price,
        "last_price": last.price,
        "change_pct": change_pct,
        "price_high": max(prices),
        "price_low": min(prices),
    }
