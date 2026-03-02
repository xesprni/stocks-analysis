#!/usr/bin/env python3
"""
Market Brief Generator v3
- 多板块预测 + 政治经济分析
- 数据来源校验
- 真实数据，禁止捏造
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
import time

# ============ Configuration ============

RSS_FEEDS = {
    "finance": [
        ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
        ("CNBC Markets", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
        ("Reuters Business", "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best"),
    ],
    "politics": [
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("CNN Politics", "http://rss.cnn.com/rss/cnn_allpolitics.rss"),
        ("Reuters Politics", "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best;topic=politics"),
    ],
    "economics": [
        ("Economist", "https://www.economist.com/world/rss.xml"),
        ("FT World", "https://www.ft.com/rss/world"),
    ],
    "asia": [
        ("SCMP China", "https://www.scmp.com/rss/91/feed"),
        ("Nikkei Asia", "https://asia.nikkei.com/rss/feed"),
    ]
}

# 美股板块 ETF（用于板块分析）
US_SECTOR_ETFS = {
    "XLK": "科技",
    "XLF": "金融",
    "XLV": "医疗",
    "XLE": "能源",
    "XLY": "消费",
    "XLI": "工业",
    "XLB": "材料",
    "XLRE": "房地产",
    "XLU": "公用事业",
    "XLC": "通信",
}

# 经济指标来源
ECON_INDICATORS = {
    "vix": "^VIX",
    "dxy": "DX-Y.NYB",  # 美元指数
    "gold": "GC=F",     # 黄金期货
    "oil": "CL=F",      # 原油期货
    "treasury_10y": "^TNX",  # 10年期美债收益率
}

CONFIG_FILE = os.path.expanduser("~/.openclaw/market-brief-config.json")

# ============ Data Validation ============

class DataValidator:
    """验证数据来源和完整性"""
    
    def __init__(self):
        self.sources = []
        self.warnings = []
    
    def log_source(self, source: str, data_type: str, status: str = "ok"):
        self.sources.append({
            "source": source,
            "type": data_type,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    def warn(self, msg: str):
        self.warnings.append(msg)
        print(f"⚠️ WARNING: {msg}", file=sys.stderr)
    
    def validate_price(self, price, name: str) -> bool:
        """验证价格数据合理性"""
        if price is None:
            self.warn(f"{name}: 价格数据缺失")
            return False
        if not isinstance(price, (int, float)):
            self.warn(f"{name}: 价格格式错误 ({type(price)})")
            return False
        if price <= 0:
            self.warn(f"{name}: 价格异常 ({price})")
            return False
        return True
    
    def validate_pct(self, pct, name: str) -> bool:
        """验证百分比变化合理性"""
        if pct is None:
            return False  # 允许缺失，但不使用
        if not isinstance(pct, (int, float)):
            return False
        if abs(pct) > 50:  # 单日涨跌超过50%通常是错误
            self.warn(f"{name}: 涨跌幅异常 ({pct}%)")
            return False
        return True
    
    def report(self) -> str:
        """生成数据来源报告"""
        lines = ["\n---\n**数据来源**"]
        ok_sources = [s for s in self.sources if s["status"] == "ok"]
        failed_sources = [s for s in self.sources if s["status"] != "ok"]
        
        for s in ok_sources:
            lines.append(f"- ✅ {s['type']}: {s['source']}")
        for s in failed_sources:
            lines.append(f"- ❌ {s['type']}: {s['source']}")
        
        if self.warnings:
            lines.append("\n**警告**:")
            for w in self.warnings:
                lines.append(f"- {w}")
        
        return "\n".join(lines)


validator = DataValidator()


# ============ RSS Fetching ============

def fetch_rss(url: str, limit: int = 10) -> List[dict]:
    """Fetch and parse RSS feed with error handling."""
    import feedparser
    
    try:
        feed = feedparser.parse(url, agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
        
        if feed.bozo and feed.bozo_exception:
            validator.warn(f"RSS解析警告 ({url}): {feed.bozo_exception}")
        
        items = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "")
            if not title:
                continue
            items.append({
                "title": title,
                "link": entry.get("link", ""),
                "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
                "source": feed.feed.get("title", ""),
                "published": entry.get("published", ""),
            })
        
        validator.log_source(url, "RSS", "ok" if items else "empty")
        return items
    except Exception as e:
        validator.log_source(url, "RSS", f"error: {e}")
        return []


def fetch_all_news(categories: List[str] = None) -> List[dict]:
    """Fetch news from all configured feeds."""
    all_news = []
    cats = categories or list(RSS_FEEDS.keys())
    
    for cat in cats:
        if cat not in RSS_FEEDS:
            continue
        for name, url in RSS_FEEDS[cat]:
            items = fetch_rss(url)
            for item in items:
                item["category"] = cat
                item["feed_name"] = name
            all_news.extend(items)
            time.sleep(0.5)  # 避免请求过快
    
    # Deduplicate
    seen = set()
    unique = []
    for item in all_news:
        title_key = item["title"].lower()[:50]
        if title_key not in seen:
            seen.add(title_key)
            unique.append(item)
    
    return unique


# ============ Market Data ============

def fetch_yfinance_data(symbols: List[str], source_name: str) -> Dict:
    """Fetch data from Yahoo Finance with validation."""
    import yfinance as yf
    
    data = {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        
        for symbol in symbols:
            try:
                t = tickers.tickers.get(symbol)
                if not t:
                    continue
                    
                info = t.info
                if not info:
                    continue
                
                price = info.get("regularMarketPrice")
                change = info.get("regularMarketChange")
                change_pct = info.get("regularMarketChangePercent")
                
                if validator.validate_price(price, f"{source_name}/{symbol}"):
                    data[symbol] = {
                        "name": info.get("shortName", symbol),
                        "price": round(price, 2) if price else None,
                        "change": round(change, 2) if change else None,
                        "change_pct": round(change_pct, 2) if change_pct else None,
                    }
                    validator.log_source(f"Yahoo Finance/{symbol}", source_name, "ok")
            except Exception as e:
                validator.log_source(f"Yahoo Finance/{symbol}", source_name, f"error: {e}")
    except Exception as e:
        validator.warn(f"yfinance error: {e}")
    
    return data


def fetch_us_indices() -> Dict:
    """Fetch US major indices."""
    return fetch_yfinance_data(
        ["^GSPC", "^IXIC", "^DJI", "^VIX"],
        "美股指数"
    )


def fetch_us_futures() -> Dict:
    """Fetch US futures."""
    return fetch_yfinance_data(
        ["ES=F", "NQ=F", "YM=F"],
        "美股期货"
    )


def fetch_us_sectors() -> Dict:
    """Fetch US sector ETFs for sector analysis."""
    return fetch_yfinance_data(
        list(US_SECTOR_ETFS.keys()),
        "板块ETF"
    )


def fetch_econ_indicators() -> Dict:
    """Fetch economic indicators."""
    return fetch_yfinance_data(
        list(ECON_INDICATORS.values()),
        "经济指标"
    )


def fetch_hk_market() -> Dict:
    """Fetch HK market."""
    return fetch_yfinance_data(
        ["^HSI", "^HSCE"],
        "港股指数"
    )


def fetch_cn_market() -> Dict:
    """Fetch A-share indices using East Money API."""
    import requests
    data = {}
    
    secids = "1.000001,1.000300,0.399001,0.399006"
    
    try:
        resp = requests.get(
            f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f3,f12,f14&secids={secids}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        result = resp.json()
        
        for item in result.get("data", {}).get("diff", []):
            code = item.get("f12", "")
            price = item.get("f2")
            pct = item.get("f3")
            
            if validator.validate_price(float(price) if price != "-" else None, f"A股/{code}"):
                data[code] = {
                    "name": item.get("f14", code),
                    "price": float(price) if price != "-" else None,
                    "change_pct": float(pct) if pct != "-" else None,
                }
        
        validator.log_source("东方财富", "A股指数", "ok")
    except Exception as e:
        validator.log_source("东方财富", "A股指数", f"error: {e}")
    
    return data


# ============ Analysis ============

def classify_news(news_items: List[dict]) -> Dict[str, List[dict]]:
    """按主题分类新闻"""
    themes = {
        "politics": [],
        "economy": [],
        "tech_ai": [],
        "china": [],
        "energy": [],
        "finance": [],
        "other": [],
    }
    
    keywords = {
        "politics": ["trump", "biden", "election", "tariff", "sanctions", "policy", "white house", "congress", "fed", "央行", "政策", "关税"],
        "economy": ["gdp", "inflation", "rates", "recession", "jobs", "employment", "growth", "经济", "通胀", "利率"],
        "tech_ai": ["ai", "nvidia", "apple", "microsoft", "google", "deepseek", "chip", "semiconductor", "科技", "芯片"],
        "china": ["china", "chinese", "beijing", "shanghai", "中国", "北京"],
        "energy": ["oil", "gas", "energy", "crude", "opec", "原油", "能源"],
        "finance": ["bank", "earnings", "stock", "market", "fund", "银行", "财报", "基金"],
    }
    
    for item in news_items:
        title_lower = item["title"].lower()
        classified = False
        
        for theme, kws in keywords.items():
            if any(kw in title_lower for kw in kws):
                themes[theme].append(item)
                classified = True
                break
        
        if not classified:
            themes["other"].append(item)
    
    return themes


def analyze_sector_performance(sector_data: Dict) -> Dict:
    """分析板块表现"""
    analysis = {
        "leading": [],  # 领涨
        "lagging": [],  # 领跌
        "neutral": [],  # 中性
    }
    
    for symbol, data in sector_data.items():
        pct = data.get("change_pct")
        if pct is None:
            continue
        
        name = US_SECTOR_ETFS.get(symbol, symbol)
        entry = {"name": name, "symbol": symbol, "change_pct": pct}
        
        if pct > 1:
            analysis["leading"].append(entry)
        elif pct < -1:
            analysis["lagging"].append(entry)
        else:
            analysis["neutral"].append(entry)
    
    # 排序
    analysis["leading"].sort(key=lambda x: x["change_pct"], reverse=True)
    analysis["lagging"].sort(key=lambda x: x["change_pct"])
    
    return analysis


def generate_comprehensive_brief(
    market: str,
    news_items: List[dict],
    indices_data: Dict,
    sectors_data: Dict,
    econ_data: Dict,
    use_ai: bool = True
) -> str:
    """生成全面的市场简报"""
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    # 分类新闻
    classified_news = classify_news(news_items)
    
    # 板块分析
    sector_analysis = analyze_sector_performance(sectors_data)
    
    # 构建报告
    market_names = {"us": "美股", "hk": "港股", "cn": "A股"}
    
    report = f"# 📊 {market_names.get(market, market.upper())}市场深度简报\n"
    report += f"_生成时间: {now}_\n\n"
    
    # === 1. 市场概览 ===
    report += "## 一、市场概览\n\n"
    if indices_data:
        for symbol, data in indices_data.items():
            price = data.get("price", "N/A")
            pct = data.get("change_pct")
            name = data.get("name", symbol)
            
            if pct is not None:
                emoji = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
                report += f"- **{name}**: {price:,.2f} {emoji} {pct:+.2f}%\n"
            else:
                report += f"- **{name}**: {price:,.2f}\n"
    else:
        report += "_指数数据暂不可用_\n"
    
    # === 2. 宏观环境 ===
    report += "\n## 二、宏观环境\n\n"
    if econ_data:
        indicator_names = {
            "^VIX": "VIX恐慌指数",
            "DX-Y.NYB": "美元指数",
            "GC=F": "黄金",
            "CL=F": "原油",
            "^TNX": "10年期美债收益率",
        }
        for symbol, data in econ_data.items():
            name = indicator_names.get(symbol, data.get("name", symbol))
            price = data.get("price")
            pct = data.get("change_pct")
            if price:
                if pct is not None:
                    report += f"- **{name}**: {price:,.2f} ({pct:+.2f}%)\n"
                else:
                    report += f"- **{name}**: {price:,.2f}\n"
    
    # === 3. 板块表现 ===
    report += "\n## 三、板块表现\n\n"
    
    if sector_analysis["leading"]:
        report += "**🟢 领涨板块**\n"
        for s in sector_analysis["leading"][:3]:
            report += f"- {s['name']}: +{s['change_pct']:.2f}%\n"
    
    if sector_analysis["lagging"]:
        report += "\n**🔴 领跌板块**\n"
        for s in sector_analysis["lagging"][:3]:
            report += f"- {s['name']}: {s['change_pct']:.2f}%\n"
    
    if not sector_analysis["leading"] and not sector_analysis["lagging"]:
        report += "_板块数据暂不可用_\n"
    
    # === 4. 新闻分析 ===
    report += "\n## 四、新闻要点\n\n"
    
    # 政治
    if classified_news["politics"]:
        report += "**🏛️ 政治/政策**\n"
        for item in classified_news["politics"][:3]:
            report += f"- {item['title']}\n"
        report += "\n"
    
    # 经济
    if classified_news["economy"]:
        report += "**💰 经济/央行**\n"
        for item in classified_news["economy"][:3]:
            report += f"- {item['title']}\n"
        report += "\n"
    
    # 科技/AI
    if classified_news["tech_ai"]:
        report += "**🤖 科技/AI**\n"
        for item in classified_news["tech_ai"][:3]:
            report += f"- {item['title']}\n"
        report += "\n"
    
    # 中国相关
    if classified_news["china"]:
        report += "**🇨🇳 中国相关**\n"
        for item in classified_news["china"][:3]:
            report += f"- {item['title']}\n"
        report += "\n"
    
    # 能源
    if classified_news["energy"]:
        report += "**⚡ 能源/大宗**\n"
        for item in classified_news["energy"][:3]:
            report += f"- {item['title']}\n"
        report += "\n"
    
    # === 5. AI 深度分析 ===
    if use_ai and (news_items or indices_data):
        report += "\n## 五、AI 综合分析\n\n"
        ai_summary = generate_ai_analysis(
            indices_data, sectors_data, econ_data, classified_news, market
        )
        report += ai_summary + "\n"
    
    # === 数据来源 ===
    report += validator.report()
    
    return report


def generate_ai_analysis(indices, sectors, econ, news, market) -> str:
    """使用 LLM 生成深度分析"""
    
    # 准备市场数据摘要
    market_summary = []
    for sym, data in indices.items():
        pct = data.get("change_pct")
        if pct is not None:
            market_summary.append(f"{data.get('name', sym)}: {pct:+.2f}%")
    
    sector_summary = []
    for sym, data in sectors.items():
        pct = data.get("change_pct")
        if pct is not None:
            sector_summary.append(f"{US_SECTOR_ETFS.get(sym, sym)}: {pct:+.2f}%")
    
    econ_summary = []
    for sym, data in econ.items():
        pct = data.get("change_pct")
        if pct is not None:
            econ_summary.append(f"{data.get('name', sym)}: {pct:+.2f}%")
    
    # 准备新闻标题
    all_titles = []
    for category, items in news.items():
        for item in items[:5]:
            all_titles.append(item["title"])
    
    prompt = f"""你是资深市场分析师。基于以下**真实数据**，生成深度市场分析报告。

