"""Stock analysis routes (run, async, tasks, history)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.api.deps import get_effective_user_id, get_user_config
from market_reporter.api.stock_analysis_tasks import StockAnalysisTaskManager
from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis.schemas import (
    StockAnalysisHistoryItem,
    StockAnalysisRunRequest,
    StockAnalysisRunView,
    StockAnalysisTaskView,
)
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService

router = APIRouter(prefix="/api", tags=["analysis"])


def _get_task_manager(request: Request) -> StockAnalysisTaskManager:
    return request.app.state.stock_analysis_task_manager


async def _run_stock_analysis_once(
    config: AppConfig,
    user_id: Optional[int],
    symbol: str,
    payload: StockAnalysisRunRequest,
) -> StockAnalysisRunView:
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


@router.post(
    "/analysis/stocks/{symbol}/run/async", response_model=StockAnalysisTaskView
)
async def run_stock_analysis_async(
    symbol: str,
    payload: StockAnalysisRunRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> StockAnalysisTaskView:
    task_manager = _get_task_manager(request)
    return await task_manager.start_task(
        symbol=symbol,
        payload=payload,
        user_id=get_effective_user_id(user),
    )


@router.get("/analysis/stocks/tasks/{task_id}", response_model=StockAnalysisTaskView)
async def stock_analysis_task(
    task_id: str,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> StockAnalysisTaskView:
    task_manager = _get_task_manager(request)
    try:
        return await task_manager.get_task(
            task_id=task_id,
            user_id=get_effective_user_id(user),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analysis/stocks/tasks", response_model=List[StockAnalysisTaskView])
async def list_stock_analysis_tasks(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> List[StockAnalysisTaskView]:
    task_manager = _get_task_manager(request)
    return await task_manager.list_tasks(user_id=get_effective_user_id(user))


@router.post("/analysis/stocks/{symbol}/run", response_model=StockAnalysisRunView)
async def run_stock_analysis(
    symbol: str,
    payload: StockAnalysisRunRequest,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> StockAnalysisRunView:
    try:
        return await _run_stock_analysis_once(
            config=config,
            user_id=get_effective_user_id(user),
            symbol=symbol,
            payload=payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/analysis/stocks/runs",
    response_model=List[StockAnalysisHistoryItem],
)
async def list_stock_analysis_runs(
    limit: int = Query(50, ge=1, le=200),
    symbol: Optional[str] = Query(None),
    market: Optional[str] = Query(None, pattern="^(CN|HK|US)$"),
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> List[StockAnalysisHistoryItem]:
    init_db(config.database.url)
    service = AnalysisService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    return service.list_recent_history(
        limit=limit,
        symbol=symbol,
        market=market,
    )


@router.get(
    "/analysis/stocks/runs/{run_id}",
    response_model=StockAnalysisHistoryItem,
)
async def get_stock_analysis_run(
    run_id: int,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> StockAnalysisHistoryItem:
    init_db(config.database.url)
    service = AnalysisService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    try:
        return service.get_history_item(run_id=run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/analysis/stocks/runs/{run_id}")
async def delete_stock_analysis_run(
    run_id: int,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> dict:
    init_db(config.database.url)
    service = AnalysisService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    deleted = service.delete_history_item(run_id=run_id)
    return {"deleted": deleted}


@router.get(
    "/analysis/stocks/{symbol}/history",
    response_model=List[StockAnalysisHistoryItem],
)
async def stock_analysis_history(
    symbol: str,
    market: str = Query(..., pattern="^(CN|HK|US)$"),
    limit: int = Query(20, ge=1, le=100),
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> List[StockAnalysisHistoryItem]:
    init_db(config.database.url)
    service = AnalysisService(
        config=config,
        registry=ProviderRegistry(),
        user_id=get_effective_user_id(user),
    )
    return service.list_history(symbol=symbol, market=market, limit=limit)
