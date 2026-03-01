"""Report routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.api.deps import get_effective_user_id, get_report_service
from market_reporter.modules.reports.service import ReportService
from market_reporter.schemas import (
    ReportRunDetail,
    ReportRunSummary,
    ReportRunTaskView,
    RunRequest,
    RunResult,
)

router = APIRouter(prefix="/api", tags=["reports"])


@router.post("/reports/run", response_model=RunResult)
async def run_report(
    payload: Optional[RunRequest] = None,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> RunResult:
    try:
        return await report_service.run_report(
            overrides=payload,
            user_id=get_effective_user_id(user),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reports/run/async", response_model=ReportRunTaskView)
async def run_report_async(
    payload: Optional[RunRequest] = None,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> ReportRunTaskView:
    return await report_service.start_report_async(
        overrides=payload,
        user_id=get_effective_user_id(user),
    )


@router.get("/reports/tasks", response_model=List[ReportRunTaskView])
async def list_report_tasks(
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> List[ReportRunTaskView]:
    return await report_service.list_report_tasks(
        user_id=get_effective_user_id(user),
    )


@router.get("/reports/tasks/{task_id}", response_model=ReportRunTaskView)
async def get_report_task(
    task_id: str,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> ReportRunTaskView:
    try:
        return await report_service.get_report_task(
            task_id=task_id,
            user_id=get_effective_user_id(user),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports", response_model=List[ReportRunSummary])
async def list_reports(
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> List[ReportRunSummary]:
    return report_service.list_reports(user_id=get_effective_user_id(user))


@router.get("/reports/{run_id}", response_model=ReportRunDetail)
async def get_report(
    run_id: str,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> ReportRunDetail:
    try:
        return report_service.get_report(
            run_id=run_id,
            user_id=get_effective_user_id(user),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/reports/{run_id}")
async def delete_report(
    run_id: str,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> dict:
    try:
        deleted = report_service.delete_report(
            run_id=run_id,
            user_id=get_effective_user_id(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@router.get("/reports/{run_id}/markdown", response_class=PlainTextResponse)
async def get_report_markdown(
    run_id: str,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> str:
    try:
        return report_service.get_report(
            run_id=run_id,
            user_id=get_effective_user_id(user),
        ).report_markdown
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
