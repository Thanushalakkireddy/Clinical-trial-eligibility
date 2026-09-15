"""FastAPI router for Contradiction and Silent Exclusion Analysis.

Exposes POST /api/v1/contradiction/analyze to detect protocol contradictions,
patient fact discrepancies, assessment contradictions, and silent exclusions.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from app.agents.contradiction_agent import ContradictionAgent, TrialIsolationError
from app.schemas.contradiction import (
    AnalyzeContradictionRequest,
    ContradictionAssessment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contradiction", tags=["Contradiction Analysis"])


@router.post(
    "/analyze",
    response_model=ContradictionAssessment,
    status_code=status.HTTP_200_OK,
    summary="Analyze protocol criteria, patient facts, and assessments for contradictions",
)
async def analyze_contradictions(
    request: AnalyzeContradictionRequest,
) -> ContradictionAssessment:
    """Analyzes a clinical trial eligibility evaluation for contradictions and omissions.

    Enforces:
    - Protocol Contradictions: Mutually unsatisfiable eligibility constraints.
    - Patient Fact Contradictions: Conflicting contemporaneous facts in patient record.
    - Assessment Contradictions: Deterministic re-evaluation of upstream agent decisions.
    - Silent Exclusions: Protocol exclusions triggered by patient facts but omitted from assessment.
    - Strict Trial Isolation: Cross-trial evidence or assessments are rejected immediately.
    """
    clean_trial_id = (request.trial_id or "").strip()
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    agent = ContradictionAgent()

    try:
        assessment = await agent.analyze(
            trial_id=clean_trial_id,
            patient_profile=request.patient_profile,
            protocol_evidence=request.protocol_evidence,
            inclusion_assessment=request.inclusion_assessment,
            exclusion_assessment=request.exclusion_assessment,
            reference_date=request.reference_date,
        )
        return assessment
    except TrialIsolationError as err:
        logger.warning("Trial isolation error in contradiction analysis: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        logger.warning("Validation error in contradiction analysis: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.error("Unexpected error in contradiction analysis: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during contradiction and silent exclusion analysis.",
        ) from err
