"""FastAPI router for clinical trial inclusion criteria evaluation.

Provides POST /api/v1/inclusion/evaluate to process structured patient profiles
against trial-isolated protocol evidence.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from app.agents.inclusion_matching_agent import (
    CriterionTypeError,
    InclusionMatchingAgent,
    TrialIsolationError,
)
from app.schemas.inclusion import EvaluateInclusionRequest, InclusionAssessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/inclusion", tags=["Inclusion Matching"])


@router.post(
    "/evaluate",
    response_model=InclusionAssessment,
    status_code=status.HTTP_200_OK,
    summary="Evaluate trial inclusion criteria against a structured patient profile",
)
async def evaluate_inclusion(request: EvaluateInclusionRequest) -> InclusionAssessment:
    """Evaluates protocol inclusion criteria for the selected trial against a patient profile.

    Enforces:
    - Strict trial isolation: All evidence criteria must belong to the selected trial_id.
    - Criterion type validation: Only inclusion criteria are accepted.
    - Deterministic numerical and range comparison.
    - Zero/False preservation (not treated as missing).
    - UNKNOWN status for any missing required clinical fact.
    """
    clean_trial_id = (request.trial_id or "").strip()
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    agent = InclusionMatchingAgent()

    try:
        assessment = await agent.evaluate(
            trial_id=clean_trial_id,
            patient_profile=request.patient_profile,
            retrieved_evidence=request.retrieved_evidence,
        )
        return assessment
    except TrialIsolationError as err:
        logger.warning("Trial isolation error: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except CriterionTypeError as err:
        logger.warning("Criterion type error: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        logger.warning("Validation error in inclusion evaluation: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.error("Unexpected error during inclusion evaluation: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating inclusion criteria.",
        ) from err
