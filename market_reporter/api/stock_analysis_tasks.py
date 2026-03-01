"""In-memory stock analysis task management service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis.schemas import (
    StockAnalysisRunRequest,
    StockAnalysisRunView,
    StockAnalysisTaskStatus,
    StockAnalysisTaskView,
)
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.user_config_store import UserConfigStore


class StockAnalysisTaskManager:
    """Manages in-memory background stock analysis tasks."""

    def __init__(self, config_store: ConfigStore) -> None:
        self._config_store = config_store
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, StockAnalysisTaskView] = {}
        self._task_user_ids: Dict[str, Optional[int]] = {}
        self._handles: Dict[str, asyncio.Task[None]] = {}

    async def update_task(
        self,
        task_id: str,
        status: StockAnalysisTaskStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        result: Optional[StockAnalysisRunView] = None,
        error_message: Optional[str] = None,
    ) -> None:
        async with self._lock:
            current = self._tasks.get(task_id)
            if current is None:
                return

            update_payload: dict = {
                "status": status,
                "error_message": error_message
                if error_message is not None
                else current.error_message,
            }
            if started_at is not None:
                update_payload["started_at"] = started_at
            if finished_at is not None:
                update_payload["finished_at"] = finished_at
            if result is not None:
                update_payload["result"] = result
            self._tasks[task_id] = current.model_copy(update=update_payload)

    async def _run_analysis_once(
        self,
        symbol: str,
        payload: StockAnalysisRunRequest,
        user_id: Optional[int] = None,
    ) -> StockAnalysisRunView:
        config = self._load_config(user_id=user_id)
        init_db(config.database.url)
        async with HttpClient(
            timeout_seconds=config.request_timeout_seconds,
            user_agent=config.user_agent,
        ) as client:
            registry = ProviderRegistry()
            news_service = NewsService(config=config, client=client, registry=registry)
            fund_flow_service = FundFlowService(
                config=config, client=client, registry=registry
            )
            market_data_service = MarketDataService(config=config, registry=registry)
            analysis_service = AnalysisService(
                config=config,
                registry=registry,
                user_id=user_id,
                market_data_service=market_data_service,
                news_service=news_service,
                fund_flow_service=fund_flow_service,
            )
            return await analysis_service.run_stock_analysis(
                symbol=symbol,
                market=payload.market,
                skill_id=payload.skill_id,
                provider_id=payload.provider_id,
                model=payload.model,
                interval=payload.interval,
                lookback_bars=payload.lookback_bars,
                question=payload.question,
                peer_list=payload.peer_list,
                indicators=payload.indicators,
                news_from=payload.news_from,
                news_to=payload.news_to,
                filing_from=payload.filing_from,
                filing_to=payload.filing_to,
                timeframes=payload.timeframes,
                indicator_profile=payload.indicator_profile,
            )

    def _load_config(self, user_id: Optional[int]) -> AppConfig:
        if user_id is None:
            return self._config_store.load(user_id=None)
        global_config = self._config_store.load(user_id=None)
        store = UserConfigStore(
            database_url=global_config.database.url,
            global_config_path=self._config_store.config_path,
            user_id=user_id,
        )
        if not store.has_user_config():
            store.init_from_global()
        return store.load()

    async def _run_task(
        self,
        task_id: str,
        symbol: str,
        payload: StockAnalysisRunRequest,
        user_id: Optional[int] = None,
    ) -> None:
        await self.update_task(
            task_id=task_id,
            status=StockAnalysisTaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            error_message=None,
        )
        try:
            result = await self._run_analysis_once(
                symbol=symbol,
                payload=payload,
                user_id=user_id,
            )
            await self.update_task(
                task_id=task_id,
                status=StockAnalysisTaskStatus.SUCCEEDED,
                finished_at=datetime.now(timezone.utc),
                result=result,
                error_message=None,
            )
        except Exception as exc:
            await self.update_task(
                task_id=task_id,
                status=StockAnalysisTaskStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )

    async def start_task(
        self,
        symbol: str,
        payload: StockAnalysisRunRequest,
        user_id: Optional[int] = None,
    ) -> StockAnalysisTaskView:
        task_id = uuid4().hex
        task_view = StockAnalysisTaskView(
            task_id=task_id,
            symbol=symbol.strip().upper(),
            market=payload.market.upper(),
            status=StockAnalysisTaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._tasks[task_id] = task_view
            self._task_user_ids[task_id] = user_id

        task_payload = payload.model_copy(deep=True)
        task = asyncio.create_task(
            self._run_task(
                task_id=task_id,
                symbol=symbol,
                payload=task_payload,
                user_id=user_id,
            )
        )
        self._handles[task_id] = task
        task.add_done_callback(lambda _: self._handles.pop(task_id, None))
        return task_view

    async def get_task(
        self,
        task_id: str,
        user_id: Optional[int] = None,
    ) -> StockAnalysisTaskView:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise FileNotFoundError(f"Stock analysis task not found: {task_id}")
            owner = self._task_user_ids.get(task_id)
            if owner != user_id:
                raise FileNotFoundError(f"Stock analysis task not found: {task_id}")
            return task

    async def list_tasks(
        self,
        user_id: Optional[int] = None,
    ) -> list[StockAnalysisTaskView]:
        async with self._lock:
            tasks = [
                task
                for task_id, task in self._tasks.items()
                if self._task_user_ids.get(task_id) == user_id
            ]
        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return tasks

    async def cancel_all(self) -> None:
        handles = list(self._handles.values())
        for handle in handles:
            if not handle.done():
                handle.cancel()
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)