**重要**：所有分析必须基于提供的数据，不得编造数据或随意推测。

## 市场数据
指数: {', '.join(market_summary) if market_summary else '暂无'}
板块: {', '.join(sector_summary) if sector_summary else '暂无'}
宏观: {', '.join(econ_summary) if econ_summary else '暂无'}

## 主要新闻
{chr(10).join(f'- {t}' for t in all_titles[:15])}

## 输出要求（中文，300字内）

### 1. 市场情绪判断
- 风险偏好/避险
- 依据哪些数据判断

### 2. 板块轮动预测
- 哪些板块可能走强（基于今日表现+新闻）
- 哪些板块需警惕
- 具体理由

### 3. 政治经济影响
- 主要政策/政治事件
- 对市场的潜在影响

### 4. 风险提示
- 具体风险点
- 关注指标

直接输出分析，不要开场白。"""

    try:
        import subprocess
        result = subprocess.run(
            ["openclaw", "agent", "--agent", "main", "--local", "--timeout", "90", "--message", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            validator.warn(f"AI分析失败: {result.stderr[:100]}")
    except Exception as e:
        validator.warn(f"AI分析异常: {e}")
    
    # Fallback
    return generate_fallback_analysis(indices, sectors, econ)


def generate_fallback_analysis(indices, sectors, econ) -> str:
    """备用：基于规则的分析"""
    
    # 计算市场整体涨跌
    total_pct = 0
    count = 0
    for data in indices.values():
        if data.get("change_pct"):
            total_pct += data["change_pct"]
            count += 1
    
    avg_pct = total_pct / count if count > 0 else 0
    
    if avg_pct > 0.5:
        sentiment = "🟢 市场情绪乐观，风险偏好上升"
    elif avg_pct < -0.5:
        sentiment = "🔴 市场情绪谨慎，避险倾向明显"
    else:
        sentiment = "🟡 市场震荡，多空分歧"
    
    # VIX 分析
    vix_data = econ.get("^VIX", {})
    vix_level = vix_data.get("price", 0)
    
    if vix_level > 25:
        vix_comment = "VIX处于高位（>25），市场恐慌情绪较重"
    elif vix_level > 18:
        vix_comment = "VIX处于中等水平，市场存在一定担忧"
    else:
        vix_comment = "VIX处于低位，市场相对平静"
    
    return f"""**市场情绪**: {sentiment}

