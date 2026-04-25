"""Report routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import PlainTextResponse

from market_reporter.api.auth import CurrentUser, decode_token, require_user
from market_reporter.api.deps import get_effective_user_id, get_report_service
from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.reports.service import ReportService
from market_reporter.schemas import (
    ReportRunDetail,
    ReportRunSummary,
    ReportRunTaskView,
    ReportTaskStatus,
    RunRequest,
    RunResult,
)

router = APIRouter(prefix="/api", tags=["reports"])
ws_router = APIRouter(prefix="/api", tags=["reports"])


async def _resolve_websocket_user_id(websocket: WebSocket) -> Optional[int]:
    settings = websocket.app.state.settings
    if not settings.auth_enabled:
        return None

    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    try:
        payload = decode_token(token, settings)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    user_id = int(payload.get("sub", 0) or 0)
    db_url = websocket.app.state.config_store.load().database.url
    with session_scope(db_url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None or not user.is_active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        return user.id


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


@ws_router.websocket("/reports/tasks/{task_id}/ws")
async def report_task_websocket(
    task_id: str,
    websocket: WebSocket,
) -> None:
    user_id = await _resolve_websocket_user_id(websocket)
    if websocket.app.state.settings.auth_enabled and user_id is None:
        return

    report_service: ReportService = websocket.app.state.report_service
    try:
        queue = await report_service.subscribe_report_task(
            task_id=task_id,
            user_id=user_id,
        )
    except FileNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        while True:
            task = await queue.get()
            await websocket.send_json(task.model_dump(mode="json"))
            if task.status in {ReportTaskStatus.SUCCEEDED, ReportTaskStatus.FAILED}:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await report_service.unsubscribe_report_task(task_id, queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass


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


@router.post("/reports/tasks/{task_id}/save", response_model=ReportRunSummary)
async def save_report(
    task_id: str,
    report_service: ReportService = Depends(get_report_service),
    user: CurrentUser = Depends(require_user),
) -> ReportRunSummary:
    try:
        return await report_service.save_report(
            task_id=task_id,
            user_id=get_effective_user_id(user),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
