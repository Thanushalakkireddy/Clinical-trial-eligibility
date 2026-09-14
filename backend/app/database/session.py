"""Optional async SQLAlchemy session management.

Persistence is entirely optional. When ``DATABASE_URL`` is not set:

- the application runs in its normal deterministic in-memory mode,
- no async engine is created,
- no database connection is ever attempted,
- eligibility logic is never altered.

When ``DATABASE_URL`` is set the engine/session factory are created lazily on
first use. All persistence failures are surfaced as non-fatal warnings upstream;
a database failure can never fabricate an assessment_id or change a decision.
"""

from __future__ import annotations

import logging
import threading
from typing import AsyncIterator, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.base import Base
from app.database import models  # noqa: F401  (register tables on the metadata)

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
# RLock because get_session_maker() legitimately calls get_engine() while the
# session factory lock is already held; a plain Lock self-deadlocks on the very
# first database operation and stalls every workflow request forever.
_lock = threading.RLock()

# Short connection timeout so an unavailable database fails fast instead of hanging.
_CONNECT_TIMEOUT_SECONDS = 5


def get_database_url() -> Optional[str]:
    """Return the currently configured database URL, or None when disabled.

    Prefers a URL installed via configure_database() (used by isolated local /
    test runtimes) and falls back to the DATABASE_URL environment/settings value.
    """
    if _engine is not None:
        return str(_engine.url)
    url = (settings.database_url or "").strip()
    return url or None


def redact_database_url(url: str) -> str:
    """Return a log-safe copy of a database URL with any password masked."""
    if not url:
        return url or "(empty)"
    scheme, _, rest = url.partition("://")
    if not rest or "/" not in rest:
        # e.g. sqlite file paths that do not carry credentials
        return url
    authority, _, path = rest.partition("/")
    if "@" in authority:
        userinfo, _, host = authority.rpartition("@")
        if ":" in userinfo:
            user, _, _ = userinfo.partition(":")
            authority = f"{user}:***@{host}"
            return f"{scheme}://{authority}/{path}"
    return url


def persist_is_configured() -> bool:
    """True when a DATABASE_URL is configured and persistence is enabled."""
    return get_database_url() is not None


def require_database_url() -> str:
    """Return the configured DATABASE_URL or raise a clear configuration error.

    Intentionally avoids returning credentials in exceptions.
    """
    url = get_database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE "
            "to enable persistence."
        )
    return url


def _normalize_database_url(url: str) -> str:
    """Map plain PostgreSQL URLs to the asyncpg driver URL used by the async engine.

    ``postgresql://`` is accepted by the checkpointer and runtime validation, so
    the async engine must accept it too instead of falling back to a sync driver.
    Non-PostgreSQL URLs pass through unchanged.
    """
    clean = (url or "").strip()
    if clean.startswith("postgresql://"):
        return clean.replace("postgresql://", "postgresql+asyncpg://", 1)
    if clean.startswith("postgres://"):
        return clean.replace("postgres://", "postgresql+asyncpg://", 1)
    return clean


def _engine_kwargs(url: str) -> dict:
    """Build create_async_engine kwargs for the target URL (never logs secrets)."""
    connect_args: dict = {}
    if url.startswith("postgresql+asyncpg://"):
        connect_args["timeout"] = _CONNECT_TIMEOUT_SECONDS
        command_timeout = settings.database_command_timeout_seconds
        if command_timeout and command_timeout > 0:
            # Bounds every asyncpg command (SELECT/INSERT/UPDATE, flush, and
            # commit round-trips) so a stalled transaction cannot hang a request
            # indefinitely. Per-command, not a blanket wrapper timeout.
            connect_args["command_timeout"] = command_timeout
    return {"pool_pre_ping": True, "connect_args": connect_args}


def configure_database(url: Optional[str]) -> None:
    """(Re)configure the global engine/session factory.

    Passing None or an empty string disables persistence and clears any prior
    engine. Used by the application at first use and by tests to install an
    isolated database.
    """
    global _engine, _session_maker
    with _lock:
        if _engine is not None:
            try:
                _engine.sync_engine.dispose()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Best-effort engine dispose failed during reconfigure.")
            _engine = None
            _session_maker = None

        clean_url = _normalize_database_url(url or "")
        if not clean_url:
            return

        _engine = create_async_engine(clean_url, **_engine_kwargs(clean_url))
        _session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info(
            "Assessment persistence enabled: %s",
            redact_database_url(clean_url),
        )


def dispose_database() -> None:
    """Clear the global engine/session factory, disposing pooled connections."""
    global _engine, _session_maker
    with _lock:
        if _engine is not None:
            try:
                _engine.sync_engine.dispose()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Best-effort engine dispose failed.")
            _engine = None
            _session_maker = None


def get_engine_url() -> Optional[str]:
    """Return the URL of the currently configured engine (redacted), if any."""
    if _engine is None:
        return None
    return redact_database_url(str(_engine.url))


def get_engine() -> AsyncEngine:
    """Return the lazily-created global async engine, or raise if unconfigured."""
    if not persist_is_configured():
        raise RuntimeError("DATABASE_URL is not configured; persistence is disabled.")
    global _engine
    with _lock:
        if _engine is None:
            configure_database(get_database_url())
        if _engine is None:  # pragma: no cover - defensive
            raise RuntimeError("Unable to initialize database engine.")
        return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the lazily-created global session factory, or raise if unconfigured."""
    if not persist_is_configured():
        raise RuntimeError("DATABASE_URL is not configured; persistence is disabled.")
    global _session_maker
    with _lock:
        if _session_maker is None:
            get_engine()
        if _session_maker is None:  # pragma: no cover - defensive
            raise RuntimeError("Unable to initialize database session factory.")
        return _session_maker


async def get_session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session.

    Returns 503 when persistence is not configured or the database is
    unreachable so callers can report availability clearly.
    """
    if not persist_is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Assessment persistence is not configured. "
                "Set DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE to enable it."
            ),
        )
    try:
        maker = get_session_maker()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Assessment persistence is not available.",
        ) from None
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_schema(session: Optional[AsyncSession] = None) -> None:
    """Create all tables (non-destructive) on the current engine.

    Intended for local development and isolated test databases. Production uses
    Alembic migrations instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_schema() -> None:
    """Drop all tables (destructive). Intended for isolated test databases only."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def ping_database() -> Tuple[bool, str]:
    """Return (reachable, detail) for the configured database."""
    try:
        async with get_session_maker()() as session:
            await session.execute(text("SELECT 1"))
        return True, "reachable"
    except Exception as err:
        return False, str(err)