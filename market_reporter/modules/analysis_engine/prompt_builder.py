from __future__ import annotations

import json
from typing import Dict, List

from market_reporter.core.types import AnalysisInput


# ---------------------------------------------------------------------------
# System prompt: Senior Equity Research Analyst persona
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior equity research analyst with 15+ years of experience in cross-market analysis \
(CN A-shares, HK equities, US equities). You combine technical analysis, fundamental insights, \
and macro/political awareness to produce actionable trading recommendations.

## Your analysis methodology

1. **Technical Analysis**
   - K-line pattern recognition: identify doji, engulfing, hammer, morning/evening star, etc.
   - Support and resistance levels from recent swing highs/lows
   - Moving average alignment (infer from price trajectory)
   - Volume-price divergence detection
   - Intraday momentum from real-time curve data

2. **News & Sentiment Analysis**
   - Categorize news by relevance: company-specific, sector, macro, political/regulatory
   - Assess sentiment polarity and urgency of each news cluster
   - Identify catalysts that may trigger short-term price moves
   - Flag conflicting signals between news sentiment and price action

3. **Fund Flow & Institutional Activity**
   - Analyze net inflow/outflow trends (northbound, southbound, ETF, etc.)
   - Detect institutional accumulation or distribution patterns
   - Compare fund flow direction vs. price direction for divergence

4. **Macro & Political Risk**
   - Evaluate relevant policy changes, trade tensions, regulatory shifts
   - Assess central bank signals, interest rate environment
   - Consider geopolitical events that may affect the market or sector

5. **Risk Assessment Framework**
   - Assign risk level: LOW / MEDIUM / HIGH / CRITICAL
   - Identify specific downside triggers and their probability
   - Suggest position sizing guidance based on risk level
   - Define stop-loss and take-profit zones where applicable

## Output requirements

Return exactly one valid JSON object with these keys:
- "summary": One-sentence core conclusion (in Chinese)
- "sentiment": "bullish" | "neutral" | "bearish"
- "key_levels": Array of key price levels or conditions (strings)
- "risks": Array of main risks (strings)
- "action_items": Array of actionable recommendations with specific conditions and thresholds
- "confidence": Decimal between 0 and 1
- "markdown": Structured Chinese analysis report in markdown format, organized into clear sections

For the "markdown" field, structure your report as follows:
## 核心观点
## 技术面分析
## 消息面与情绪
## 资金流向
## 风险评估
## 操作建议

Do NOT wrap output with markdown code fences. Return raw JSON only.
"""

# ---------------------------------------------------------------------------
# System prompt variant for market overview (no specific stock)
# ---------------------------------------------------------------------------

MARKET_OVERVIEW_SYSTEM_PROMPT = """\
You are a senior macro strategist and chief market analyst covering global equity markets \
(CN A-shares, HK equities, US equities). You synthesize news, fund flows, and cross-market \
signals to provide a comprehensive market outlook.

## Your analysis framework

1. **Market Sentiment Scan**
   - Overall risk appetite: risk-on vs. risk-off signals
   - Cross-market divergence: are CN/HK/US moving in sync or diverging?
   - Sector rotation patterns visible from news flow

2. **News & Event Impact**
   - Cluster news by theme: monetary policy, earnings, geopolitical, regulatory, trade
   - Rank events by market-moving potential
   - Identify overnight developments and their expected impact on each market

3. **Fund Flow Synopsis**
   - Northbound/southbound flow trends for CN-HK connect
   - ETF flow signals for US markets
   - Institutional vs. retail positioning shifts

4. **Macro & Political Landscape**
   - Central bank policy signals (PBOC, Fed, HKMA)
   - Key economic data releases and their implications
   - Political/regulatory events affecting market structure

5. **Cross-Market Opportunities & Risks**
   - Identify relative value opportunities across markets
   - Flag systemic risks that could cause correlated drawdowns
   - Suggest defensive vs. offensive positioning

## Output requirements

Return exactly one valid JSON object with these keys:
- "summary": One-sentence market outlook (in Chinese)
- "sentiment": "bullish" | "neutral" | "bearish"
- "key_levels": Array of key market levels or themes to watch
- "risks": Array of main macro risks
- "action_items": Array of strategic recommendations
- "confidence": Decimal between 0 and 1
- "markdown": Structured Chinese market overview in markdown, organized as:

## 市场总览
## 各市场动态
## 热点事件解读
## 资金流向分析
## 宏观与政策
## 风险提示
## 策略建议

