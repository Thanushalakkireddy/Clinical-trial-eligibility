"""Pydantic schemas for Contradiction and Silent Exclusion Agent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from app.schemas.exclusion import ExclusionAssessment
from app.schemas.inclusion import InclusionAssessment
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk


class ContradictionType(str, Enum):
    """Classification of contradictions and evidence inconsistencies."""

    PROTOCOL_CONTRADICTION = "PROTOCOL_CONTRADICTION"
    PATIENT_FACT_CONTRADICTION = "PATIENT_FACT_CONTRADICTION"
    ASSESSMENT_CONTRADICTION = "ASSESSMENT_CONTRADICTION"
    SILENT_EXCLUSION = "SILENT_EXCLUSION"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"


class ContradictionSeverity(str, Enum):
    """Severity classification for clinical contradiction findings."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ContradictionFinding(BaseModel):
    """Individual contradiction or silent exclusion finding."""

    finding_id: str = Field(..., description="Unique finding identifier (e.g. FINDING-001)")
    trial_id: str = Field(..., description="Authoritative trial identifier")
    contradiction_type: ContradictionType = Field(..., description="Category of contradiction")
    severity: ContradictionSeverity = Field(..., description="Impact severity: INFO, WARNING, or CRITICAL")
    title: str = Field(..., description="Concise human-readable title of the discrepancy")
    description: str = Field(..., description="Detailed explanation of the contradiction and conflict logic")
    criterion_ids: List[str] = Field(default_factory=list, description="IDs of protocol criteria involved")
    patient_fields: List[str] = Field(default_factory=list, description="Patient profile fields involved")
    evidence: Optional[Union[Dict[str, Any], List[Any], str]] = Field(
        default=None, description="Supporting conflicting facts, citations, or excerpts"
    )
    recommended_action: str = Field(..., description="Clinical action or investigator inquiry recommendation")


class ContradictionAssessment(BaseModel):
    """Comprehensive contradiction and silent exclusion assessment."""

    trial_id: str = Field(..., description="Authoritative trial identifier")
    patient_profile_id: str = Field(..., description="Evaluated patient profile identifier")
    findings: List[ContradictionFinding] = Field(
        default_factory=list, description="List of detected contradiction findings"
    )
    checked_criteria: List[str] = Field(
        default_factory=list, description="List of criterion IDs analyzed across protocol and assessments"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal warnings or validation notices"
    )
    has_critical_findings: bool = Field(
        default=False, description="True if one or more CRITICAL severity findings were detected"
    )


class AnalyzeContradictionRequest(BaseModel):
    """Request payload for contradiction and silent exclusion analysis."""

    trial_id: str = Field(..., min_length=1, description="Authoritative clinical trial ID (e.g. SYN-ONC-001)")
    patient_profile: PatientProfile = Field(..., description="Structured patient clinical profile")
    protocol_evidence: List[Union[RetrievedChunk, Dict[str, Any]]] = Field(
        default_factory=list, description="List of retrieved protocol evidence chunks for the trial"
    )
    inclusion_assessment: Optional[InclusionAssessment] = Field(
        default=None, description="Optional upstream InclusionMatchingAgent assessment"
    )
    exclusion_assessment: Optional[ExclusionAssessment] = Field(
        default=None, description="Optional upstream ExclusionDetectionAgent assessment"
    )
    reference_date: Optional[str] = Field(
        default=None, description="Evaluation reference date (YYYY-MM-DD) for temporal criteria"
    )
