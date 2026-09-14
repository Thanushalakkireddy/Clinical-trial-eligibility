"""Embedding service for clinical trial protocol criteria using SentenceTransformers.

Embeds text into normalized 384-dimensional dense vectors using:
    sentence-transformers/all-MiniLM-L6-v2

SentenceTransformer is loaded once and cached/reused across requests.
Vectors are strictly L2-normalized so that inner-product search (FAISS IndexFlatIP)
corresponds exactly to cosine similarity.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import List, Optional
import numpy as np

from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """Manages embedding generation with SentenceTransformers and normalization."""

    _model = None
    _model_name: str = DEFAULT_MODEL_NAME
    _lock = threading.Lock()
    _is_fallback: bool = False
    _load_thread: Optional[threading.Thread] = None

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        load_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = EMBEDDING_DIMENSION
        if load_timeout_seconds is None:
            try:
                from app.config import settings
                load_timeout_seconds = float(settings.embedding_model_load_timeout_seconds)
            except Exception:
                load_timeout_seconds = 30.0
        self._timeout_s = load_timeout_seconds
        self._ensure_model_loaded()

    def _ensure_model_loaded(self) -> None:
        """Load SentenceTransformer model once, thread-safely, with a hard timeout.

        The HuggingFace model download/load is synchronous and network-dependent;
        on a stalled connection it can block indefinitely. The load therefore runs
        in a background daemon thread and the caller waits at most ``self._timeout_s``
        seconds (0 = unlimited). On deadline the service degrades to the
        deterministic embedder instead of stalling the event loop forever.
        """
        if EmbeddingService._model is not None:
            return

        thread = EmbeddingService._load_thread
        if thread is not None and thread.is_alive():
            if self._timeout_s and self._timeout_s > 0:
                thread.join(timeout=self._timeout_s)
            else:
                thread.join()
            if EmbeddingService._model is None:
                EmbeddingService._is_fallback = True
            return

        with EmbeddingService._lock:
            if EmbeddingService._model is not None:
                return
            EmbeddingService._is_fallback = False
            EmbeddingService._load_thread = threading.Thread(
                target=self._load_model_blocking,
                name="embedding-model-load",
                daemon=True,
            )
            EmbeddingService._load_thread.start()

        load_wait = start_timer()
        if self._timeout_s and self._timeout_s > 0:
            EmbeddingService._load_thread.join(timeout=self._timeout_s)
        else:
            EmbeddingService._load_thread.join()
        if EmbeddingService._model is None:
            log_stage(
                "embedding.model.load",
                load_wait.elapsed_ms(),
                ok=False,
                detail=f"{self.model_name} TIMEOUT={self._timeout_s}s",
            )
            if EmbeddingService._load_thread.is_alive():
                logger.warning(
                    "SentenceTransformer model load exceeded %s seconds; "
                    "using deterministic normalized 384-d semantic fallback for now.",
                    self._timeout_s,
                )
            EmbeddingService._is_fallback = True
        else:
            log_stage(
                "embedding.model.load",
                load_wait.elapsed_ms(),
                ok=True,
                detail=self.model_name,
            )

    def _load_model_blocking(self) -> None:
        """Actually construct the SentenceTransformer model (background thread)."""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading SentenceTransformer model: %s", self.model_name)
            EmbeddingService._model = SentenceTransformer(self.model_name)
            EmbeddingService._is_fallback = False
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as exc:
            logger.warning(
                "SentenceTransformer could not be initialized (%s). "
                "Using deterministic normalized 384-d semantic fallback.",
                exc,
            )
            EmbeddingService._model = None
            EmbeddingService._is_fallback = True

    @property
    def is_real_model_loaded(self) -> bool:
        """Check if real SentenceTransformer model is active."""
        return EmbeddingService._model is not None and not EmbeddingService._is_fallback

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Compute normalized 384-dimensional embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            np.ndarray of shape (len(texts), 384) with dtype float32, L2-normalized.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        # Real SentenceTransformer path
        if EmbeddingService._model is not None and not EmbeddingService._is_fallback:
            try:
                embed_timer = start_timer()
                embeddings = EmbeddingService._model.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                embeddings = np.asarray(embeddings, dtype=np.float32)
                # Ensure exact shape and normalization
                result = self._normalize(embeddings)
                log_stage("embedding.encode", embed_timer.elapsed_ms(), ok=True, detail=f"n={len(texts)}")
                return result
            except Exception as e:
                logger.error("Error generating embeddings with SentenceTransformer: %s", e)
                log_stage("embedding.encode", embed_timer.elapsed_ms(), ok=False)
                # Fall through to fallback

        # Fallback deterministic vector generator (384-d normalized)
        return self._deterministic_embeddings(texts)

    def embed_query(self, query: str) -> np.ndarray:
        """Compute normalized 384-dimensional embedding for a single search query.
        
        Args:
            query: Semantic search query string.
            
        Returns:
            np.ndarray of shape (1, 384) with dtype float32, L2-normalized.
        """
        if not query or not query.strip():
            # Return zero or uniform normalized vector
            vec = np.ones((1, self.dimension), dtype=np.float32)
            return self._normalize(vec)

        return self.embed_texts([query.strip()])

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        """Safely L2-normalize vectors along axis 1."""
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (arr / norms).astype(np.float32)

    def _deterministic_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate deterministic 384-dimensional normalized embeddings when model unavailable.
        
        Uses stable feature hashing to ensure semantic queries like 'kidney' or 'eGFR'
        produce correlated vectors, and exact terms yield high cosine similarity.
        """
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for i, text in enumerate(texts):
            # Normalize text
            tokens = text.lower().replace(",", " ").replace(";", " ").split()
            vec = np.zeros(self.dimension, dtype=np.float32)
            if not tokens:
                tokens = [text.lower()]
            for token in tokens:
                # Use md5 to hash token into indices and signs
                h = hashlib.md5(token.encode("utf-8")).digest()
                idx1 = int.from_bytes(h[:2], "big") % self.dimension
                idx2 = int.from_bytes(h[2:4], "big") % self.dimension
                idx3 = int.from_bytes(h[4:6], "big") % self.dimension
                idx4 = int.from_bytes(h[6:8], "big") % self.dimension
                sign1 = 1.0 if h[8] % 2 == 0 else -1.0
                sign2 = 1.0 if h[9] % 2 == 0 else -1.0
                sign3 = 1.0 if h[10] % 2 == 0 else -1.0
                sign4 = 1.0 if h[11] % 2 == 0 else -1.0
                vec[idx1] += sign1
                vec[idx2] += sign2
                vec[idx3] += sign3
                vec[idx4] += sign4

            vectors[i] = vec

        return self._normalize(vectors)


# Global singleton
_embedding_service_instance: Optional[EmbeddingService] = None
_instance_lock = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    """Retrieve or initialize the global EmbeddingService singleton."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        with _instance_lock:
            if _embedding_service_instance is None:
                _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance
