"""Workflow state models for LangGraph multi-agent clinical trial eligibility orchestration.

Strongly typed state for the multi-agent graph:
START -> Validate Input -> Protocol Retrieval -> Inclusion Agent -> Exclusion Agent -> Contradiction Agent -> END
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from app.schemas.contradiction import ContradictionAssessment
from app.schemas.decision import DecisionAssessment
from app.schemas.exclusion import ExclusionAssessment
from app.schemas.inclusion import InclusionAssessment
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class WorkflowState(TypedDict, total=False):
    """Authoritative strongly typed LangGraph state schema.

    Contains trial isolation anchors, clinical profiles, protocol evidence with full
    provenance, sequential agent assessment outputs, and final decision assessment.
    """

    trial_id: str
    patient_profile: PatientProfile
    patient_profile_id: str
    reference_date: Optional[str]
    protocol_evidence: List[RetrievedChunk]
    inclusion_assessment: Optional[InclusionAssessment]
    exclusion_assessment: Optional[ExclusionAssessment]
    contradiction_assessment: Optional[ContradictionAssessment]
    decision_assessment: Optional[DecisionAssessment]
    errors: List[str]
    warnings: List[str]
    current_step: str


def create_initial_state(
    trial_id: str,
    patient_profile: PatientProfile,
    patient_profile_id: Optional[str] = None,
    reference_date: Optional[str] = None,
    protocol_evidence: Optional[List[RetrievedChunk]] = None,
) -> WorkflowState:
    """Helper to initialize a pristine WorkflowState dictionary for LangGraph execution."""
    derived_pid = (
        patient_profile_id
        or getattr(patient_profile, "patient_profile_id", None)
        or "UNKNOWN_PATIENT"
    )

    return {
        "trial_id": (trial_id or "").strip(),
        "patient_profile": patient_profile,
        "patient_profile_id": derived_pid,
        "reference_date": reference_date,
        "protocol_evidence": list(protocol_evidence) if protocol_evidence else [],
        "inclusion_assessment": None,
        "exclusion_assessment": None,
        "contradiction_assessment": None,
        "decision_assessment": None,
        "errors": [],
        "warnings": [],
        "current_step": "START",
    }
