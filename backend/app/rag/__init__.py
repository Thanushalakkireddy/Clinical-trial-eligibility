"""Retrieval-Augmented Generation (RAG) and vector store package."""

from app.rag.chunker import ProtocolChunker
from app.rag.embeddings import (
    DEFAULT_MODEL_NAME,
    EMBEDDING_DIMENSION,
    EmbeddingService,
    get_embedding_service,
)
from app.rag.metadata_store import MetadataStore, sanitize_trial_id
from app.rag.retriever import ProtocolRetriever
from app.rag.service import RAGService, get_rag_service
from app.rag.vector_store import FAISSVectorStore

__all__ = [
    "ProtocolChunker",
    "EmbeddingService",
    "get_embedding_service",
    "EMBEDDING_DIMENSION",
    "DEFAULT_MODEL_NAME",
    "MetadataStore",
    "sanitize_trial_id",
    "FAISSVectorStore",
    "ProtocolRetriever",
    "RAGService",
    "get_rag_service",
]
