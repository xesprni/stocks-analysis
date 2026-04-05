"""Skills management routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from market_reporter.modules.analysis.agent.skill_catalog import (
    SkillCatalog,
    SkillCreateRequest,
    SkillDetailView,
    SkillUpdateRequest,
    SkillView,
)

router = APIRouter(prefix="/api", tags=["skills"])

_catalog = SkillCatalog.from_default_path()


def _get_catalog() -> SkillCatalog:
    return _catalog


@router.get("/skills", response_model=List[SkillView])
async def list_skills() -> List[SkillView]:
    catalog = _get_catalog()
    return [SkillView(name=s.name, description=s.description) for s in catalog.list_skills()]


@router.get("/skills/{name}", response_model=SkillDetailView)
async def get_skill(name: str) -> SkillDetailView:
    catalog = _get_catalog()
    summary = catalog.get_summary(name)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    full_content = catalog.load_skill_content(name)
    return SkillDetailView(
        name=summary.name,
        description=summary.description,
        content=full_content or "",
    )


@router.post("/skills", response_model=SkillDetailView, status_code=201)
async def create_skill(payload: SkillCreateRequest) -> SkillDetailView:
    catalog = _get_catalog()
    try:
        summary = catalog.create_skill(
            name=payload.name,
            description=payload.description,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    full_content = catalog.load_skill_content(summary.name)
    return SkillDetailView(
        name=summary.name,
        description=summary.description,
        content=full_content or "",
    )


@router.put("/skills/{name}", response_model=SkillDetailView)
async def update_skill(name: str, payload: SkillUpdateRequest) -> SkillDetailView:
    catalog = _get_catalog()
    try:
        summary = catalog.update_skill(
            name=name,
            description=payload.description,
            content=payload.content,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    full_content = catalog.load_skill_content(summary.name)
    return SkillDetailView(
        name=summary.name,
        description=summary.description,
        content=full_content or "",
    )


@router.delete("/skills/{name}")
async def delete_skill(name: str) -> dict:
    catalog = _get_catalog()
    deleted = catalog.delete_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    return {"deleted": True}


@router.post("/skills/reload")
async def reload_skills() -> dict:
    catalog = _get_catalog()
    catalog.reload()
    return {"reloaded": True, "count": len(catalog.list_skills())}
