"""Lazy, optional LangGraph checkpointer provider.

The provider builds a persistent ``BaseCheckpointSaver`` from the existing
``DATABASE_URL`` the first time it is requested, and caches it for the lifetime
of the process. No database connection or module import side effect happens
until ``get_langgraph_checkpointer()`` is actually awaited.

Failure handling: if the checkpointer cannot be created/set up, the exception
propagates to the caller (the workflow endpoint), which degrades gracefully and
continues with the deterministic non-checkpointed execution.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.checkpoint.serializer import make_checkpoint_serializer
from app.config import settings
from app.database.session import get_database_url
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)

_saver: Optional[BaseCheckpointSaver] = None
_saver_url: Optional[str] = None
_sqlite_connection = None
_postgres_connection = None
_lock = threading.Lock()


def checkpoint_backend() -> Optional[str]:
    """Return the checkpointer backend for the configured URL, or None.

    - ``postgres``  -> ``AsyncPostgresSaver`` (psycopg v3 async)
    - ``sqlite``    -> ``AsyncSqliteSaver`` (aiosqlite)
    - ``None``      -> no DATABASE_URL, or an unsupported URL
    """
    url = get_database_url()
    if not url:
        return None
    if url.startswith("postgresql+asyncpg://") or url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    if url.startswith("sqlite+aiosqlite://") or url.startswith("sqlite://"):
        return "sqlite"
    return None


def checkpoint_is_available() -> bool:
    """True when persistent LangGraph checkpointing would be available.

    Reflects the configured URL backend only; the actual saver is still built
    lazily by ``get_langgraph_checkpointer()``.
    """
    return checkpoint_backend() is not None


def _sqlite_path(url: str) -> str:
    """Extract a SQLite file path (or ``:memory:``) from a SQLAlchemy-style URL."""
    rest = url.split("://", 1)[1] if "://" in url else url
    if not rest or rest in (":memory:", "/:memory:", "//:memory:"):
        return ":memory:"
    if rest.startswith("//"):
        return rest[1:]
    if rest.startswith("/"):
        # If followed by Windows drive letter like /C:/, strip leading slash
        if len(rest) > 3 and rest[1].isalpha() and rest[2] == ":":
            return rest[1:]
        return rest[1:]
    return rest


async def _build_saver(url: str) -> BaseCheckpointSaver:
    backend = checkpoint_backend()
    serde = make_checkpoint_serializer()
    build_timer = start_timer()

    if backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        dsn = url.replace("postgresql+asyncpg://", "postgresql://")
        connect_timeout_s = settings.checkpointer_connect_timeout_seconds
        setup_timeout_s = settings.checkpointer_setup_timeout_seconds

        connect_timer = start_timer()
        try:
            # psycopg's supported libpq connect_timeout bounds TCP/TLS/startup;
            # asyncio.wait_for is a belt-and-suspenders application deadline so a
            # stalled psycopg handshake can never leave the request Pending.
            conn = await asyncio.wait_for(
                AsyncConnection.connect(
                    dsn,
                    autocommit=True,
                    prepare_threshold=0,
                    row_factory=dict_row,
                    connect_timeout=connect_timeout_s,
                ),
                timeout=connect_timeout_s,
            )
            log_stage(
                "checkpoint.saver.connect",
                connect_timer.elapsed_ms(),
                ok=True,
                detail="backend=postgres",
            )
        except Exception:
            log_stage(
                "checkpoint.saver.connect",
                connect_timer.elapsed_ms(),
                ok=False,
                detail="backend=postgres",
            )
            raise

        global _postgres_connection
        try:
            saver = AsyncPostgresSaver(conn, serde=serde)
            setup_timer = start_timer()
            try:
                # setup() runs CREATE TABLE DDL (and may take advisory locks that
                # ignore statement_timeout), so bound it with an event-loop level
                # deadline instead of relying on a server-side statement timeout.
                await asyncio.wait_for(saver.setup(), timeout=setup_timeout_s)
                log_stage(
                    "checkpoint.saver.setup",
                    setup_timer.elapsed_ms(),
                    ok=True,
                    detail="backend=postgres",
                )
            except Exception:
                log_stage(
                    "checkpoint.saver.setup",
                    setup_timer.elapsed_ms(),
                    ok=False,
                    detail="backend=postgres",
                )
                raise
            _postgres_connection = conn
            log_stage(
                "checkpoint.saver.build",
                build_timer.elapsed_ms(),
                ok=True,
                detail="backend=postgres",
            )
            return saver
        except Exception:
            try:
                await conn.close()
            except Exception:
                pass
            log_stage(
                "checkpoint.saver.build",
                build_timer.elapsed_ms(),
                ok=False,
                detail="backend=postgres",
            )
            raise

    if backend == "sqlite":
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = await asyncio.wait_for(
            aiosqlite.connect(_sqlite_path(url)),
            timeout=max(1.0, settings.checkpointer_connect_timeout_seconds),
        )
        global _sqlite_connection
        try:
            saver = AsyncSqliteSaver(conn, serde=serde)
            setup_timer = start_timer()
            await saver.setup()
            log_stage("checkpoint.saver.setup", setup_timer.elapsed_ms(), ok=True, detail="backend=sqlite")
            _sqlite_connection = conn
            log_stage("checkpoint.saver.build", build_timer.elapsed_ms(), ok=True, detail="backend=sqlite")
            return saver
        except Exception:
            await conn.close()
            log_stage("checkpoint.saver.build", build_timer.elapsed_ms(), ok=False, detail="backend=sqlite")
            raise

    raise ValueError(f"Unsupported DATABASE_URL backend for checkpointing: {url}")


async def _close_saver() -> None:
    global _sqlite_connection, _postgres_connection, _saver, _saver_url
    with _lock:
        _saver = None
        _saver_url = None
        sqlite_connection = _sqlite_connection
        postgres_connection = _postgres_connection
        _sqlite_connection = None
        _postgres_connection = None
    for conn in (sqlite_connection, postgres_connection):
        if conn is None:
            continue
        try:
            await conn.close()
        except Exception:  # pragma: no cover - best effort cleanup
            logger.debug("Best-effort checkpointer connection close failed.")


async def get_langgraph_checkpointer() -> Optional[BaseCheckpointSaver]:
    """Return the lazily-created persistent checkpointer, or None when disabled.

    The saver is cached per configured URL. Safe for concurrent callers: if two
    tasks build a saver at the same time the losing one is closed and dropped.
    """
    url = get_database_url()
    if not url:
        return None

    global _saver, _saver_url
    with _lock:
        if _saver is not None and _saver_url == url:
            log_stage("checkpoint.saver.cache-hit", 0.0, ok=True)
            return _saver

    built = await _build_saver(url)

    with _lock:
        if _saver is not None and _saver_url == url:
            # Another caller already installed a saver for this URL; discard ours.
            if built is not _saver:
                closing = built
            else:
                closing = None
        else:
            _saver = built
            _saver_url = url
            closing = None

    if closing is not None:
        try:
            if getattr(closing, "conn", None) is not None:
                await closing.conn.close()
            elif hasattr(closing, "close"):
                await closing.close()
        except Exception:  # pragma: no cover - best effort cleanup
            logger.debug("Best-effort race-loser checkpointer close failed.")

    with _lock:
        return _saver


async def dispose_checkpointer() -> None:
    """Close the active checkpointer connection and drop the cached saver.

    Intended for tests and controlled shutdown; the next call to
    ``get_langgraph_checkpointer()`` rebuilds the saver lazily.
    """
    await _close_saver()