"""User management routes."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from market_reporter.api.auth import CurrentUser, require_admin, require_user
from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import hash_password, session_scope
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings


router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: bool = False


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class UserView(BaseModel):
    id: int
    username: str
    email: Optional[str]
    display_name: Optional[str]
    is_admin: bool
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


def _get_db_url() -> str:
    settings = AppSettings()
    config_store = ConfigStore(config_path=settings.config_file)
    return config_store.load().database.url


def _to_user_view(user) -> UserView:
    return UserView(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=List[UserView])
async def list_users(
    admin: CurrentUser = Depends(require_admin),
) -> List[UserView]:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        users = user_repo.list_all(include_inactive=True)
        return [_to_user_view(u) for u in users]


@router.post("", response_model=UserView)
async def create_user(
    payload: CreateUserRequest,
    admin: CurrentUser = Depends(require_admin),
) -> UserView:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        existing = user_repo.get_by_username(payload.username)
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        password_hash = hash_password(payload.password)
        user = user_repo.create(
            username=payload.username,
            password_hash=password_hash,
            email=payload.email,
            display_name=payload.display_name,
            is_admin=payload.is_admin,
        )
        return _to_user_view(user)


@router.get("/me", response_model=UserView)
async def get_my_info(
    user: CurrentUser = Depends(require_user),
) -> UserView:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        db_user = user_repo.get(user.user_id)
        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return _to_user_view(db_user)


@router.get("/{user_id}", response_model=UserView)
async def get_user(
    user_id: int,
    admin: CurrentUser = Depends(require_admin),
) -> UserView:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return _to_user_view(user)


@router.put("/{user_id}", response_model=UserView)
async def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    admin: CurrentUser = Depends(require_admin),
) -> UserView:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user = user_repo.update(
            user=user,
            email=payload.email,
            display_name=payload.display_name,
            is_admin=payload.is_admin,
            is_active=payload.is_active,
        )
        return _to_user_view(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    if admin.user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        deleted = user_repo.delete(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return {"deleted": True}


@router.put("/me/password")
async def change_my_password(
    payload: ChangePasswordRequest,
    user: CurrentUser = Depends(require_user),
) -> dict:
    from market_reporter.infra.db.session import verify_password

    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        db_user = user_repo.get(user.user_id)
        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(payload.current_password, db_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        new_hash = hash_password(payload.new_password)
        user_repo.update_password(db_user, new_hash)
        return {"message": "Password changed successfully"}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    with session_scope(_get_db_url()) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        new_hash = hash_password(payload.new_password)
        user_repo.update_password(user, new_hash)
        return {"message": "Password reset successfully"}
