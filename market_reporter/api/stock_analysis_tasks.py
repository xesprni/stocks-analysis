"""In-memory stock analysis task management service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis_engine.schemas import (
    StockAnalysisRunRequest,
    StockAnalysisRunView,
    StockAnalysisTaskStatus,
    StockAnalysisTaskView,
)
from market_reporter.modules.analysis_engine.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.services.config_store import ConfigStore


class StockAnalysisTaskManager:
    """Manages in-memory background stock analysis tasks."""

    def __init__(self, config_store: ConfigStore) -> None:
        self._config_store = config_store
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, StockAnalysisTaskView] = {}
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
    ) -> StockAnalysisRunView:
        config = self._config_store.load()
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
                market_data_service=market_data_service,
                news_service=news_service,
                fund_flow_service=fund_flow_service,
            )
            return await analysis_service.run_stock_analysis(
                symbol=symbol,
                market=payload.market,
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

    async def _run_task(
        self,
        task_id: str,
        symbol: str,
        payload: StockAnalysisRunRequest,
    ) -> None:
        await self.update_task(
            task_id=task_id,
            status=StockAnalysisTaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            error_message=None,
        )
        try:
            result = await self._run_analysis_once(symbol=symbol, payload=payload)
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

        task_payload = payload.model_copy(deep=True)
        task = asyncio.create_task(
            self._run_task(
                task_id=task_id,
                symbol=symbol,
                payload=task_payload,
            )
        )
        self._handles[task_id] = task
        task.add_done_callback(lambda _: self._handles.pop(task_id, None))
        return task_view

    async def get_task(self, task_id: str) -> StockAnalysisTaskView:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise FileNotFoundError(f"Stock analysis task not found: {task_id}")
            return task

    async def list_tasks(self) -> list[StockAnalysisTaskView]:
        async with self._lock:
            tasks = list(self._tasks.values())
        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return tasks

    async def cancel_all(self) -> None:
        handles = list(self._handles.values())
        for handle in handles:
            if not handle.done():
                handle.cancel()
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)
