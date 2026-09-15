"""FastAPI router for LangGraph multi-agent clinical trial eligibility workflow.

Endpoints:
- POST /api/v1/workflow/evaluate: Primary LangGraph execution endpoint returning WorkflowStateResponse.
- POST /api/v1/workflow/run: Legacy/convenience endpoint returning StructuredWorkflowState.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status

from app.checkpoint import get_langgraph_checkpointer
from app.config import settings
from app.database import persistence as db_persistence
from app.graph.workflow import run_workflow
from app.timing import log_stage, start_timer
from app.schemas.contradiction import ContradictionAssessment
from app.schemas.exclusion import ExclusionAssessment, ExclusionStatus
from app.schemas.inclusion import InclusionAssessment, InclusionStatus
from app.schemas.rag import RetrievedChunk
from app.schemas.workflow import (
    RunWorkflowRequest,
    StructuredWorkflowState,
    WorkflowEvaluateRequest,
    WorkflowStage,
    WorkflowStateResponse,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["Eligibility Workflow"])


def _workflow_timeout() -> float:
    """Bounded total deadline for one evaluate request (seconds)."""
    t = settings.workflow_timeout_seconds
    return float(t) if t and t > 0 else 180.0


def _db_step_timeout() -> float:
    """Bounded deadline for a single persistence step (seconds).

    Kept well below the total workflow deadline so a stalled ``commit()`` or
    checkpointer flush can never starve the whole request.
    """
    return max(1.0, min(_workflow_timeout(), 60.0))


@router.post(
    "/evaluate",
    response_model=WorkflowStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute LangGraph multi-agent eligibility evaluation",
)
async def evaluate_workflow(
    request: WorkflowEvaluateRequest,
) -> WorkflowStateResponse:
    """Executes the real LangGraph multi-agent orchestration workflow.

    Sequential stages:
    1. Validate Input (trial isolation, profile structure, dates)
    2. Protocol Retrieval (scoped strictly to selected trial)
    3. Inclusion Matching (InclusionMatchingAgent)
    4. Exclusion Detection (ExclusionDetectionAgent)
    5. Contradiction Analysis (ContradictionAgent)
    """
    clean_trial_id = (request.trial_id or "").strip()
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    log_stage("request.entry", 0.0, ok=True, detail=f"trial={clean_trial_id}")
    request_timer = start_timer()

    assessment_id: Optional[str] = None
    extra_warnings: List[str] = []

    if db_persistence.persist_is_enabled():
        try:
            assessment_id = await asyncio.wait_for(
                db_persistence.persist_assessment_start(
                    trial_id=clean_trial_id,
                    patient_profile=request.patient_profile,
                    reference_date=request.reference_date,
                    protocol_evidence=request.protocol_evidence,
                ),
                timeout=_db_step_timeout(),
            )
            log_stage(
                "assessment.persistence.start",
                request_timer.elapsed_ms(),
                ok=assessment_id is not None,
                detail=f"trial={clean_trial_id} assessment={assessment_id or 'none'}",
            )
        except Exception as persist_err:
            log_stage(
                "assessment.persistence.start",
                request_timer.elapsed_ms(),
                ok=False,
                detail=f"trial={clean_trial_id} error={type(persist_err).__name__}",
            )
            logger.warning(
                "Assessment persistence unavailable (start phase): %s",
                persist_err,
            )
            assessment_id = None

    # Persistent LangGraph checkpointing: only enabled together with a real
    # assessment_id (whose value doubles as the LangGraph thread_id). If the
    # checkpointer cannot be configured, degrade to the deterministic run.
    checkpointer = None
    if assessment_id is not None:
        try:
            checkpointer_timer = start_timer()
            checkpointer = await asyncio.wait_for(
                get_langgraph_checkpointer(),
                timeout=_workflow_timeout(),
            )
            log_stage(
                "checkpointer.acquire",
                checkpointer_timer.elapsed_ms(),
                ok=checkpointer is not None,
                detail=f"trial={clean_trial_id} assessment={assessment_id}",
            )
            if checkpointer is None:
                logger.warning(
                    "LangGraph checkpointing unavailable for the configured database backend."
                )
                extra_warnings.append(
                    "LangGraph checkpointing is not available for the configured database."
                )
        except Exception as checkpoint_err:
            log_stage(
                "checkpointer.acquire",
                checkpointer_timer.elapsed_ms(),
                ok=False,
                detail=f"trial={clean_trial_id} error={type(checkpoint_err).__name__}",
            )
            logger.warning(
                "LangGraph checkpointing could not be configured: %s",
                checkpoint_err,
            )
            extra_warnings.append(
                "LangGraph checkpointing could not be configured; running without persistent state."
            )
            checkpointer = None

    try:
        workflow_timer = start_timer()
        final_state = await asyncio.wait_for(
            run_workflow(
                state_or_trial_id=clean_trial_id,
                patient_profile=request.patient_profile,
                reference_date=request.reference_date,
                protocol_evidence=request.protocol_evidence,
                checkpointer=checkpointer,
                thread_id=assessment_id,
            ),
            timeout=_workflow_timeout(),
        )
        log_stage(
            "workflow.run",
            workflow_timer.elapsed_ms(),
            ok=True,
            detail=f"trial={clean_trial_id} assessment={assessment_id or 'none'}",
        )
        log_stage(
            "workflow.complete",
            workflow_timer.elapsed_ms(),
            ok=True,
            detail=f"trial={clean_trial_id} assessment={assessment_id or 'none'}",
        )
    except asyncio.TimeoutError as err:
        log_stage(
            "workflow.run",
            workflow_timer.elapsed_ms(),
            ok=False,
            detail=f"trial={clean_trial_id} error=Timeout({_workflow_timeout()}s)",
        )
        if assessment_id is not None:
            try:
                await asyncio.wait_for(
                    db_persistence.persist_assessment_fail(
                        assessment_id,
                        [f"Workflow evaluation timed out after {_workflow_timeout()} seconds"],
                    ),
                    timeout=_db_step_timeout(),
                )
            except Exception:
                logger.debug("Best-effort assessment failure recording skipped.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Workflow evaluation timed out after "
                f"{_workflow_timeout()} seconds. No single operation may hang indefinitely."
            ),
        ) from err
    except ValueError as err:
        log_stage(
            "workflow.run",
            workflow_timer.elapsed_ms(),
            ok=False,
            detail=f"trial={clean_trial_id} error={type(err).__name__}",
        )
        if assessment_id is not None:
            try:
                await asyncio.wait_for(
                    db_persistence.persist_assessment_fail(
                        assessment_id,
                        [f"Validation failure: {err}"],
                    ),
                    timeout=_db_step_timeout(),
                )
            except Exception:
                logger.debug("Best-effort assessment failure recording skipped.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        log_stage(
            "workflow.run",
            workflow_timer.elapsed_ms(),
            ok=False,
            detail=f"trial={clean_trial_id} error={type(err).__name__}",
        )
        if assessment_id is not None:
            try:
                await asyncio.wait_for(
                    db_persistence.persist_assessment_fail(
                        assessment_id,
                        [f"Workflow execution failure: {err}"],
                    ),
                    timeout=_db_step_timeout(),
                )
            except Exception:
                logger.debug("Best-effort assessment failure recording skipped.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during workflow evaluation.",
        ) from err

    # Post-run persistence (non-fatal — never alters the workflow response)
    if assessment_id is not None:
        persist_complete_timer = start_timer()
        try:
            await asyncio.wait_for(
                db_persistence.persist_assessment_complete(
                    assessment_id,
                    final_state,
                    reference_date=request.reference_date,
                ),
                timeout=_db_step_timeout(),
            )
            log_stage(
                "assessment.persistence.complete",
                persist_complete_timer.elapsed_ms(),
                ok=True,
                detail=f"trial={clean_trial_id} assessment={assessment_id}",
            )
        except Exception as persist_err:
            log_stage(
                "assessment.persistence.complete",
                persist_complete_timer.elapsed_ms(),
                ok=False,
                detail=f"trial={clean_trial_id} assessment={assessment_id} error={type(persist_err).__name__}",
            )
            logger.warning(
                "Assessment persistence update failed for %s: %s",
                assessment_id,
                persist_err,
            )
            extra_warnings.append(
                "Assessment record was created but could not be completed: "
                "the database update failed."
            )

    warnings = list(final_state.get("warnings") or []) + extra_warnings

    log_stage(
        "request.complete",
        request_timer.elapsed_ms(),
        ok=True,
        detail=f"trial={clean_trial_id} assessment={assessment_id or 'none'}",
    )

    return WorkflowStateResponse(
        assessment_id=assessment_id,
        trial_id=final_state.get("trial_id", clean_trial_id),
        patient_profile_id=final_state.get(
            "patient_profile_id", request.patient_profile.patient_profile_id
        ),
        protocol_evidence=final_state.get("protocol_evidence", []),
        inclusion_assessment=final_state.get("inclusion_assessment"),
        exclusion_assessment=final_state.get("exclusion_assessment"),
        contradiction_assessment=final_state.get("contradiction_assessment"),
        decision_assessment=final_state.get("decision_assessment"),
        warnings=warnings,
        errors=final_state.get("errors", []),
        current_step=final_state.get("current_step", "END"),
    )


@router.post(
    "/run",
    response_model=StructuredWorkflowState,
    status_code=status.HTTP_200_OK,
    summary="Execute eligibility workflow with backwards-compatible state wrapper",
)
async def run_legacy_workflow(
    request: RunWorkflowRequest,
) -> StructuredWorkflowState:
    """Executes the LangGraph workflow and packages into StructuredWorkflowState."""
    clean_trial_id = (request.trial_id or "").strip()
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    try:
        final_state = await run_workflow(
            state_or_trial_id=clean_trial_id,
            patient_profile=request.patient_profile,
            reference_date=request.reference_date,
            protocol_evidence=request.protocol_evidence,
        )

        evidence = final_state.get("protocol_evidence", [])
        inc_evidence = [
            c for c in evidence if (c.criterion_type or "").lower() == "inclusion"
        ]
        exc_evidence = [
            c for c in evidence if (c.criterion_type or "").lower() == "exclusion"
        ]
        errors = final_state.get("errors", [])
        warnings = final_state.get("warnings", [])

        inc_assessment = final_state.get("inclusion_assessment")
        exc_assessment = final_state.get("exclusion_assessment")
        contra_assessment = final_state.get("contradiction_assessment")

        is_failed = bool(errors)
        status_val = WorkflowStatus.FAILED if is_failed else WorkflowStatus.COMPLETED

        return StructuredWorkflowState(
            trial_id=final_state.get("trial_id", clean_trial_id),
            patient_profile_id=final_state.get(
                "patient_profile_id", request.patient_profile.patient_profile_id
            ),
            status=status_val,
            current_stage=WorkflowStage.COMPLETED if not is_failed else WorkflowStage.FAILED,
            patient_profile=request.patient_profile,
            retrieved_evidence=evidence,
            inclusion_evidence=inc_evidence,
            exclusion_evidence=exc_evidence,
            inclusion_assessment=inc_assessment,
            exclusion_assessment=exc_assessment,
            contradiction_assessment=contra_assessment,
            decision_assessment=final_state.get("decision_assessment"),
            errors=errors,
            warnings=warnings,
            summary={
                "total_criteria": len(evidence),
                "inclusion_criteria": len(inc_evidence),
                "exclusion_criteria": len(exc_evidence),
                "has_errors": bool(errors),
            },
        )
    except Exception as err:
        logger.error("Error in run_legacy_workflow: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during workflow evaluation.",
        ) from err
