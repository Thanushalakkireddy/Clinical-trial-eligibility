"""Pydantic response schemas for the assessment persistence API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class AssessmentSummaryResponse(BaseModel):
    """Summary view of a persisted assessment run."""

    assessment_id: str = Field(..., description="Persisted assessment identifier")
    trial_id: str = Field(..., description="Clinical trial identifier")
    patient_profile_id: str = Field(..., description="Evaluated patient profile identifier")
    reference_date: Optional[str] = Field(default=None, description="Reference date (YYYY-MM-DD) if provided")
    workflow_status: str = Field(..., description="RUNNING | COMPLETED | FAILED")
    final_decision: Optional[str] = Field(default=None, description="ELIGIBLE | NOT_ELIGIBLE | MORE_INFORMATION_REQUIRED")
    current_step: Optional[str] = Field(default=None, description="Final LangGraph step reached")
    created_at: Optional[datetime] = Field(default=None, description="Record creation timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Record completion timestamp")
    has_errors: bool = Field(default=False, description="True when the run recorded workflow errors")
    error_count: int = Field(default=0, description="Number of recorded workflow errors")
    warning_count: int = Field(default=0, description="Number of recorded non-fatal warnings")


class AssessmentTraceResponse(BaseModel):
    """A single persisted per-stage audit line."""

    sequence: int = Field(..., description="1-indexed execution order")
    stage: str = Field(..., description="Workflow stage (start, inclusion, exclusion, contradiction, decision, complete)")
    status: Optional[str] = Field(default=None, description="Stage status or assessment overall status")
    payload: Optional[dict] = Field(default=None, description="Stage assessment payload (JSON-free dict)")
    created_at: Optional[datetime] = Field(default=None, description="Trace line creation timestamp")


class AssessmentDetailResponse(AssessmentSummaryResponse):
    """Full audit view of a persisted assessment run."""

    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings recorded")
    errors: List[str] = Field(default_factory=list, description="Workflow errors recorded")
    snapshot: Optional[dict] = Field(default=None, description="Reproducible snapshot of the evaluated workflow state")
    traces: List[AssessmentTraceResponse] = Field(default_factory=list, description="Ordered per-stage audit lines")