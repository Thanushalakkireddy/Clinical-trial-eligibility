"""Pydantic schemas for Clinical Trial Eligibility LangGraph Workflow and API Endpoints.

Represents the multi-agent execution pipeline:
START -> Validate Input -> Protocol Retrieval -> Inclusion Agent -> Exclusion Agent -> Contradiction Agent -> END
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.contradiction import ContradictionAssessment
from app.schemas.decision import DecisionAssessment
from app.schemas.exclusion import ExclusionAssessment
from app.schemas.inclusion import InclusionAssessment
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class WorkflowStatus(str, Enum):
    """Execution status of the eligibility workflow."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowStage(str, Enum):
    """Current progression stage of the workflow pipeline."""

    INITIALIZATION = "INITIALIZATION"
    VALIDATE_INPUT = "VALIDATE_INPUT"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    INCLUSION = "INCLUSION"
    EXCLUSION = "EXCLUSION"
    CONTRADICTION = "CONTRADICTION"
    DECISION = "DECISION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowEvaluateRequest(BaseModel):
    """Request payload for POST /api/v1/workflow/evaluate."""

    trial_id: str = Field(..., min_length=1, description="Authoritative clinical trial identifier")
    patient_profile: PatientProfile = Field(..., description="Patient clinical data record")
    reference_date: Optional[str] = Field(
        default=None, description="Optional reference date (YYYY-MM-DD) for time-sensitive criteria"
    )
    protocol_evidence: Optional[List[RetrievedChunk]] = Field(
        default=None,
        description="Optional explicitly provided protocol criteria evidence chunks",
    )


class WorkflowStateResponse(BaseModel):
    """Authoritative structured workflow state response from LangGraph execution.

    Contains trial isolation anchors, evidence with full provenance, upstream agent assessments,
    and final authoritative DecisionAssessment produced by DecisionReviewerAgent.
    """

    trial_id: str = Field(..., description="Authoritative selected clinical trial identifier")
    patient_profile_id: str = Field(..., description="Evaluated patient profile identifier")
    protocol_evidence: List[RetrievedChunk] = Field(
        default_factory=list, description="All evaluated protocol criteria with full provenance"
    )
    inclusion_assessment: Optional[InclusionAssessment] = Field(
        default=None, description="Assessment from InclusionMatchingAgent"
    )
    exclusion_assessment: Optional[ExclusionAssessment] = Field(
        default=None, description="Assessment from ExclusionDetectionAgent"
    )
    contradiction_assessment: Optional[ContradictionAssessment] = Field(
        default=None, description="Assessment from ContradictionAgent"
    )
    decision_assessment: Optional[DecisionAssessment] = Field(
        default=None, description="Authoritative final eligibility decision assessment from DecisionReviewerAgent"
    )
    assessment_id: Optional[str] = Field(
        default=None,
        description="Optional assessment persistence identifier (only present when DATABASE_URL is configured)",
    )
    warnings: List[str] = Field(default_factory=list, description="Non-fatal execution warnings")
    errors: List[str] = Field(default_factory=list, description="Structured workflow execution errors")
    current_step: str = Field(..., description="Final pipeline node reached")


# Backwards compatibility schemas
class RunWorkflowRequest(BaseModel):
    """Legacy request payload to execute workflow."""

    trial_id: str = Field(..., min_length=1, description="Selected clinical trial identifier")
    patient_profile: PatientProfile = Field(..., description="Patient clinical profile to evaluate")
    protocol_evidence: Optional[List[RetrievedChunk]] = Field(default=None)
    reference_date: Optional[str] = Field(default=None)
    top_k: int = Field(default=25, ge=1, le=100)


class StructuredWorkflowState(BaseModel):
    """Legacy structured workflow state wrapper."""

    trial_id: str
    patient_profile_id: str
    status: WorkflowStatus = WorkflowStatus.COMPLETED
    current_stage: WorkflowStage = WorkflowStage.COMPLETED
    patient_profile: PatientProfile
    retrieved_evidence: List[RetrievedChunk] = Field(default_factory=list)
    inclusion_evidence: List[RetrievedChunk] = Field(default_factory=list)
    exclusion_evidence: List[RetrievedChunk] = Field(default_factory=list)
    inclusion_assessment: Optional[InclusionAssessment] = None
    exclusion_assessment: Optional[ExclusionAssessment] = None
    contradiction_assessment: Optional[ContradictionAssessment] = None
    decision_assessment: Optional[DecisionAssessment] = None
    execution_timestamp: str = ""
    execution_duration_ms: Optional[float] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    summary: Optional[Dict[str, Any]] = None
