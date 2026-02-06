from __future__ import annotations

from typing import Awaitable, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from market_reporter.config import AppConfig


class NewsListenerScheduler:
    JOB_ID = "watchlist_news_listener"

    def __init__(self, config: AppConfig, run_func: Callable[[], Awaitable[object]]) -> None:
        self.config = config
        self.run_func = run_func
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self) -> None:
        if not self.config.news_listener.enabled:
            return
        if self.scheduler is not None:
            return
        scheduler = AsyncIOScheduler(timezone=self.config.timezone)
        scheduler.add_job(
            self._safe_run,
            "interval",
            minutes=self.config.news_listener.interval_minutes,
            id=self.JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )
        scheduler.start()
        self.scheduler = scheduler

    async def trigger_now(self):
        return await self.run_func()

    async def _safe_run(self) -> None:
        try:
            await self.run_func()
        except Exception:
            return

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
