"""Minimal assessment persistence API (read-only).

Provides read access to persisted assessment runs and their audit traces.
Persistence is optional: when DATABASE_URL is not configured every endpoint
returns 503 (Service Unavailable) with a clear message rather than failing
silently.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import repository
from app.database.serialization import decode_json
from app.database.session import get_session_dependency, persist_is_configured
from app.schemas.assessment import (
    AssessmentDetailResponse,
    AssessmentSummaryResponse,
    AssessmentTraceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assessments", tags=["Assessment Persistence"])


def _require_persistence() -> None:
    if not persist_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment persistence is not configured. Set DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE to enable it.",
        )


def _record_to_summary(rec) -> AssessmentSummaryResponse:
    warnings: list = decode_json(rec.warnings_json, [])
    errors: list = decode_json(rec.errors_json, [])
    return AssessmentSummaryResponse(
        assessment_id=rec.assessment_id,
        trial_id=rec.trial_id,
        patient_profile_id=rec.patient_profile_id,
        reference_date=rec.reference_date,
        workflow_status=rec.workflow_status,
        final_decision=rec.final_decision,
        current_step=rec.current_step,
        created_at=rec.created_at,
        completed_at=rec.completed_at,
        has_errors=bool(errors),
        error_count=len(errors),
        warning_count=len(warnings),
    )


def _trace_to_response(t) -> AssessmentTraceResponse:
    return AssessmentTraceResponse(
        sequence=t.sequence,
        stage=t.stage,
        status=t.status,
        payload=decode_json(t.payload_json),
        created_at=t.created_at,
    )


@router.get(
    "",
    response_model=List[AssessmentSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List persisted assessment runs (newest first)",
)
async def list_assessments(
    trial_id: Optional[str] = Query(default=None, description="Filter by clinical trial ID"),
    patient_profile_id: Optional[str] = Query(default=None, description="Filter by patient profile ID"),
    limit: int = Query(default=20, ge=1, le=200, description="Maximum results to return"),
    offset: int = Query(default=0, ge=0, description="Skip the first N results"),
    _session: AsyncSession = Depends(get_session_dependency),
) -> List[AssessmentSummaryResponse]:
    _require_persistence()
    records = await repository.list_assessments(
        _session,
        trial_id=trial_id,
        patient_profile_id=patient_profile_id,
        limit=limit,
        offset=offset,
    )
    return [_record_to_summary(r) for r in records]


@router.get(
    "/{assessment_id}",
    response_model=AssessmentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a persisted assessment record with full audit trace",
)
async def get_assessment_detail(
    assessment_id: str,
    _session: AsyncSession = Depends(get_session_dependency),
) -> AssessmentDetailResponse:
    _require_persistence()
    rec = await repository.get_assessment(_session, assessment_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment '{assessment_id}' not found.",
        )
    traces = await repository.get_assessment_traces(_session, assessment_id)
    summary = _record_to_summary(rec)
    return AssessmentDetailResponse(
        assessment_id=summary.assessment_id,
        trial_id=summary.trial_id,
        patient_profile_id=summary.patient_profile_id,
        reference_date=summary.reference_date,
        workflow_status=summary.workflow_status,
        final_decision=summary.final_decision,
        current_step=summary.current_step,
        created_at=summary.created_at,
        completed_at=summary.completed_at,
        has_errors=summary.has_errors,
        error_count=summary.error_count,
        warning_count=summary.warning_count,
        warnings=decode_json(rec.warnings_json, []),
        errors=decode_json(rec.errors_json, []),
        snapshot=decode_json(rec.snapshot_json),
        traces=[_trace_to_response(t) for t in traces],
    )