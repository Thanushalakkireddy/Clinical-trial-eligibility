"""FastAPI router for clinical trial RAG indexing and semantic criteria retrieval.

Endpoints:
- POST /api/v1/rag/index: Indexes extracted protocol criteria into a trial-isolated FAISS store.
- POST /api/v1/rag/retrieve: Retrieves top-k semantically relevant criteria preserving exact thresholds.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, status

from app.rag.service import get_rag_service
from app.schemas.rag import (
    IndexProtocolRequest,
    IndexProtocolResponse,
    RetrievalQuery,
    RetrievalResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@router.post(
    "/index",
    response_model=IndexProtocolResponse,
    status_code=status.HTTP_200_OK,
    summary="Index protocol criteria",
    description="Chunks and embeds protocol eligibility criteria into a trial-isolated FAISS vector store.",
)
async def index_protocol(request: IndexProtocolRequest) -> IndexProtocolResponse:
    """Index an extracted protocol into the trial-specific FAISS store."""
    if not request.trial_id or not request.trial_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    if not request.protocol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="protocol payload must not be empty.",
        )

    try:
        rag_service = get_rag_service()
        response = rag_service.index_protocol(
            protocol=request.protocol,
            trial_id=request.trial_id.strip(),
        )
        return response
    except ValueError as ve:
        logger.error("Validation error indexing protocol: %s", ve)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        logger.exception("Unexpected error indexing protocol for trial %s", request.trial_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while indexing protocol criteria.",
        )


@router.post(
    "/retrieve",
    response_model=RetrievalResult,
    status_code=status.HTTP_200_OK,
    summary="Retrieve criteria for a query",
    description="Retrieves the top-k most relevant eligibility criteria for a given trial and query.",
)
async def retrieve_criteria(query: RetrievalQuery) -> RetrievalResult:
    """Perform semantic search for eligibility criteria within a specific trial."""
    trial_id = query.trial_id.strip() if query.trial_id else ""
    if not trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id must not be empty.",
        )

    clean_q = query.query.strip() if query.query else ""
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query must not be empty.",
        )

    if query.top_k <= 0 or query.top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="top_k must be between 1 and 50.",
        )

    try:
        rag_service = get_rag_service()
        result = rag_service.retrieve(
            trial_id=trial_id,
            query=clean_q,
            top_k=query.top_k,
        )
        return result
    except Exception as exc:
        logger.exception("Failed retrieval for trial %s", trial_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during criteria retrieval.",
        )
