from __future__ import annotations

import json
from typing import Dict

from market_reporter.core.types import AnalysisInput


SYSTEM_PROMPT = (
    "You are a professional equity analyst. Return concise and actionable analysis in JSON. "
    "Must include fields: summary, sentiment, key_levels, risks, action_items, confidence, markdown."
)


def build_user_prompt(payload: AnalysisInput) -> str:
    quote = payload.quote.model_dump() if payload.quote else {}
    kline = [item.model_dump() for item in payload.kline[-60:]]
    curve = [item.model_dump() for item in payload.curve[-120:]]
    news = [item.model_dump() for item in payload.news[:30]]
    fund_flow: Dict[str, list] = {
        key: [point.model_dump() for point in value[-12:]] for key, value in payload.fund_flow.items()
    }

    request_json = {
        "symbol": payload.symbol,
        "market": payload.market,
        "quote": quote,
        "kline": kline,
        "curve": curve,
        "news": news,
        "fund_flow": fund_flow,
        "watch_meta": payload.watch_meta,
        "instructions": {
            "language": "zh-CN",
            "focus": [
                "trend",
                "support_resistance",
                "risk",
                "actionable_next_steps",
            ],
            "output_format": "json",
        },
    }
    return json.dumps(request_json, ensure_ascii=False)
