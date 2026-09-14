"""Alembic migration environment.

Supports both synchronous connection strings (psycopg2) and async drivers
(``postgresql+asyncpg``, ``sqlite+aiosqlite``). The target URL comes from
the application settings (``DATABASE_URL``); running a migration without it
available raises a clear error instead of silently generating a null URL.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import the application settings and registered metadata so migrations see
# every table. The model module import keeps the mapper config in sync.
from app.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database import models as _models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = settings.database_url
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. Set it before running Alembic, e.g.:\n"
        '  .\\scripts\\set-env.ps1  # or\n'
        "  set DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE\n"
    )

# Use ?safe URL escaping for % in passwords.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode. Supports async drivers when configured."""
    scheme = DATABASE_URL.split(":", 1)[0]
    if scheme in {"postgresql+asyncpg", "sqlite+aiosqlite"}:
        asyncio.run(run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()