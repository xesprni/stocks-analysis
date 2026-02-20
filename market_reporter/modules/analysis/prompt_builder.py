from __future__ import annotations

import json
from typing import Dict

from market_reporter.core.types import AnalysisInput


# ---------------------------------------------------------------------------
# System prompt: Market overview / news alert analyst persona
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
    """Build the user prompt for market overview / news alert triage."""
    return _build_market_overview_prompt(payload)


def get_system_prompt(payload: AnalysisInput) -> str:
    """Return the system prompt for LLM-based analysis."""
    return MARKET_OVERVIEW_SYSTEM_PROMPT


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
# News categorization helpers
# ---------------------------------------------------------------------------


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

    # Remove empty categories to reduce prompt noise.
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
