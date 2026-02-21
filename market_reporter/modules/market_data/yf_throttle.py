"""Shared Yahoo Finance rate-limiter.

Every call to the Yahoo Finance API anywhere in the application should go
through the helpers in this module so that we respect the platform's
rate-limit (~2 000 req/hour) and avoid ``YFRateLimitError``.

The module exposes:

* ``yf_throttle()`` – sleep until it is safe to make the next request.
* ``yf_ticker(symbol)`` – return a ``yf.Ticker`` guarded by the global
  semaphore + throttle.
* ``yf_call(fn, *a, **kw)`` – run an arbitrary callable inside the
  semaphore + throttle with automatic retry on rate-limit errors.
* Constants ``YF_SEMAPHORE``, ``YF_MAX_RETRIES``, ``YF_RETRY_BASE_DELAY``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level rate-limiter shared by *all* Yahoo Finance callers.
# At most 2 concurrent requests with a minimum 0.3 s gap between any two.
# ---------------------------------------------------------------------------
YF_SEMAPHORE = threading.Semaphore(2)
_YF_LOCK = threading.Lock()
_YF_LAST_REQUEST: float = 0.0
YF_MIN_INTERVAL: float = 0.3  # seconds between requests

YF_MAX_RETRIES: int = 3
YF_RETRY_BASE_DELAY: float = 2.0  # seconds; doubles on each retry

T = TypeVar("T")


def yf_throttle() -> None:
    """Block the calling thread until it is safe to make the next request."""
    global _YF_LAST_REQUEST
    with _YF_LOCK:
        now = time.monotonic()
        wait = YF_MIN_INTERVAL - (now - _YF_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _YF_LAST_REQUEST = time.monotonic()


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a Yahoo Finance rate-limit error."""
    name = type(exc).__name__
    if "RateLimit" in name or "TooManyRequests" in name:
        return True
    msg = str(exc).lower()
    return "too many requests" in msg or "rate limit" in msg


def yf_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Execute *fn* inside the global semaphore/throttle with retry logic.

    ``fn`` is called as ``fn(*args, **kwargs)``.  If it raises a rate-limit
    error, the call is retried up to ``YF_MAX_RETRIES`` times with
    exponential back-off.
    """
    last_exc: Exception | None = None
    for attempt in range(1, YF_MAX_RETRIES + 1):
        with YF_SEMAPHORE:
            yf_throttle()
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit_error(exc) and attempt < YF_MAX_RETRIES:
                    delay = YF_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "yf_call: rate-limited (attempt %d/%d), retrying in %.1fs – %s",
                        attempt,
                        YF_MAX_RETRIES,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    raise
    # Should never reach here, but satisfy the type checker.
    raise last_exc  # type: ignore[misc]


def yf_ticker(symbol: str) -> Any:
    """Return a ``yf.Ticker`` instance, throttled through the global limiter.

    Note: creating a ``Ticker`` object itself does *not* make an HTTP call
    in modern yfinance, but accessing its properties does.  This helper
    acquires the semaphore and enforces the inter-request gap so that the
    *first* property access is already rate-limited.
    """
    import yfinance as yf

    with YF_SEMAPHORE:
        yf_throttle()
        return yf.Ticker(symbol)
