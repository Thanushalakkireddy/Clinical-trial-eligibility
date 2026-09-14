"""Optional persistent database layer (PostgreSQL via SQLAlchemy async).

Persistence is opt-in via the ``DATABASE_URL`` environment variable. Without
it the application runs in its normal deterministic in-memory mode.
"""

from app.database.base import Base
from app.database.models import (
    AssessmentRecord,
    AssessmentTraceRecord,
    PatientRecord,
    ProtocolRecord,
)
from app.database import session
from app.database import repository
from app.database import serialization
from app.database import persistence

__all__ = [
    "Base",
    "AssessmentRecord",
    "AssessmentTraceRecord",
    "PatientRecord",
    "ProtocolRecord",
    "session",
    "repository",
    "serialization",
    "persistence",
]