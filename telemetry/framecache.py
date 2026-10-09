"""Memoise pure per-session computations on the session DataFrame object they were given."""

from __future__ import annotations

import copy
import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar

import pandas as pd

F = TypeVar("F", bound=Callable[..., Any])
_REGISTRY: list[Callable[[], None]] = []


def per_frame(maxsize: int = 6) -> Callable[[F], F]:
    """
    Cache `fn(df, *args, **kwargs)` per DataFrame object (identity + length) and hashable args.

    The UI keeps one frame per session for the whole app run (st.cache_resource), and many
    tabs ask the same question of it several times per rerun. Results are deep-copied on the
    way out so callers can still modify what they get.
    """

    def deco(fn: F) -> F:
        cache: list[tuple[pd.DataFrame, int, Any, Any]] = []
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(df: pd.DataFrame, *args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            try:
                hash(key)
            except TypeError:
                return fn(df, *args, **kwargs)
            with lock:
                for frame, n, k, result in cache:
                    if frame is df and n == len(df) and k == key:
                        return copy.deepcopy(result)
            result = fn(df, *args, **kwargs)
            with lock:
                cache.insert(0, (df, len(df), key, result))
                del cache[maxsize:]
            return copy.deepcopy(result)

        def cache_clear() -> None:
            with lock:
                cache.clear()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        _REGISTRY.append(cache_clear)
        return wrapper  # type: ignore[return-value]

    return deco


def clear_all() -> None:
    for clear in _REGISTRY:
        clear()
