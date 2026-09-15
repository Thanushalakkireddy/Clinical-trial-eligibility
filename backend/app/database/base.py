"""SQLAlchemy declarative base and metadata for the optional persistence layer.

Persistence is opt-in: tables are only created/migrated when DATABASE_URL is set.
The base class intentionally carries no database-specific behavior so the same
models work on the production PostgreSQL database and isolated test databases.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all persistent ORM models."""