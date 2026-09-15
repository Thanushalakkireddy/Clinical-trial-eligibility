"""Pydantic schemas for Clinical Trial Protocol criteria and structured extraction.

Provides validation models for criteria traceability, page evidence, and protocol structure.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CriterionType(str, Enum):
    """Classification of eligibility criterion."""

    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"
    OTHER = "other"


class ProtocolCriterion(BaseModel):
    """Structured representation of an individual eligibility criterion with page traceability."""

    criterion_id: str = Field(
        ...,
        description="Deterministic criterion ID (e.g. INC-001, EXC-001, OTHER-001)",
        examples=["INC-001", "EXC-002"],
    )
    type: CriterionType = Field(
        ...,
        description="Type of eligibility criterion (inclusion, exclusion, or other)",
    )
    text: str = Field(
        ...,
        description="Exact or faithful criterion text as stated in the protocol",
    )
    source_page: int = Field(
        ...,
        ge=1,
        description="1-indexed source page number in the protocol PDF where criterion appears",
    )
    section: str = Field(
        ...,
        description="Protocol section heading (e.g., 'Inclusion Criteria', 'Exclusion Criteria')",
    )
    source_excerpt: Optional[str] = Field(
        default=None,
        description="Short direct textual excerpt from the source page serving as citation",
    )
    trial_id: str = Field(
        ...,
        description="Clinical trial identifier this criterion belongs to",
    )


class ExtractedProtocol(BaseModel):
    """Complete structured representation of an extracted clinical trial protocol."""

    trial_id: str = Field(
        ...,
        description="Trial identifier assigned or extracted for the trial",
    )
    protocol_id: str = Field(
        ...,
        description="Official protocol code from the document (e.g. SYN-ONC-001) or deterministic fallback",
    )
    title: str = Field(
        default="",
        description="Official trial/protocol title from the document",
    )
    inclusion_criteria: List[ProtocolCriterion] = Field(
        default_factory=list,
        description="Ordered list of extracted inclusion criteria",
    )
    exclusion_criteria: List[ProtocolCriterion] = Field(
        default_factory=list,
        description="Ordered list of extracted exclusion criteria",
    )
    other_requirements: List[ProtocolCriterion] = Field(
        default_factory=list,
        description="Other eligibility requirements (e.g., study design parameters, age bounds)",
    )
    source_document: str = Field(
        ...,
        description="Source PDF filename or relative path",
    )
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata including model name, timestamp, page count, and status",
    )
