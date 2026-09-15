"""FastAPI router for clinical trial exclusion criteria evaluation.

Provides POST /api/v1/exclusion/evaluate to evaluate patient profiles against
trial-isolated protocol exclusion criteria.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from app.agents.exclusion_detection_agent import (
    CriterionTypeError,
    ExclusionDetectionAgent,
    TrialIsolationError,
)
from app.schemas.exclusion import EvaluateExclusionRequest, ExclusionAssessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exclusion", tags=["Exclusion Detection"])


@router.post(
    "/evaluate",
    response_model=ExclusionAssessment,
    status_code=status.HTTP_200_OK,
    summary="Evaluate trial exclusion criteria against a structured patient profile",
)
async def evaluate_exclusion(request: EvaluateExclusionRequest) -> ExclusionAssessment:
    """Evaluates protocol exclusion criteria for the selected trial against a patient profile.

    Enforces:
    - Strict trial isolation: All evidence criteria must belong to the selected trial_id.
    - Criterion type validation: Only exclusion criteria are accepted.
    - Deterministic threshold, operator, and temporal comparison.
    - Zero/False preservation (not treated as missing).
    - UNKNOWN status for any missing required clinical fact (never assumes missing = CLEAR).
    """
    clean_trial_id = (request.trial_id or "").strip()
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    agent = ExclusionDetectionAgent()

    try:
        assessment = await agent.evaluate(
            trial_id=clean_trial_id,
            patient_profile=request.patient_profile,
            retrieved_evidence=request.retrieved_evidence,
            reference_date=request.reference_date,
        )
        return assessment
    except TrialIsolationError as err:
        logger.warning("Trial isolation error in exclusion: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except CriterionTypeError as err:
        logger.warning("Criterion type error in exclusion: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        logger.warning("Validation error in exclusion evaluation: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.error("Unexpected error during exclusion evaluation: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating exclusion criteria.",
        ) from err
