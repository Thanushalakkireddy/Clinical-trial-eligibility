"""FastAPI router for the Decision / Reviewer Agent.

Provides direct evaluation of upstream eligibility assessments (Inclusion, Exclusion,
Contradiction) to produce authoritative, deterministic DecisionAssessment outputs.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from app.agents.decision_reviewer_agent import DecisionReviewerAgent, TrialIsolationError
from app.schemas.decision import DecisionAssessment, EvaluateDecisionRequest

logger = logging.getLogger(__name__)

decision_router = APIRouter(prefix="/api/v1/decision", tags=["Decision / Reviewer Agent"])


@decision_router.post(
    "/evaluate",
    response_model=DecisionAssessment,
    summary="Evaluate eligibility assessments to produce authoritative final decision",
    status_code=status.HTTP_200_OK,
)
async def evaluate_decision(request: EvaluateDecisionRequest) -> DecisionAssessment:
    """Evaluates upstream assessments deterministically to produce the final classification.

    Applies strict clinical trial decision rules:
    - NOT_ELIGIBLE if inclusion FAIL, exclusion TRIGGERED, or confirmed SILENT_EXCLUSION
    - MORE_INFORMATION_REQUIRED if missing data, UNKNOWN criteria, or critical contradictions
    - ELIGIBLE if all inclusion PASS, exclusions CLEAR, and no critical contradictions
    """
    agent = DecisionReviewerAgent()
    try:
        assessment = agent.evaluate(
            trial_id=request.trial_id,
            patient_profile=request.patient_profile,
            inclusion_assessment=request.inclusion_assessment,
            exclusion_assessment=request.exclusion_assessment,
            contradiction_assessment=request.contradiction_assessment,
            protocol_evidence=request.protocol_evidence,
        )
        return assessment
    except TrialIsolationError as tie:
        logger.warning("Trial isolation error in decision evaluation: %s", tie)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(tie),
        )
    except ValueError as ve:
        logger.warning("Validation error in decision evaluation: %s", ve)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as exc:
        logger.exception("Unexpected error in decision evaluation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during decision evaluation.",
        )