**波动率**: {vix_comment}

**注意**: AI分析服务暂不可用，以上为简化分析。"""


# ============ Main ============

def main():
    parser = argparse.ArgumentParser(description="Generate comprehensive market brief")
    parser.add_argument("--market", "-m", default="us", 
                        choices=["us", "hk", "cn"],
                        help="Market to fetch")
    parser.add_argument("--no-ai", action="store_true",
                        help="Disable AI analysis")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file")
    parser.add_argument("--categories", "-c", nargs="+",
                        default=["finance", "politics", "economics", "asia"],
                        help="RSS categories")
    args = parser.parse_args()
    
    print(f"正在获取 {args.market} 市场数据...", file=sys.stderr)
    
    # 获取新闻
    print("获取新闻...", file=sys.stderr)
    news_items = fetch_all_news(args.categories)
    print(f"获取到 {len(news_items)} 条新闻", file=sys.stderr)
    
    # 获取市场数据
    if args.market == "us":
        indices_data = fetch_us_indices()
        sectors_data = fetch_us_sectors()
        econ_data = fetch_econ_indicators()
    elif args.market == "hk":
        indices_data = fetch_hk_market()
        sectors_data = {}
        econ_data = fetch_econ_indicators()
    elif args.market == "cn":
        indices_data = fetch_cn_market()
        sectors_data = {}
        econ_data = {}
    
    # 生成报告
    report = generate_comprehensive_brief(
        args.market,
        news_items,
        indices_data,
        sectors_data,
        econ_data,
        use_ai=not args.no_ai
    )
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存到 {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
