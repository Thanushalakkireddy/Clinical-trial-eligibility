"""Pydantic schemas for Exclusion Detection Agent assessments and requests.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class ExclusionStatus(str, Enum):
    """Evaluation status for an exclusion criterion or overall exclusion assessment."""

    TRIGGERED = "TRIGGERED"
    CLEAR = "CLEAR"
    UNKNOWN = "UNKNOWN"


class ExclusionCriterionAssessment(BaseModel):
    """Detailed clinical evaluation result for a single exclusion criterion."""

    criterion_id: str = Field(..., description="Unique criterion identifier (e.g. EXC-001)")
    trial_id: str = Field(..., description="Authoritative trial identifier this criterion belongs to")
    status: ExclusionStatus = Field(..., description="Evaluation outcome: TRIGGERED, CLEAR, or UNKNOWN")
    criterion_text: str = Field(..., description="Exact textual statement of the protocol exclusion criterion")
    patient_value: Optional[Any] = Field(default=None, description="Extracted patient clinical fact used for evaluation")
    exclusion_requirement: str = Field(..., description="Specific protocol exclusion threshold or condition")
    rationale: str = Field(..., description="Traceable clinical justification for the evaluation outcome")
    evidence: Optional[Union[Dict[str, Any], str]] = Field(
        default=None, description="Supporting patient or protocol evidence citation"
    )
    source_page: int = Field(..., ge=1, description="1-indexed source page in protocol document")
    source_document: str = Field(..., description="Filename or identifier of the source protocol document")
    source_excerpt: Optional[str] = Field(default=None, description="Direct excerpt citation from protocol source")


class ExclusionAssessment(BaseModel):
    """Complete exclusion criteria assessment for a patient and trial."""

    trial_id: str = Field(..., description="Authoritative trial identifier")
    patient_profile_id: str = Field(..., description="Identifier of the evaluated patient profile")
    overall_status: ExclusionStatus = Field(
        ...,
        description="Overall exclusion status: TRIGGERED (any triggered), UNKNOWN (no triggered, >=1 unknown), CLEAR (all clear)",
    )
    criteria: List[ExclusionCriterionAssessment] = Field(
        default_factory=list, description="Criterion-by-criterion assessment list"
    )
    missing_information: List[str] = Field(
        default_factory=list, description="List of required clinical data points missing from the patient record"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal warnings or validation notices"
    )


class EvaluateExclusionRequest(BaseModel):
    """Request payload for evaluating exclusion criteria."""

    trial_id: str = Field(..., min_length=1, description="Authoritative clinical trial ID (e.g. SYN-ONC-001)")
    patient_profile: PatientProfile = Field(..., description="Structured patient clinical profile")
    retrieved_evidence: List[RetrievedChunk] = Field(
        ..., min_length=1, description="Protocol exclusion chunks retrieved for the selected trial"
    )
    reference_date: Optional[str] = Field(
        default=None, description="Evaluation reference date (YYYY-MM-DD) for temporal calculations"
    )
