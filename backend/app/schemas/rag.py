"""Pydantic schemas for RAG protocol chunking, semantic retrieval, and FAISS indexing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ProtocolChunk(BaseModel):
    """Retrieval-ready protocol chunk retaining full criterion identity and evidence traceability."""

    chunk_id: str = Field(..., description="Deterministic unique ID for this chunk (e.g. CHK-SYN-ONC-001-INC-001)")
    trial_id: str = Field(..., description="Clinical trial identifier")
    criterion_id: str = Field(..., description="Criterion identifier (e.g. INC-001, EXC-002)")
    criterion_type: str = Field(..., description="Criterion type: inclusion | exclusion | other")
    section: str = Field(..., description="Protocol section heading (e.g. 'Inclusion Criteria')")
    text: str = Field(..., description="Exact/faithful criterion text with clinical thresholds preserved")
    source_page: int = Field(..., ge=1, description="1-indexed source page number in protocol PDF")
    source_document: str = Field(..., description="Source protocol PDF or document name")
    source_excerpt: Optional[str] = Field(default=None, description="Direct textual excerpt from source page")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")


class RetrievalQuery(BaseModel):
    """Query model for retrieving relevant protocol criteria."""

    trial_id: str = Field(..., description="Clinical trial identifier to search within (enforces trial isolation)")
    query: str = Field(..., min_length=1, description="Semantic search query text (e.g. 'kidney function requirement')")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of top relevant criteria to return")


class RetrievedChunk(BaseModel):
    """A retrieved protocol chunk scored by semantic similarity."""

    chunk_id: str = Field(..., description="Chunk identifier")
    trial_id: str = Field(..., description="Trial identifier")
    criterion_id: str = Field(..., description="Criterion identifier")
    criterion_type: str = Field(..., description="Criterion type: inclusion | exclusion | other")
    text: str = Field(..., description="Criterion text")
    score: float = Field(..., description="Cosine similarity score (higher is more relevant)")
    source_page: int = Field(..., description="Source page number")
    source_document: str = Field(..., description="Source document filename")
    source_excerpt: Optional[str] = Field(default=None, description="Source excerpt")
    section: Optional[str] = Field(default=None, description="Protocol section")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")


class RetrievalResult(BaseModel):
    """Container for retrieval response."""

    query: str = Field(..., description="Original semantic query")
    trial_id: str = Field(..., description="Trial identifier searched")
    results: List[RetrievedChunk] = Field(default_factory=list, description="Ranked retrieved protocol chunks")


class IndexProtocolRequest(BaseModel):
    """Request body for indexing an extracted protocol."""

    trial_id: str = Field(..., description="Clinical trial identifier")
    protocol: Union[Dict[str, Any], Any] = Field(..., description="ExtractedProtocol payload as JSON dictionary or model")


class IndexProtocolResponse(BaseModel):
    """Response body for indexing an extracted protocol."""

    trial_id: str = Field(..., description="Clinical trial identifier")
    indexed_chunks_count: int = Field(..., description="Number of chunks successfully indexed")
    status: str = Field(default="success", description="Status of indexing operation")
    storage_path: Optional[str] = Field(default=None, description="Filesystem directory where index and metadata are stored")
