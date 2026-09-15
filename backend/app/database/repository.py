"""Repository (data access) layer for the optional persistence backend.

All functions take an async SQLAlchemy session explicitly so callers control
transaction boundaries and isolated test databases can be used. The repository
never raises domain-level eligibility errors: persistence errors bubble up as
plain exceptions that the workflow layer treats as non-fatal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AssessmentRecord,
    AssessmentTraceRecord,
    PatientRecord,
    ProtocolRecord,
)
from app.database.serialization import decode_json, encode_json


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

async def create_protocol(
    session: AsyncSession,
    trial_id: str,
    protocol_metadata: Optional[dict] = None,
    source_document: Optional[str] = None,
    source_page_count: Optional[int] = None,
    criteria: Optional[List[dict]] = None,
) -> ProtocolRecord:
    """Insert or update the protocol record for a trial (idempotent by trial_id)."""
    existing = await session.get(ProtocolRecord, trial_id)
    if existing is not None:
        if protocol_metadata is not None:
            existing_meta = decode_json(existing.protocol_metadata, default={}) or {}
            if isinstance(existing_meta, dict) and existing_meta.get("inclusion_criteria"):
                merged_meta = dict(existing_meta)
                if isinstance(protocol_metadata, dict):
                    for k, v in protocol_metadata.items():
                        if k not in merged_meta or not merged_meta[k]:
                            merged_meta[k] = v
                existing.protocol_metadata = encode_json(merged_meta)
            else:
                existing.protocol_metadata = encode_json(protocol_metadata)
        if source_document is not None:
            existing.source_document = source_document
        if source_page_count is not None:
            existing.source_page_count = source_page_count
        if criteria is not None:
            if criteria or not existing.criteria:
                existing.criteria = encode_json(criteria)
        record = existing
    else:
        record = ProtocolRecord(
            trial_id=trial_id,
            protocol_metadata=encode_json(protocol_metadata),
            source_document=source_document,
            source_page_count=source_page_count,
            criteria=encode_json(criteria),
        )
        session.add(record)
    await session.flush()
    return record


async def get_protocol(session: AsyncSession, trial_id: str) -> Optional[ProtocolRecord]:
    """Return the protocol record for a trial, or None."""
    return await session.get(ProtocolRecord, trial_id)


async def list_protocols(session: AsyncSession) -> Sequence[ProtocolRecord]:
    """Return all stored protocol records ordered by created_at desc (newest first)."""
    stmt = select(ProtocolRecord).order_by(ProtocolRecord.created_at.desc(), ProtocolRecord.trial_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

async def create_patient(
    session: AsyncSession,
    patient_profile_id: str,
    profile_json: Optional[dict] = None,
    source_type: Optional[str] = None,
    source_document: Optional[str] = None,
) -> PatientRecord:
    """Insert or update the patient profile record (idempotent by id)."""
    existing = await session.get(PatientRecord, patient_profile_id)
    if existing is not None:
        if profile_json is not None:
            existing.profile_json = encode_json(profile_json)
        if source_type is not None:
            existing.source_type = source_type
        if source_document is not None:
            existing.source_document = source_document
        record = existing
    else:
        record = PatientRecord(
            patient_profile_id=patient_profile_id,
            profile_json=encode_json(profile_json),
            source_type=source_type,
            source_document=source_document,
        )
        session.add(record)
    await session.flush()
    return record


async def get_patient(session: AsyncSession, patient_profile_id: str) -> Optional[PatientRecord]:
    """Return the patient profile record, or None."""
    return await session.get(PatientRecord, patient_profile_id)


async def list_patients(session: AsyncSession) -> Sequence[PatientRecord]:
    """Return all stored patient records ordered by created_at desc (newest first)."""
    stmt = select(PatientRecord).order_by(PatientRecord.created_at.desc(), PatientRecord.patient_profile_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

async def create_assessment(
    session: AsyncSession,
    assessment_id: str,
    trial_id: str,
    patient_profile_id: str,
    reference_date: Optional[str] = None,
) -> AssessmentRecord:
    """Create a new assessment run record in RUNNING state."""
    record = AssessmentRecord(
        assessment_id=assessment_id,
        trial_id=trial_id,
        patient_profile_id=patient_profile_id,
        reference_date=reference_date,
        workflow_status="RUNNING",
    )
    session.add(record)
    await session.flush()
    return record


async def update_assessment(
    session: AsyncSession,
    assessment_id: str,
    *,
    workflow_status: Optional[str] = None,
    final_decision: Optional[str] = None,
    current_step: Optional[str] = None,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
    snapshot: Optional[dict] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[AssessmentRecord]:
    """Update fields of an assessment record, returning it or None if not found."""
    record = await session.get(AssessmentRecord, assessment_id)
    if record is None:
        return None
    if workflow_status is not None:
        record.workflow_status = workflow_status
    if final_decision is not None:
        record.final_decision = final_decision
    if current_step is not None:
        record.current_step = current_step
    if warnings is not None:
        record.warnings_json = encode_json(list(warnings))
    if errors is not None:
        record.errors_json = encode_json(list(errors))
    if snapshot is not None:
        record.snapshot_json = encode_json(snapshot)
    if completed_at is not None:
        record.completed_at = completed_at
    await session.flush()
    return record


async def get_assessment(session: AsyncSession, assessment_id: str) -> Optional[AssessmentRecord]:
    """Return a single assessment record, or None."""
    return await session.get(AssessmentRecord, assessment_id)


async def list_assessments(
    session: AsyncSession,
    trial_id: Optional[str] = None,
    patient_profile_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[AssessmentRecord]:
    """Return assessment records, newest first, with optional filters."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    stmt = select(AssessmentRecord).order_by(AssessmentRecord.created_at.desc(), AssessmentRecord.assessment_id)
    if trial_id:
        stmt = stmt.where(AssessmentRecord.trial_id == trial_id)
    if patient_profile_id:
        stmt = stmt.where(AssessmentRecord.patient_profile_id == patient_profile_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Assessment traces
# ---------------------------------------------------------------------------

async def save_assessment_traces(
    session: AsyncSession,
    assessment_id: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Persist ordered per-stage audit trace lines for an assessment."""
    for index, entry in enumerate(entries, start=1):
        session.add(
            AssessmentTraceRecord(
                assessment_id=assessment_id,
                sequence=index,
                stage=entry.get("stage", "unknown"),
                status=entry.get("status"),
                payload_json=encode_json(entry.get("payload")),
            )
        )
    await session.flush()


async def get_assessment_traces(
    session: AsyncSession,
    assessment_id: str,
) -> Sequence[AssessmentTraceRecord]:
    """Return persisted trace lines for an assessment, in sequence order."""
    stmt = (
        select(AssessmentTraceRecord)
        .where(AssessmentTraceRecord.assessment_id == assessment_id)
        .order_by(AssessmentTraceRecord.sequence)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())