"""Optional workflow persistence service.

The workflow router calls these functions around LangGraph execution. Every
function is failure-safe: it raises on database problems and the router treats
the exception as a non-fatal warning. Eligibility logic never depends on
persistence succeeding, and an assessment_id is only ever returned after the
record has actually been created.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from app.database.repository import (
    create_assessment,
    create_patient,
    create_protocol,
    save_assessment_traces,
    update_assessment,
)
from app.database.serialization import (
    build_assessment_snapshot,
    mint_assessment_id,
    serialize_schema,
    serialize_evidence,
)
from app.database.session import get_session_maker, persist_is_configured
from app.schemas.rag import RetrievedChunk
from app.timing import timed_async

logger = logging.getLogger(__name__)


def persist_is_enabled() -> bool:
    """True when DATABASE_URL is configured and persistence will be attempted."""
    return persist_is_configured()


def _protocol_source(protocol_evidence: Optional[List[RetrievedChunk]]):
    chunks = protocol_evidence or []
    source_document = chunks[0].source_document if chunks else None
    page_count = None
    if chunks:
        page_count = len({c.source_page for c in chunks})
    criteria = [c.model_dump(mode="json") for c in chunks]
    return source_document, page_count, criteria


async def persist_assessment_start(
    trial_id: str,
    patient_profile,
    reference_date: Optional[str],
    protocol_evidence: Optional[List[RetrievedChunk]],
) -> Optional[str]:
    """Create the RUNNING assessment record (plus patient/protocol audit rows).

    Returns the newly created assessment_id, or None when persistence is
    disabled. Raises on any database failure (caller treats as non-fatal).
    """
    if not persist_is_enabled():
        return None

    patient_id = getattr(patient_profile, "patient_profile_id", None) or "UNKNOWN_PATIENT"
    source_document, page_count, criteria = _protocol_source(protocol_evidence)

    # Mint early so every persistence stage log can reference the id safely.
    assessment_id = mint_assessment_id()

    async with get_session_maker()() as session:
        await timed_async(
            "persistence.start.patient",
            create_patient(
                session,
                patient_profile_id=patient_id,
                profile_json=serialize_schema(patient_profile),
                source_type="api_request",
            ),
            detail=f"assessment={assessment_id or 'pending'}",
        )
        await timed_async(
            "persistence.start.protocol",
            create_protocol(
                session,
                trial_id=trial_id,
                protocol_metadata={
                    "source": "workflow_evaluate",
                    "evidence_chunk_count": len(protocol_evidence or []),
                },
                source_document=source_document,
                source_page_count=page_count,
                criteria=criteria,
            ),
            detail=f"trial={trial_id}",
        )
        await timed_async(
            "persistence.start.assessment",
            create_assessment(
                session,
                assessment_id=assessment_id,
                trial_id=trial_id,
                patient_profile_id=patient_id,
                reference_date=reference_date,
            ),
            detail=f"assessment={assessment_id}",
        )
        await timed_async(
            "persistence.start.commit",
            session.commit(),
            detail=f"assessment={assessment_id}",
        )
        return assessment_id


async def persist_assessment_complete(
    assessment_id: str,
    final_state: Dict[str, Any],
    reference_date: Optional[str],
) -> None:
    """Persist the final decision, all agent assessments, traces and snapshot."""
    if not persist_is_enabled():
        return

    errors = list(final_state.get("errors") or [])
    warnings = list(final_state.get("warnings") or [])
    workflow_status = "FAILED" if errors else "COMPLETED"

    decision = final_state.get("decision_assessment")
    final_decision = getattr(decision, "final_status", None)
    final_decision_value = final_decision.value if final_decision is not None else None

    current_step = final_state.get("current_step", "END")

    snapshot = build_assessment_snapshot(
        trial_id=final_state.get("trial_id", ""),
        patient_profile_id=final_state.get("patient_profile_id", ""),
        patient_profile=final_state.get("patient_profile"),
        reference_date=reference_date,
        protocol_evidence=final_state.get("protocol_evidence") or [],
        inclusion_assessment=final_state.get("inclusion_assessment"),
        exclusion_assessment=final_state.get("exclusion_assessment"),
        contradiction_assessment=final_state.get("contradiction_assessment"),
        decision_assessment=decision,
        warnings=warnings,
        errors=errors,
        current_step=current_step,
    )

    traces = [
        {
            "stage": "start",
            "status": "RUNNING",
            "payload": {
                "trial_id": final_state.get("trial_id", ""),
                "patient_profile_id": final_state.get("patient_profile_id", ""),
                "reference_date": reference_date,
            },
        },
        {
            "stage": "inclusion",
            "status": _short_status(final_state.get("inclusion_assessment")),
            "payload": serialize_schema(final_state.get("inclusion_assessment")),
        },
        {
            "stage": "exclusion",
            "status": _short_status(final_state.get("exclusion_assessment")),
            "payload": serialize_schema(final_state.get("exclusion_assessment")),
        },
        {
            "stage": "contradiction",
            "status": _short_status(final_state.get("contradiction_assessment")),
            "payload": serialize_schema(final_state.get("contradiction_assessment")),
        },
        {
            "stage": "decision",
            "status": final_decision_value,
            "payload": serialize_schema(decision),
        },
        {
            "stage": "complete",
            "status": workflow_status,
            "payload": {
                "current_step": current_step,
                "evidence": serialize_evidence(final_state.get("protocol_evidence") or []),
            },
        },
    ]

    async with get_session_maker()() as session:
        await timed_async(
            "persistence.complete.update",
            update_assessment(
                session,
                assessment_id,
                workflow_status=workflow_status,
                final_decision=final_decision_value,
                current_step=current_step,
                warnings=warnings,
                errors=errors,
                snapshot=snapshot,
                completed_at=datetime.now(UTC),
            ),
            detail=f"assessment={assessment_id}",
        )
        await timed_async(
            "persistence.complete.traces",
            save_assessment_traces(session, assessment_id, traces),
            detail=f"assessment={assessment_id}",
        )
        await timed_async(
            "persistence.complete.commit",
            session.commit(),
            detail=f"assessment={assessment_id}",
        )


async def persist_assessment_fail(
    assessment_id: str,
    error_messages: List[str],
) -> None:
    """Mark an in-flight assessment as FAILED after an execution error."""
    if not persist_is_enabled():
        return

    async with get_session_maker()() as session:
        await update_assessment(
            session,
            assessment_id,
            workflow_status="FAILED",
            current_step="error",
            errors=error_messages,
            warnings=None,
            completed_at=datetime.now(UTC),
        )
        await save_assessment_traces(
            session,
            assessment_id,
            [
                {
                    "stage": "failed",
                    "status": "FAILED",
                    "payload": {"errors": error_messages},
                }
            ],
        )
        await session.commit()


def _short_status(assessment: Optional[Any]) -> Optional[str]:
    """Extract a coarse status string for a trace line."""
    if assessment is None:
        return None
    overall = getattr(assessment, "overall_status", None)
    if overall is not None:
        return str(getattr(overall, "value", overall))
    has = getattr(assessment, "has_critical_findings", None)
    if has is not None:
        return "CRITICAL" if has else "OK"
    return None