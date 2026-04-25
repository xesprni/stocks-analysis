"""MCP Server configuration CRUD and connection test endpoints."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.api.deps import get_effective_user_id, get_user_config
from market_reporter.config import AppConfig
from market_reporter.infra.db.repos import McpServerConfigRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.modules.analysis.agent.tools.mcp_tool import McpManager
from market_reporter.modules.analysis.schemas import (
    McpConnectionTestResult,
    McpServerConfigCreate,
    McpServerConfigUpdate,
    McpServerConfigView,
)

router = APIRouter(prefix="/api", tags=["mcp"])


def _to_view(row) -> McpServerConfigView:
    try:
        config = json.loads(row.config_json) if row.config_json else {}
    except (json.JSONDecodeError, ValueError):
        config = {}
    return McpServerConfigView(
        id=row.id,
        server_name=row.server_name,
        transport_type=row.transport_type,
        config=config,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/mcp-configs", response_model=List[McpServerConfigView])
async def list_mcp_configs(
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> List[McpServerConfigView]:
    user_id = get_effective_user_id(user)
    with session_scope(config.database.url) as session:
        repo = McpServerConfigRepo(session)
        rows = repo.list_by_user(user_id=user_id)
        return [_to_view(row) for row in rows]


@router.post("/mcp-configs", response_model=McpServerConfigView)
async def create_mcp_config(
    payload: McpServerConfigCreate,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> McpServerConfigView:
    user_id = get_effective_user_id(user)
    config_json = json.dumps(payload.config, ensure_ascii=False)

    with session_scope(config.database.url) as session:
        repo = McpServerConfigRepo(session)
        try:
            row = repo.add(
                server_name=payload.server_name,
                transport_type=payload.transport_type,
                config_json=config_json,
                user_id=user_id,
            )
        except Exception as exc:
            if "uq_mcp_user_server" in str(exc).lower() or "unique" in str(exc).lower():
                raise HTTPException(
                    status_code=409,
                    detail=f"MCP server '{payload.server_name}' already exists.",
                ) from exc
            raise
        return _to_view(row)


@router.put("/mcp-configs/{config_id}", response_model=McpServerConfigView)
async def update_mcp_config(
    config_id: int,
    payload: McpServerConfigUpdate,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> McpServerConfigView:
    user_id = get_effective_user_id(user)
    with session_scope(config.database.url) as session:
        repo = McpServerConfigRepo(session)
        row = repo.get(config_id=config_id, user_id=user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="MCP config not found.")

        config_json = (
            json.dumps(payload.config, ensure_ascii=False)
            if payload.config is not None
            else None
        )
        updated = repo.update(
            row=row,
            server_name=payload.server_name,
            transport_type=payload.transport_type,
            config_json=config_json,
            enabled=payload.enabled,
        )
        return _to_view(updated)


@router.delete("/mcp-configs/{config_id}")
async def delete_mcp_config(
    config_id: int,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> dict:
    user_id = get_effective_user_id(user)
    with session_scope(config.database.url) as session:
        repo = McpServerConfigRepo(session)
        deleted = repo.delete(config_id=config_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="MCP config not found.")
        return {"deleted": True}


@router.post("/mcp-configs/{config_id}/test", response_model=McpConnectionTestResult)
async def test_mcp_config(
    config_id: int,
    config: AppConfig = Depends(get_user_config),
    user: CurrentUser = Depends(require_user),
) -> McpConnectionTestResult:
    user_id = get_effective_user_id(user)
    with session_scope(config.database.url) as session:
        repo = McpServerConfigRepo(session)
        row = repo.get(config_id=config_id, user_id=user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="MCP config not found.")
        server_name = row.server_name
        transport_type = row.transport_type
        try:
            mcp_config = json.loads(row.config_json) if row.config_json else {}
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid config JSON.")

    manager = McpManager()
    try:
        return await manager.test_connection(
            server_name=server_name,
            transport_type=transport_type,
            config=mcp_config,
        )
    finally:
        await manager.close_all()
