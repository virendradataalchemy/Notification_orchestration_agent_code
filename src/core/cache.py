"""In-memory async cache with TTL support.

Usage:
    from src.core.cache import cached, invalidate_cache

    @cached("dashboard_data", ttl=300)
    async def _load_dashboard_data(): ...

    await invalidate_cache("dashboard_data")
"""

from __future__ import annotations

import time
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# {key: (value, expires_at)}
_store: dict[str, tuple[Any, float]] = {}


def _get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _store[key]
        return None
    return value


def _set(key: str, value: Any, ttl: int) -> None:
    _store[key] = (value, time.monotonic() + ttl)


async def invalidate_cache(*keys: str) -> None:
    for key in keys:
        _store.pop(key, None)


async def invalidate_pattern(pattern: str) -> None:
    """Remove all keys that start with the given prefix (strip trailing *)."""
    prefix = pattern.rstrip("*")
    for key in list(_store.keys()):
        if key.startswith(prefix):
            del _store[key]


def cached(key: str, ttl: int = 300):
    """Decorator that caches the return value of an async function.

    Args:
        key:  Cache key prefix.
        ttl:  Time-to-live in seconds (default 5 min).
    """
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if args or kwargs:
                arg_str = ":".join(str(a) for a in args)
                kwarg_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{key}:{arg_str}:{kwarg_str}".strip(":")
            else:
                cache_key = key

            hit = _get(cache_key)
            if hit is not None:
                logger.debug("Cache HIT  %s", cache_key)
                return hit

            logger.debug("Cache MISS %s", cache_key)
            result = await fn(*args, **kwargs)
            _set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
