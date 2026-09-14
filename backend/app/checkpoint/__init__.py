"""LangGraph persistent state / checkpointing.

Enables the LangGraph workflow to save and recover execution state through a
supported persistent checkpointer:

- ``DATABASE_URL`` with a PostgreSQL URL  -> ``AsyncPostgresSaver`` (psycopg v3)
- ``DATABASE_URL`` with a SQLite URL     -> ``AsyncSqliteSaver`` (aiosqlite)
- unset ``DATABASE_URL``                 -> checkpointing disabled

State is stored in the checkpointer's own ``checkpoints``/``writes`` tables in
the same database already used for assessment persistence, so no second
database is introduced. Checkpointers are created lazily on first use: no
connection is opened at module import time.
"""

from app.checkpoint.provider import (
    checkpoint_backend,
    checkpoint_is_available,
    dispose_checkpointer,
    get_langgraph_checkpointer,
)
from app.checkpoint.serializer import make_checkpoint_serializer

__all__ = [
    "checkpoint_backend",
    "checkpoint_is_available",
    "dispose_checkpointer",
    "get_langgraph_checkpointer",
    "make_checkpoint_serializer",
]