from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.models import WatchlistNewsAlertTable
from market_reporter.infra.db.repos import NewsListenerRunRepo, WatchlistNewsAlertRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.analysis_engine.service import AnalysisService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.news_listener.matcher import (
    calculate_window_change_percent,
    choose_severity,
    find_symbol_news_matches,
)
from market_reporter.modules.news_listener.schemas import (
    MatchedAlertCandidate,
    NewsAlertView,
    NewsListenerRunView,
)
from market_reporter.modules.watchlist.service import WatchlistService


class NewsListenerService:
    def __init__(
        self,
        config: AppConfig,
        registry: ProviderRegistry,
        news_service: Optional[NewsService],
        watchlist_service: WatchlistService,
        market_data_service: MarketDataService,
        analysis_service: AnalysisService,
    ) -> None:
        self.config = config
        self.registry = registry
        self.news_service = news_service
        self.watchlist_service = watchlist_service
        self.market_data_service = market_data_service
        self.analysis_service = analysis_service
        self._run_lock = asyncio.Lock()

    async def run_once(self) -> NewsListenerRunView:
        if self._run_lock.locked():
            raise ValueError("News listener task is already running")

        async with self._run_lock:
            if self.news_service is None:
                raise ValueError("News listener is missing news service dependency")
            started_at = datetime.utcnow()
            error_messages: List[str] = []
            status = "SUCCESS"
            scanned_news_count = 0
            matched_news_count = 0
            alerts: List[MatchedAlertCandidate] = []

            try:
                watch_items = self.watchlist_service.list_enabled_items()
                news_items, news_warnings = await self.news_service.collect(
                    limit=self.config.news_listener.max_news_per_cycle
                )
                scanned_news_count = len(news_items)
                error_messages.extend(news_warnings)

                matches = find_symbol_news_matches(news_items=news_items, watch_items=watch_items)
                matched_news_count = sum(len(value.get("news", [])) for value in matches.values())
                alerts = await self._build_alert_candidates(matches)
            except Exception as exc:
                status = "FAILED"
                error_messages.append(str(exc))
                alerts = []

            analysis_results = await self._run_analysis(alerts=alerts, errors=error_messages)
            finished_at = datetime.utcnow()

            with session_scope(self.config.database.url) as session:
                run_repo = NewsListenerRunRepo(session)
                alert_repo = WatchlistNewsAlertRepo(session)
                run = run_repo.add(
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    scanned_news_count=scanned_news_count,
                    matched_news_count=matched_news_count,
                    alerts_count=len(alerts),
                    error_message=" | ".join(error_messages)[:2000] if error_messages else None,
                )
                if alerts:
                    rows: List[WatchlistNewsAlertTable] = []
                    for idx, candidate in enumerate(alerts):
                        analysis = analysis_results[idx] if idx < len(analysis_results) else {}
                        rows.append(
                            WatchlistNewsAlertTable(
                                run_id=int(run.id),
                                symbol=candidate.symbol,
                                market=candidate.market,
                                news_title=candidate.news_title,
                                news_link=candidate.news_link,
                                news_source=candidate.news_source,
                                published_at=candidate.published_at,
                                move_window_minutes=candidate.move_window_minutes,
                                price_change_percent=candidate.price_change_percent,
                                threshold_percent=candidate.threshold_percent,
                                severity=str(analysis.get("severity") or candidate.severity),
                                analysis_summary=str(analysis.get("summary") or "规则触发：价格异动且新闻命中 watchlist"),
                                analysis_markdown=str(
                                    analysis.get("markdown")
                                    or (
                                        f"### {candidate.symbol}\n"
                                        f"- 命中新闻：{candidate.news_title}\n"
                                        f"- {candidate.move_window_minutes}分钟涨跌幅："
                                        f"{candidate.price_change_percent:.2f}%\n"
                                    )
                                ),
                                analysis_json=json.dumps(analysis or {}, ensure_ascii=False, default=str),
                                status="UNREAD",
                            )
                        )
                    alert_repo.add_many(rows)
                run_id = int(run.id)

            return NewsListenerRunView(
                id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                scanned_news_count=scanned_news_count,
                matched_news_count=matched_news_count,
                alerts_count=len(alerts),
                error_message=" | ".join(error_messages)[:2000] if error_messages else None,
            )

    def list_runs(self, limit: int = 50) -> List[NewsListenerRunView]:
        try:
            with session_scope(self.config.database.url) as session:
                repo = NewsListenerRunRepo(session)
                rows = repo.list_recent(limit=limit)
                result: List[NewsListenerRunView] = []
                for row in rows:
                    try:
                        result.append(NewsListenerRunView.model_validate(row, from_attributes=True))
                    except Exception:
                        continue
        except Exception:
            return []
        return result

    def list_alerts(
        self,
        status: str = "ALL",
        symbol: Optional[str] = None,
        market: Optional[str] = None,
        limit: int = 50,
    ) -> List[NewsAlertView]:
        symbol_value = symbol.strip().upper() if symbol else None
        market_value = market.strip().upper() if market else None
        try:
            with session_scope(self.config.database.url) as session:
                repo = WatchlistNewsAlertRepo(session)
                rows = repo.list_recent(
                    status=status.upper(),
                    symbol=symbol_value,
                    market=market_value,
                    limit=limit,
                )
                return [self._to_alert_view(row) for row in rows]
        except Exception:
            return []

    def update_alert_status(self, alert_id: int, status: str) -> NewsAlertView:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistNewsAlertRepo(session)
            row = repo.get(alert_id)
            if row is None:
                raise ValueError(f"Alert not found: {alert_id}")
            updated = repo.update_status(row=row, status=status.upper())
            return self._to_alert_view(updated)

    def mark_all_read(self) -> int:
        with session_scope(self.config.database.url) as session:
            repo = WatchlistNewsAlertRepo(session)
            return repo.mark_all_read()

    async def _build_alert_candidates(self, matches: Dict[Tuple[str, str], Dict[str, object]]) -> List[MatchedAlertCandidate]:
        tasks = []
        for key, value in matches.items():
            tasks.append(self._evaluate_symbol(symbol=key[0], market=key[1], payload=value))
        evaluated = await asyncio.gather(*tasks) if tasks else []

        threshold = self.config.news_listener.move_threshold_percent
        window_minutes = self.config.news_listener.move_window_minutes
        alerts: List[MatchedAlertCandidate] = []
        for value in evaluated:
            if value is None:
                continue
            symbol, market, change_percent, payload = value
            if abs(change_percent) < threshold:
                continue
            severity = choose_severity(change_percent=change_percent, threshold_percent=threshold)
            news_items = payload.get("news", [])
            keywords = [str(item) for item in payload.get("keywords", [])]
            for news in news_items[:3]:
                alerts.append(
                    MatchedAlertCandidate(
                        symbol=symbol,
                        market=market,
                        news_title=news.title,
                        news_link=news.link,
                        news_source=news.source,
                        published_at=news.published,
                        price_change_percent=change_percent,
                        threshold_percent=threshold,
                        move_window_minutes=window_minutes,
                        severity=severity,
                        watch_keywords=keywords,
                    )
                )
        return alerts

    async def _evaluate_symbol(
        self,
        symbol: str,
        market: str,
        payload: Dict[str, object],
    ) -> Optional[Tuple[str, str, float, Dict[str, object]]]:
        change_percent: Optional[float] = None
        try:
            curve = await self.market_data_service.get_curve(symbol=symbol, market=market, window="1d")
            change_percent = calculate_window_change_percent(
                points=curve,
                window_minutes=self.config.news_listener.move_window_minutes,
            )
        except Exception:
            change_percent = None

        if change_percent is None:
            try:
                quote = await self.market_data_service.get_quote(symbol=symbol, market=market)
                change_percent = quote.change_percent
            except Exception:
                change_percent = None

        if change_percent is None:
            return None
        return symbol, market, float(change_percent), payload

    async def _run_analysis(self, alerts: List[MatchedAlertCandidate], errors: List[str]) -> List[Dict[str, object]]:
        if not alerts:
            return []

        provider_id = self.config.news_listener.analysis_provider or self.config.analysis.default_provider
        model = self.config.news_listener.analysis_model or self.config.analysis.default_model
        payload = [item.model_dump(mode="python") for item in alerts]

        try:
            return await self.analysis_service.analyze_news_alert_batch(
                candidates=payload,
                provider_id=provider_id,
                model=model,
            )
        except Exception as exc:
            errors.append(f"analysis degraded: {exc}")
            fallback = []
            for item in alerts:
                fallback.append(
                    {
                        "severity": item.severity,
                        "summary": "模型不可用，已规则降级",
                        "markdown": (
                            f"### {item.symbol} 告警\n"
                            f"- 新闻：{item.news_title}\n"
                            f"- {item.move_window_minutes}分钟涨跌幅：{item.price_change_percent:.2f}%\n"
                        ),
                    }
                )
            return fallback

    @staticmethod
    def _to_alert_view(row) -> NewsAlertView:
        try:
            parsed = json.loads(row.analysis_json or "{}")
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception:
            parsed = {}
        return NewsAlertView(
            id=row.id,
            run_id=row.run_id,
            symbol=row.symbol,
            market=row.market,
            news_title=row.news_title,
            news_link=row.news_link or "",
            news_source=row.news_source or "",
            published_at=row.published_at or "",
            move_window_minutes=row.move_window_minutes,
            price_change_percent=row.price_change_percent,
            threshold_percent=row.threshold_percent,
            severity=row.severity,
            analysis_summary=row.analysis_summary,
            analysis_markdown=row.analysis_markdown,
            analysis_json=parsed,
            status=row.status,
            created_at=row.created_at,
        )