Do NOT wrap output with markdown code fences. Return raw JSON only.
"""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_user_prompt(payload: AnalysisInput) -> str:
    """Build the user prompt for individual stock analysis."""
    is_market_overview = payload.symbol in (
        "MARKET",
        "WATCHLIST_ALERTS",
    ) or payload.watch_meta.get("mode") in (
        "overview",
        "watchlist_news_listener",
    )

    if is_market_overview:
        return _build_market_overview_prompt(payload)
    return _build_stock_analysis_prompt(payload)


def get_system_prompt(payload: AnalysisInput) -> str:
    """Return the appropriate system prompt based on analysis mode."""
    is_market_overview = payload.symbol in (
        "MARKET",
        "WATCHLIST_ALERTS",
    ) or payload.watch_meta.get("mode") in (
        "overview",
        "watchlist_news_listener",
    )
    if is_market_overview:
        return MARKET_OVERVIEW_SYSTEM_PROMPT
    return SYSTEM_PROMPT


def _build_stock_analysis_prompt(payload: AnalysisInput) -> str:
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
        for item in payload.kline[-60:]
    ]
    curve_tail = [
        {
            "ts": item.ts,
            "price": item.price,
            "volume": item.volume,
        }
        for item in payload.curve[-90:]
    ]

    # Categorize news by type for richer analysis
    news_digest = _categorize_news(payload.news[:40])

    fund_flow: Dict[str, list] = {
        key: [point.model_dump(mode="json") for point in value[-12:]]
        for key, value in payload.fund_flow.items()
    }

    request_json = {
        "task": "对以下股票进行专业级多维度交易分析，输出可执行的投资建议。",
        "analysis_mode": "individual_stock",
        "symbol": payload.symbol,
        "market": payload.market,
        "output_contract": {
            "summary": "一句话核心结论（中文），包含方向判断和关键条件",
            "sentiment": "bullish|neutral|bearish",
            "key_levels": ["具体的关键价位、支撑位、压力位，附带触发条件"],
            "risks": ["具体风险描述，包含风险等级(LOW/MEDIUM/HIGH)和触发条件"],
            "action_items": ["具体可执行操作，包含进场条件、目标位、止损位"],
            "confidence": "0到1之间的小数，综合考虑数据质量和信号一致性",
            "markdown": "结构化中文分析报告",
        },
        "analysis_instructions": [
            "1. 技术面分析：识别K线形态（十字星、吞没、锤头等），判断趋势方向，计算支撑/压力位。",
            "2. 量价分析：检查成交量与价格变动是否配合，是否存在量价背离。",
            "3. 消息面分析：对新闻进行分类（公司、行业、宏观），评估情绪倾向和紧急程度。",
            "4. 资金流向分析：分析主力资金动向，是否与价格走势一致或背离。",
            "5. 风险评估：结合以上因素给出风险等级，提供具体的止损建议。",
            "6. 如果数据不足以支撑结论，明确指出并相应降低confidence值。",
            "7. 避免空泛判断，所有结论必须有数据支撑和具体触发条件。",
            "8. 只返回JSON对象，不要输出多余文本。",
        ],
        "data": {
            "quote": quote,
            "technical_summary": {
                "kline": _summarize_kline(payload),
                "curve": _summarize_curve(payload),
                "pattern_hints": _detect_basic_patterns(payload),
            },
            "kline_tail": kline_tail,
            "curve_tail": curve_tail,
            "news_digest": news_digest,
            "fund_flow": fund_flow,
            "fund_flow_summary": _summarize_fund_flow(payload),
            "watch_meta": payload.watch_meta,
        },
    }
    return json.dumps(request_json, ensure_ascii=False)


def _build_market_overview_prompt(payload: AnalysisInput) -> str:
    # For watchlist_news_listener mode, preserve the original format
    if payload.watch_meta.get("mode") == "watchlist_news_listener":
        request_json = {
            "task": "对以下新闻告警候选进行专业分析，评估其市场影响。",
            "analysis_mode": "watchlist_news_listener",
            "candidates": payload.watch_meta.get("candidates", []),
            "required_output": payload.watch_meta.get("required_output", {}),
            "analysis_instructions": [
                "对每条新闻评估其对相关股票的影响程度和紧急性。",
                "结合市场环境判断新闻的实际影响力。",
                "给出severity评级：LOW/MEDIUM/HIGH。",
                "只返回JSON对象。",
            ],
        }
        return json.dumps(request_json, ensure_ascii=False)

    news_digest = _categorize_news(payload.news[:50])
    fund_flow: Dict[str, list] = {
        key: [point.model_dump(mode="json") for point in value[-12:]]
        for key, value in payload.fund_flow.items()
    }

    request_json = {
        "task": "综合分析当前市场形势，提供跨市场宏观策略建议。",
        "analysis_mode": "market_overview",
        "output_contract": {
            "summary": "一句话市场总览结论（中文）",
            "sentiment": "bullish|neutral|bearish（整体市场情绪）",
            "key_levels": ["各主要指数关键点位、重要事件时间节点"],
            "risks": ["系统性风险、政策风险、地缘政治风险等"],
            "action_items": ["策略建议：仓位管理、行业配置、防御/进攻策略"],
            "confidence": "0到1之间的小数",
            "markdown": "结构化中文市场分析报告",
        },
        "analysis_instructions": [
            "1. 按市场分类分析：A股、港股、美股各自的运行状态和驱动因素。",
            "2. 识别跨市场联动或背离信号。",
            "3. 评估新闻事件的市场影响力，按影响级别排序。",
            "4. 分析资金流向趋势，判断机构动向。",
            "5. 提供明确的仓位管理和配置建议。",
            "6. 只返回JSON对象。",
        ],
        "data": {
            "news_digest": news_digest,
            "fund_flow": fund_flow,
            "fund_flow_summary": _summarize_fund_flow(payload),
            "watch_meta": payload.watch_meta,
        },
    }
    return json.dumps(request_json, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Technical analysis helpers
# ---------------------------------------------------------------------------


def _summarize_kline(payload: AnalysisInput) -> Dict[str, object]:
    bars = payload.kline[-120:]
    if not bars:
        return {}
    first = bars[0]
    last = bars[-1]
    highs = [item.high for item in bars]
    lows = [item.low for item in bars]
    closes = [item.close for item in bars]
    volumes = [item.volume for item in bars if item.volume is not None]
    change_pct = 0.0
    if first.close:
        change_pct = round(((last.close - first.close) / first.close) * 100, 4)

    # Calculate simple moving average proxies
    ma5 = round(sum(closes[-5:]) / min(5, len(closes[-5:])), 4) if closes else None
    ma10 = (
        round(sum(closes[-10:]) / min(10, len(closes[-10:])), 4)
        if len(closes) >= 5
        else None
    )
    ma20 = (
        round(sum(closes[-20:]) / min(20, len(closes[-20:])), 4)
        if len(closes) >= 10
        else None
    )

    # Determine trend from MAs
    trend = "unknown"
    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            trend = "bullish_aligned"
        elif ma5 < ma10 < ma20:
            trend = "bearish_aligned"
        else:
            trend = "mixed"

    # Volume trend (recent 5 bars vs prior 5 bars)
    volume_trend = "unknown"
    if len(volumes) >= 10:
        recent_vol = sum(volumes[-5:]) / 5
        prior_vol = sum(volumes[-10:-5]) / 5
        if prior_vol > 0:
            vol_change = (recent_vol - prior_vol) / prior_vol
            if vol_change > 0.2:
                volume_trend = "increasing"
            elif vol_change < -0.2:
                volume_trend = "decreasing"
            else:
                volume_trend = "stable"

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
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma_trend": trend,
        "volume_trend": volume_trend,
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

    # Detect intraday momentum
    momentum = "flat"
    if len(prices) >= 20:
        recent_segment = prices[-10:]
        prior_segment = prices[-20:-10]
        recent_avg = sum(recent_segment) / len(recent_segment)
        prior_avg = sum(prior_segment) / len(prior_segment)
        if prior_avg > 0:
            seg_change = (recent_avg - prior_avg) / prior_avg * 100
            if seg_change > 0.3:
                momentum = "accelerating_up"
            elif seg_change < -0.3:
                momentum = "accelerating_down"
            else:
                momentum = "stable"

    return {
        "points": len(points),
        "start_ts": first.ts,
        "end_ts": last.ts,
        "first_price": first.price,
        "last_price": last.price,
        "change_pct": change_pct,
        "price_high": max(prices),
        "price_low": min(prices),
        "intraday_momentum": momentum,
    }


def _detect_basic_patterns(payload: AnalysisInput) -> List[str]:
    """Detect basic K-line patterns from the last few bars to hint the LLM."""
    bars = payload.kline[-10:]
    if len(bars) < 2:
        return []

    patterns: List[str] = []
    last = bars[-1]
    prev = bars[-2]

    body_last = abs(last.close - last.open)
    range_last = last.high - last.low

    # Doji detection
    if range_last > 0 and body_last / range_last < 0.1:
        patterns.append("doji_last_bar")

    # Hammer / inverted hammer
    if range_last > 0:
        lower_shadow = min(last.open, last.close) - last.low
        upper_shadow = last.high - max(last.open, last.close)
        if lower_shadow > body_last * 2 and upper_shadow < body_last * 0.5:
            patterns.append("hammer_last_bar")
        if upper_shadow > body_last * 2 and lower_shadow < body_last * 0.5:
            patterns.append("inverted_hammer_last_bar")

    # Bullish / bearish engulfing
    if last.close > last.open and prev.close < prev.open:
        if last.open <= prev.close and last.close >= prev.open:
            patterns.append("bullish_engulfing")
    if last.close < last.open and prev.close > prev.open:
        if last.open >= prev.close and last.close <= prev.open:
            patterns.append("bearish_engulfing")

    # Gap detection
    if last.low > prev.high:
        patterns.append("gap_up")
    if last.high < prev.low:
        patterns.append("gap_down")

    # Volume spike on last bar
    volumes = [b.volume for b in bars if b.volume is not None]
    if len(volumes) >= 5 and volumes[-1] is not None:
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        if avg_vol > 0 and volumes[-1] > avg_vol * 2:
            patterns.append("volume_spike_last_bar")

    return patterns


def _categorize_news(news_items: list) -> Dict[str, list]:
    """Categorize news items by type for structured analysis."""
    categories: Dict[str, list] = {
        "macro_policy": [],
        "market_data": [],
        "company_sector": [],
        "geopolitical": [],
        "other": [],
    }

    macro_keywords = {
        "央行",
        "利率",
        "降息",
        "加息",
        "GDP",
        "CPI",
        "PMI",
        "货币政策",
        "财政",
        "fed",
        "pboc",
        "interest rate",
        "inflation",
        "monetary",
        "fiscal",
        "就业",
        "失业",
        "贸易",
        "关税",
        "汇率",
        "美联储",
        "国务院",
    }
    geo_keywords = {
        "战争",
        "制裁",
        "冲突",
        "地缘",
        "military",
        "sanction",
        "war",
        "tension",
        "选举",
        "election",
        "政变",
        "外交",
    }

    for item in news_items:
        title_lower = (item.title or "").lower()
        category_lower = (item.category or "").lower()
        entry = {
            "source": item.source,
            "category": item.category,
            "published": item.published,
            "title": item.title[:200],
        }

        if any(kw in title_lower for kw in macro_keywords):
            categories["macro_policy"].append(entry)
        elif any(kw in title_lower for kw in geo_keywords):
            categories["geopolitical"].append(entry)
        elif category_lower in ("market", "data", "经济数据", "行情"):
            categories["market_data"].append(entry)
        elif category_lower in ("company", "sector", "industry", "个股", "行业"):
            categories["company_sector"].append(entry)
        else:
            categories["other"].append(entry)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def _summarize_fund_flow(payload: AnalysisInput) -> Dict[str, object]:
    """Summarize fund flow trends across all series."""
    if not payload.fund_flow:
        return {}

    summary: Dict[str, object] = {}
    for key, points in payload.fund_flow.items():
        if not points:
            continue
        recent = points[-6:]
        values = []
        for p in recent:
            val = getattr(p, "value", None) or getattr(p, "amount", None)
            if val is not None:
                values.append(float(val))

        if not values:
            continue

        net_direction = (
            "inflow" if sum(values) > 0 else "outflow" if sum(values) < 0 else "neutral"
        )
        trend = "unknown"
        if len(values) >= 3:
            first_half = sum(values[: len(values) // 2])
            second_half = sum(values[len(values) // 2 :])
            if second_half > first_half * 1.2:
                trend = "accelerating_inflow"
            elif second_half < first_half * 0.8:
                trend = "decelerating" if second_half > 0 else "accelerating_outflow"
            else:
                trend = "stable"

        summary[key] = {
            "recent_periods": len(values),
            "net_direction": net_direction,
            "trend": trend,
            "total": round(sum(values), 2),
        }

    return summary
