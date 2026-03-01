"""JWT authentication module with dual token support."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from market_reporter.infra.db.repos import UserRepo
from market_reporter.infra.db.session import session_scope, verify_password
from market_reporter.settings import AppSettings


router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    user_id: int
    username: str
    is_admin: bool
    is_active: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: CurrentUser


class RefreshRequest(BaseModel):
    refresh_token: str


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


def create_access_token(
    user_id: int,
    username: str,
    is_admin: bool,
    settings: AppSettings,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(
    user_id: int,
    settings: AppSettings,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str, settings: AppSettings) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_settings(request: Request) -> AppSettings:
    return getattr(request.app.state, "settings", AppSettings())


def _get_db_url(request: Request) -> str:
    return request.app.state.config_store.load().database.url


def verify_jwt_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    settings = _get_settings(request)

    if not settings.auth_enabled:
        return CurrentUser(
            user_id=0, username="anonymous", is_admin=True, is_active=True
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token, settings)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload.get("sub", 0))
    db_url = _get_db_url(request)

    with session_scope(db_url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return CurrentUser(
            user_id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            is_active=user.is_active,
        )


class AuthDependency:
    def __call__(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> CurrentUser:
        return verify_jwt_token(request, credentials)


auth_required = AuthDependency()


def require_user(
    request: Request,
    user: CurrentUser = Depends(auth_required),
) -> CurrentUser:
    settings = getattr(request.app.state, "settings", AppSettings())
    if not settings.auth_enabled:
        return user
    if user.user_id == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, payload: LoginRequest) -> TokenResponse:
    settings = _get_settings(request)
    db_url = _get_db_url(request)

    with session_scope(db_url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get_by_username(payload.username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
            )
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        user_repo.update_last_login(user)

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            settings=settings,
        )
        refresh_token = create_refresh_token(user_id=user.id, settings=settings)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=CurrentUser(
                user_id=user.id,
                username=user.username,
                is_admin=user.is_admin,
                is_active=user.is_active,
            ),
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, payload: RefreshRequest) -> TokenResponse:
    settings = _get_settings(request)
    db_url = _get_db_url(request)

    token_payload = decode_token(payload.refresh_token, settings)
    if token_payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = int(token_payload.get("sub", 0))

    with session_scope(db_url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            settings=settings,
        )
        new_refresh_token = create_refresh_token(user_id=user.id, settings=settings)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=CurrentUser(
                user_id=user.id,
                username=user.username,
                is_admin=user.is_admin,
                is_active=user.is_active,
            ),
        )


@router.get("/me", response_model=UserView)
async def get_current_user_info(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> UserView:
    db_url = _get_db_url(request)
    with session_scope(db_url) as session:
        user_repo = UserRepo(session)
        db_user = user_repo.get(user.user_id)
        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return UserView(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            display_name=db_user.display_name,
            is_admin=db_user.is_admin,
            is_active=db_user.is_active,
            last_login_at=db_user.last_login_at,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
        )


@router.post("/logout")
async def logout() -> dict:
    return {"message": "Logged out successfully"}
