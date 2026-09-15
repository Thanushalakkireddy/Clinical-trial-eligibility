"""High-level RAG service coordinating chunking, embedding, vector storage, and retrieval.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Union

from app.rag.chunker import ProtocolChunker
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.metadata_store import MetadataStore
from app.rag.retriever import ProtocolRetriever
from app.rag.vector_store import FAISSVectorStore
from app.schemas.protocol import ExtractedProtocol
from app.schemas.rag import IndexProtocolResponse, ProtocolChunk, RetrievalResult
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)


class RAGService:
    """Unified service for protocol chunking, vector indexing, and isolated semantic retrieval."""

    def __init__(
        self,
        chunker: Optional[ProtocolChunker] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[FAISSVectorStore] = None,
        metadata_store: Optional[MetadataStore] = None,
        retriever: Optional[ProtocolRetriever] = None,
    ) -> None:
        self.chunker = chunker or ProtocolChunker()
        self.embedding_service = embedding_service or get_embedding_service()
        self.vector_store = vector_store or FAISSVectorStore()
        self.metadata_store = metadata_store or MetadataStore()
        self.retriever = retriever or ProtocolRetriever(
            embedding_service=self.embedding_service,
            vector_store=self.vector_store,
            metadata_store=self.metadata_store,
        )

    def index_protocol(
        self, protocol: Union[ExtractedProtocol, Dict[str, Any]], trial_id: Optional[str] = None
    ) -> IndexProtocolResponse:
        """Chunk, embed, and index an extracted clinical trial protocol into a trial-isolated FAISS index.
        
        Args:
            protocol: ExtractedProtocol model or equivalent dictionary.
            trial_id: Optional trial identifier override.
            
        Returns:
            IndexProtocolResponse with chunk count and storage details.
        """
        # Determine trial_id
        if trial_id:
            tid = trial_id
        elif isinstance(protocol, ExtractedProtocol):
            tid = protocol.trial_id or protocol.protocol_id
        elif isinstance(protocol, dict):
            tid = protocol.get("trial_id") or protocol.get("protocol_id")
        else:
            tid = "UNKNOWN"

        if not tid or not str(tid).strip():
            raise ValueError("Trial ID must be provided to index protocol")

        tid = str(tid).strip()

        # Step 1: Chunk protocol criteria
        chunks: List[ProtocolChunk] = self.chunker.chunk_protocol(protocol)
        if not chunks:
            logger.warning("No eligibility criteria found to chunk for trial %s", tid)
            return IndexProtocolResponse(
                trial_id=tid,
                indexed_chunks_count=0,
                status="empty",
                storage_path=str(self.metadata_store.get_trial_dir(tid)),
            )

        # Step 2: Extract text and generate normalized embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_service.embed_texts(texts)

        # Step 3: Index in trial-isolated vector store
        self.vector_store.index_vectors(tid, embeddings)

        # Step 4: Persist metadata 1:1 with vectors
        meta_path = self.metadata_store.save(tid, chunks)

        return IndexProtocolResponse(
            trial_id=tid,
            indexed_chunks_count=len(chunks),
            status="success",
            storage_path=str(meta_path.parent),
        )

    def retrieve(self, trial_id: str, query: str, top_k: int = 5) -> RetrievalResult:
        """Execute semantic retrieval over a trial's isolated protocol index.
        
        Args:
            trial_id: Target trial identifier.
            query: Clinical query string.
            top_k: Number of criteria to retrieve.
            
        Returns:
            RetrievalResult containing ranked list of criteria chunks.
        """
        timer = start_timer()
        try:
            result = self.retriever.retrieve(trial_id=trial_id, query=query, top_k=top_k)
            log_stage("rag.retrieve", timer.elapsed_ms(), ok=True, detail=f"trial={trial_id}")
            return result
        except Exception:
            log_stage("rag.retrieve", timer.elapsed_ms(), ok=False, detail=f"trial={trial_id}")
            raise

    def has_trial_index(self, trial_id: str) -> bool:
        """Check if index and metadata exist for a trial."""
        return self.vector_store.exists(trial_id) and self.metadata_store.exists(trial_id)

    def clear_trial_index(self, trial_id: str) -> bool:
        """Clear all indexed data for a trial."""
        v_cleared = self.vector_store.delete_index(trial_id)
        m_cleared = self.metadata_store.clear(trial_id)
        return v_cleared or m_cleared


_rag_service_instance: Optional[RAGService] = None
_rag_lock = threading.Lock()


def get_rag_service() -> RAGService:
    """Retrieve or initialize the global RAGService singleton."""
    global _rag_service_instance
    if _rag_service_instance is None:
        with _rag_lock:
            if _rag_service_instance is None:
                _rag_service_instance = RAGService()
    return _rag_service_instance
