"""Protocol criteria retriever for clinical trial eligibility RAG pipeline.

Searches trial-isolated FAISS indices using normalized query embeddings,
reconstructs rich criteria metadata with full threshold preservation, and
returns ranked RetrievedChunk objects.
"""

from __future__ import annotations

import logging
from typing import List, Optional
import numpy as np

from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.metadata_store import MetadataStore
from app.rag.vector_store import FAISSVectorStore
from app.schemas.rag import RetrievalResult, RetrievedChunk

logger = logging.getLogger(__name__)


class ProtocolRetriever:
    """Performs semantic search over trial-isolated criteria indices."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[FAISSVectorStore] = None,
        metadata_store: Optional[MetadataStore] = None,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.vector_store = vector_store or FAISSVectorStore()
        self.metadata_store = metadata_store or MetadataStore()

    def retrieve(self, trial_id: str, query: str, top_k: int = 5) -> RetrievalResult:
        """Retrieve most relevant protocol criteria for a query within a trial.
        
        Args:
            trial_id: Trial identifier (strict trial isolation).
            query: Semantic search query.
            top_k: Number of criteria to retrieve (must be >= 1).
            
        Returns:
            RetrievalResult containing ranked list of RetrievedChunk objects.
        """
        # Input validation
        clean_query = (query or "").strip()
        if not clean_query:
            logger.info("Empty query provided to retrieve for trial %s", trial_id)
            return RetrievalResult(query="", trial_id=trial_id, results=[])

        if top_k <= 0:
            return RetrievalResult(query=clean_query, trial_id=trial_id, results=[])

        # Check if index exists for this trial
        if not self.vector_store.exists(trial_id) or not self.metadata_store.exists(trial_id):
            logger.warning("No vector index or metadata found for trial %s", trial_id)
            return RetrievalResult(query=clean_query, trial_id=trial_id, results=[])

        # Load metadata for this trial
        metadata_chunks = self.metadata_store.load(trial_id)
        if not metadata_chunks:
            logger.warning("Loaded empty metadata for trial %s", trial_id)
            return RetrievalResult(query=clean_query, trial_id=trial_id, results=[])

        # Generate query embedding
        query_vec = self.embedding_service.embed_query(clean_query)

        # Search FAISS vector store
        scores, indices = self.vector_store.search(trial_id, query_vec, top_k=top_k)

        results: List[RetrievedChunk] = []
        if scores.size == 0 or indices.size == 0:
            return RetrievalResult(query=clean_query, trial_id=trial_id, results=[])

        score_row = scores[0]
        index_row = indices[0]

        for score, idx in zip(score_row, index_row):
            # FAISS returns -1 when fewer elements exist than requested k
            if idx < 0 or idx >= len(metadata_chunks):
                continue

            chunk = metadata_chunks[idx]
            retrieved = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                trial_id=chunk.trial_id,
                criterion_id=chunk.criterion_id,
                criterion_type=chunk.criterion_type,
                text=chunk.text,
                score=float(round(score, 4)),
                source_page=chunk.source_page,
                source_document=chunk.source_document,
                source_excerpt=chunk.source_excerpt,
                section=chunk.section,
                metadata=chunk.metadata,
            )
            results.append(retrieved)

        return RetrievalResult(
            query=clean_query,
            trial_id=trial_id,
            results=results,
        )
