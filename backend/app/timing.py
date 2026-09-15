"""Safe, zero-PHI stage timing helpers for workflow diagnostics.

Logs only stage names, elapsed milliseconds, success/failure flags, and
caller-supplied safe identifiers (e.g. trial_id). Never logs patient clinical
content, protocol text, credentials, or database URLs.
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger("app.timing")

T = TypeVar("T")


def log_stage(stage: str, ms: float, *, ok: bool = True, detail: str = "") -> None:
    """Record a single timing line for a workflow/agent stage."""
    note = f" detail={detail}" if detail else ""
    if ok:
        logger.info("[wf-timing] stage=%s ms=%.1f ok=True%s", stage, ms, note)
    else:
        logger.warning("[wf-timing] stage=%s ms=%.1f ok=False%s", stage, ms, note)


async def timed_async(stage: str, awaited: Awaitable[T], detail: str = "") -> T:
    """Time an awaited coroutine and log the elapsed duration."""
    start = time.perf_counter()
    try:
        result = await awaited
        log_stage(stage, (time.perf_counter() - start) * 1000.0, ok=True, detail=detail)
        return result
    except Exception:
        log_stage(stage, (time.perf_counter() - start) * 1000.0, ok=False, detail=detail)
        raise


def timed_sync(stage: str, fn: Callable[[], T], detail: str = "") -> T:
    """Time a synchronous callable and log the elapsed duration."""
    start = time.perf_counter()
    try:
        result = fn()
        log_stage(stage, (time.perf_counter() - start) * 1000.0, ok=True, detail=detail)
        return result
    except Exception:
        log_stage(stage, (time.perf_counter() - start) * 1000.0, ok=False, detail=detail)
        raise


class _StageTimer:
    """Context-manager style timer returning elapsed ms on exit."""

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0


def start_timer() -> _StageTimer:
    """Return a lightweight monotonic timer for manual start/end capture."""
    return _StageTimer()


def log_node(node_name: str) -> Callable[[Any], Any]:
    """Decorator timing a LangGraph async node method.

    Tracks total elapsed wall time and success (a node that returns a state
    dict without an ``errors`` key is treated as success). Only logs the node
    name and duration — never clinical or protocol content.
    """

    def _decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                timer = start_timer()
                try:
                    result = await fn(*args, **kwargs)
                except Exception:
                    log_stage(f"node.{node_name}", timer.elapsed_ms(), ok=False)
                    raise
                ok = not (isinstance(result, dict) and result.get("errors"))
                log_stage(f"node.{node_name}", timer.elapsed_ms(), ok=ok)
                return result

            return _async_wrapper

        @functools.wraps(fn)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            timer = start_timer()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                log_stage(f"node.{node_name}", timer.elapsed_ms(), ok=False)
                raise
            ok = not (isinstance(result, dict) and result.get("errors"))
            log_stage(f"node.{node_name}", timer.elapsed_ms(), ok=ok)
            return result

        return _sync_wrapper

    return _decorator