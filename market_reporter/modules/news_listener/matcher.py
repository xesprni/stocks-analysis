from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from market_reporter.core.types import CurvePoint, NewsItem
from market_reporter.modules.market_data.symbol_mapper import strip_market_suffix
from market_reporter.modules.watchlist.schemas import WatchlistItem


def build_watch_keywords(item: WatchlistItem) -> List[str]:
    keywords = {
        item.symbol.upper(),
        strip_market_suffix(item.symbol.upper()),
    }
    if item.alias:
        keywords.add(item.alias.strip())
    if item.display_name:
        keywords.add(item.display_name.strip())
    for entry in item.keywords:
        if entry.strip():
            keywords.add(entry.strip())
    return sorted([keyword for keyword in keywords if keyword], key=len, reverse=True)


def find_symbol_news_matches(
    news_items: Iterable[NewsItem],
    watch_items: Iterable[WatchlistItem],
) -> Dict[Tuple[str, str], Dict[str, object]]:
    result: Dict[Tuple[str, str], Dict[str, object]] = {}
    cached_news = list(news_items)
    for item in watch_items:
        keywords = build_watch_keywords(item)
        if not keywords:
            continue
        matched_news = []
        hit_keywords = set()
        for news in cached_news:
            title = (news.title or "").lower()
            if not title:
                continue
            for keyword in keywords:
                if keyword.lower() in title:
                    matched_news.append(news)
                    hit_keywords.add(keyword)
                    break
        if not matched_news:
            continue
        result[(item.symbol, item.market)] = {
            "item": item,
            "keywords": sorted(hit_keywords),
            "news": matched_news,
        }
    return result


def calculate_window_change_percent(points: List[CurvePoint], window_minutes: int) -> Optional[float]:
    if len(points) < 2:
        return None
    parsed = []
    for point in points:
        ts = _parse_ts(point.ts)
        if ts is None:
            continue
        parsed.append((ts, point.price))
    if len(parsed) < 2:
        return None

    parsed.sort(key=lambda item: item[0])
    latest_ts, latest_price = parsed[-1]
    target_ts = latest_ts - timedelta(minutes=window_minutes)

    baseline_price = parsed[0][1]
    for ts, price in parsed:
        if ts <= target_ts:
            baseline_price = price
        else:
            break

    if baseline_price == 0:
        return None
    return (latest_price - baseline_price) / baseline_price * 100


def choose_severity(change_percent: float, threshold_percent: float) -> str:
    abs_change = abs(change_percent)
    if abs_change >= threshold_percent * 2:
        return "HIGH"
    if abs_change >= threshold_percent * 1.4:
        return "MEDIUM"
    return "LOW"


def _parse_ts(raw: str) -> Optional[datetime]:
    value = (raw or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
