"""Pydantic schemas for Inclusion Matching Agent assessments and requests.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class InclusionStatus(str, Enum):
    """Evaluation status for an inclusion criterion or overall inclusion assessment."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class InclusionCriterionAssessment(BaseModel):
    """Detailed clinical evaluation result for a single inclusion criterion."""

    criterion_id: str = Field(..., description="Unique criterion identifier (e.g. INC-001)")
    trial_id: str = Field(..., description="Authoritative trial identifier this criterion belongs to")
    status: InclusionStatus = Field(..., description="Evaluation outcome: PASS, FAIL, or UNKNOWN")
    criterion_text: str = Field(..., description="Exact textual statement of the protocol criterion")
    patient_value: Optional[Any] = Field(default=None, description="Extracted patient clinical fact used for evaluation")
    expected_requirement: str = Field(..., description="Specific protocol requirement or threshold expected")
    rationale: str = Field(..., description="Traceable clinical justification for the evaluation outcome")
    evidence: Optional[Union[Dict[str, Any], str]] = Field(
        default=None, description="Patient or protocol evidence data supporting evaluation"
    )
    source_page: int = Field(..., ge=1, description="1-indexed source page in protocol document")
    source_document: str = Field(..., description="Filename or identifier of the source protocol document")
    source_excerpt: Optional[str] = Field(default=None, description="Direct excerpt citation from protocol source")


class InclusionAssessment(BaseModel):
    """Complete inclusion criteria assessment for a patient and trial."""

    trial_id: str = Field(..., description="Authoritative trial identifier")
    patient_profile_id: str = Field(..., description="Identifier of the evaluated patient profile")
    overall_status: InclusionStatus = Field(
        ...,
        description="Overall inclusion evaluation status: PASS (all pass), FAIL (any fail), or UNKNOWN (any missing/unknown without fail)",
    )
    criteria: List[InclusionCriterionAssessment] = Field(
        default_factory=list, description="Criterion-by-criterion assessment list"
    )
    missing_information: List[str] = Field(
        default_factory=list, description="List of required clinical data points missing from the patient record"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal warnings or validation notices"
    )


class EvaluateInclusionRequest(BaseModel):
    """Request payload for evaluating inclusion criteria."""

    trial_id: str = Field(..., min_length=1, description="Authoritative clinical trial ID (e.g. SYN-ONC-001)")
    patient_profile: PatientProfile = Field(..., description="Structured patient clinical profile")
    retrieved_evidence: List[RetrievedChunk] = Field(
        ..., min_length=1, description="Protocol evidence chunks retrieved for the selected trial"
    )
