"""Pydantic schemas for the Clinical Trial Eligibility Decision / Reviewer Agent.

Represents the deterministic final decision layer:
- DecisionStatus: ELIGIBLE, NOT_ELIGIBLE, MORE_INFORMATION_REQUIRED
- DecisionEvidence: Traceable evidence citations preserving originating agent and source document provenance
- DecisionAssessment: Complete authoritative eligibility classification and rationale
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.contradiction import ContradictionAssessment, ContradictionFinding
from app.schemas.exclusion import ExclusionAssessment
from app.schemas.inclusion import InclusionAssessment
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class DecisionStatus(str, Enum):
    """Authoritative eligibility decision categories."""

    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"


class DecisionEvidence(BaseModel):
    """Traceable decision evidence citing protocol requirements, patient facts, and provenance."""

    criterion_id: str = Field(..., description="Protocol criterion identifier (e.g., INC-001, EXC-003)")
    criterion_text: str = Field(..., description="Exact requirement or statement from protocol")
    patient_value: Optional[Any] = Field(default=None, description="Clinical value or status extracted from patient record")
    status: str = Field(..., description="Evaluated criterion status (e.g. PASS, FAIL, TRIGGERED, CLEAR, UNKNOWN)")
    source_page: int = Field(..., ge=1, description="Source page number in protocol document")
    source_document: str = Field(..., description="Filename or identifier of source protocol document")
    source_excerpt: Optional[str] = Field(default=None, description="Direct excerpt citation from protocol")
    originating_agent: str = Field(
        ..., description="Agent that produced this evidence (e.g. InclusionMatchingAgent, ExclusionDetectionAgent, ContradictionAgent)"
    )


class DecisionAssessment(BaseModel):
    """Complete authoritative clinical trial eligibility decision assessment.

    NOTE: This is a clinical trial eligibility-support output intended for research
    and clinician workflow support, NOT an independent medical decision or treatment advice.
    """

    trial_id: str = Field(..., description="Authoritative selected clinical trial identifier")
    patient_profile_id: str = Field(..., description="Evaluated patient profile identifier")
    final_status: DecisionStatus = Field(
        ..., description="Final eligibility classification: ELIGIBLE, NOT_ELIGIBLE, or MORE_INFORMATION_REQUIRED"
    )
    requires_human_review: bool = Field(
        ..., description="True if manual clinician/coordinator review is required due to ambiguities, contradictions, or missing data"
    )
    primary_reasons: List[str] = Field(
        default_factory=list, description="Primary clinical justifications driving the final decision"
    )
    decision_evidence: List[DecisionEvidence] = Field(
        default_factory=list, description="Traceable evidence items supporting the primary reasons"
    )
    unresolved_information: List[str] = Field(
        default_factory=list, description="Missing clinical parameters or ambiguous findings preventing definitive determination"
    )
    contradiction_findings: List[ContradictionFinding] = Field(
        default_factory=list, description="Contradictions, evidence conflicts, or silent exclusions identified"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal notices or advisory observations"
    )
    disclaimer: str = Field(
        default="Decision support only. Not an independent medical diagnosis, treatment recommendation, or clinical management decision.",
        description="Clinical decision support safety disclaimer",
    )


class EvaluateDecisionRequest(BaseModel):
    """Request payload for direct Decision / Reviewer Agent evaluation."""

    trial_id: str = Field(..., min_length=1, description="Selected clinical trial ID")
    patient_profile: PatientProfile = Field(..., description="Structured patient clinical profile")
    inclusion_assessment: InclusionAssessment = Field(..., description="Assessment from InclusionMatchingAgent")
    exclusion_assessment: ExclusionAssessment = Field(..., description="Assessment from ExclusionDetectionAgent")
    contradiction_assessment: Optional[ContradictionAssessment] = Field(
        default=None, description="Optional assessment from ContradictionAgent"
    )
    protocol_evidence: Optional[List[RetrievedChunk]] = Field(
        default=None, description="Optional protocol evidence chunks for provenance enrichment"
    )
