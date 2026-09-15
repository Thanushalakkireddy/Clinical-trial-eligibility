"""SQLAlchemy 2.0 ORM models for the optional persistence layer.

Models are intentionally generic (no PostgreSQL-specific types) so the same
schema works for production PostgreSQL and isolated SQLite test databases.

Tables are only created when DATABASE_URL is configured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


# ---------------------------------------------------------------------------
# Protocol record
# ---------------------------------------------------------------------------

class ProtocolRecord(Base):
    """Persistent record of a clinical trial protocol and its extracted criteria."""

    __tablename__ = "clinical_trial_protocols"

    trial_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    protocol_metadata: Mapped[Optional[dict]] = mapped_column(Text, nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    criteria: Mapped[Optional[list]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Patient profile record
# ---------------------------------------------------------------------------

class PatientRecord(Base):
    """Persistent record of a normalized patient profile."""

    __tablename__ = "patient_profiles"

    patient_profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Assessment run record
# ---------------------------------------------------------------------------

class AssessmentRecord(Base):
    """Persistent record of one eligibility assessment run."""

    __tablename__ = "assessment_runs"

    assessment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trial_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_profile_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reference_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    workflow_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True, default="RUNNING")
    final_decision: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    warnings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Assessment trace record
# ---------------------------------------------------------------------------

class AssessmentTraceRecord(Base):
    """Immutable per-stage audit line for an assessment run."""

    __tablename__ = "assessment_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
