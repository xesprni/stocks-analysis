"""Shared error handling utilities for API routers."""

from __future__ import annotations

import functools
from typing import Any, Callable, Coroutine, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def service_error_handler(
    *,
    value_error_status: int = 400,
    not_found_status: int = 404,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, T]]],
    Callable[..., Coroutine[Any, Any, T]],
]:
    """Decorator that maps common service exceptions to HTTPException."""

    def decorator(
        fn: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await fn(*args, **kwargs)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=not_found_status, detail=str(exc)
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status_code=value_error_status, detail=str(exc)
                ) from exc

        return wrapper

    return decorator


def raise_not_found(detail: str) -> None:
    raise HTTPException(status_code=404, detail=detail)


def raise_bad_request(detail: str) -> None:
    raise HTTPException(status_code=400, detail=detail)
