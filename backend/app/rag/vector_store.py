"""FAISS vector store for clinical trial eligibility criteria.

Uses IndexFlatIP(384) with L2-normalized embeddings to perform exact maximum inner product
search (equivalent to cosine similarity).

Enforces trial isolation by keeping dedicated, trial-specific indices:
    storage/faiss/<trial_id>/index.faiss
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

from app.rag.embeddings import EMBEDDING_DIMENSION
from app.rag.metadata_store import DEFAULT_FAISS_STORAGE_BASE, sanitize_trial_id

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """Manages trial-isolated FAISS indices."""

    def __init__(self, base_dir: Path = DEFAULT_FAISS_STORAGE_BASE) -> None:
        self.base_dir = Path(base_dir)
        self._faiss_available = self._check_faiss()

    def _check_faiss(self) -> bool:
        """Check if faiss library is importable."""
        try:
            import faiss
            return True
        except ImportError:
            logger.warning("faiss is not installed; vector store will use numpy cosine fallback.")
            return False

    def get_trial_dir(self, trial_id: str) -> Path:
        """Get storage directory path for a specific trial."""
        safe_id = sanitize_trial_id(trial_id)
        return self.base_dir / safe_id

    def get_index_path(self, trial_id: str) -> Path:
        """Get path to the FAISS index file for a specific trial."""
        return self.get_trial_dir(trial_id) / "index.faiss"

    def get_npy_path(self, trial_id: str) -> Path:
        """Fallback numpy storage path."""
        return self.get_trial_dir(trial_id) / "index.npy"

    def exists(self, trial_id: str) -> bool:
        """Check if an index exists for the trial."""
        return self.get_index_path(trial_id).is_file() or self.get_npy_path(trial_id).is_file()

    def index_vectors(self, trial_id: str, vectors: np.ndarray) -> Path:
        """Create and persist an IndexFlatIP index for the trial.
        
        Args:
            trial_id: Clinical trial identifier.
            vectors: (N, 384) array of float32 normalized vectors.
            
        Returns:
            Path to the saved index file.
        """
        trial_dir = self.get_trial_dir(trial_id)
        trial_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.get_index_path(trial_id)

        if vectors.ndim != 2:
            raise ValueError(f"Expected 2D vector array, got shape {vectors.shape}")
        if vectors.shape[1] != EMBEDDING_DIMENSION:
            raise ValueError(f"Expected embedding dimension {EMBEDDING_DIMENSION}, got {vectors.shape[1]}")

        vectors = np.ascontiguousarray(vectors, dtype=np.float32)

        if self._faiss_available:
            import faiss
            index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
            if vectors.shape[0] > 0:
                index.add(vectors)
            faiss.write_index(index, str(index_path))
            logger.info("Saved FAISS index with %d vectors to %s", index.ntotal, index_path)
            return index_path
        else:
            # Fallback numpy persistence
            npy_path = self.get_npy_path(trial_id)
            np.save(str(npy_path), vectors)
            logger.info("Saved fallback numpy vectors to %s", npy_path)
            return npy_path

    def load_index(self, trial_id: str):
        """Load the FAISS index for a specific trial."""
        index_path = self.get_index_path(trial_id)
        if self._faiss_available and index_path.is_file():
            import faiss
            try:
                return faiss.read_index(str(index_path))
            except Exception as e:
                logger.error("Failed to read FAISS index at %s: %s", index_path, e)
                return None
        return None

    def search(
        self, trial_id: str, query_vector: np.ndarray, top_k: int = 5
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Search the trial's index with a normalized query vector.
        
        Args:
            trial_id: Trial identifier (strict trial isolation).
            query_vector: (1, 384) or (384,) normalized float32 vector.
            top_k: Number of nearest neighbors to retrieve.
            
        Returns:
            Tuple of (scores, indices) where scores are cosine similarities.
            Returns empty arrays if trial index does not exist.
        """
        if top_k <= 0:
            return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)

        query_vector = np.ascontiguousarray(query_vector, dtype=np.float32)
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        index_path = self.get_index_path(trial_id)
        npy_path = self.get_npy_path(trial_id)

        # Real FAISS search
        if self._faiss_available and index_path.is_file():
            import faiss
            index = faiss.read_index(str(index_path))
            if index.ntotal == 0:
                return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)
            k = min(top_k, index.ntotal)
            scores, indices = index.search(query_vector, k)
            return scores, indices

        # Fallback numpy cosine similarity
        if npy_path.is_file():
            stored_vectors = np.load(str(npy_path))
            if stored_vectors.shape[0] == 0:
                return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)
            # Dot product with normalized vectors gives cosine similarity
            sims = np.dot(stored_vectors, query_vector.T).flatten()  # shape (N,)
            k = min(top_k, len(sims))
            sorted_indices = np.argsort(-sims)[:k]
            scores = sims[sorted_indices].reshape(1, -1)
            indices = sorted_indices.reshape(1, -1)
            return scores, indices

        # Trial not indexed
        return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)

    def delete_index(self, trial_id: str) -> bool:
        """Delete vector index files for the trial."""
        deleted = False
        for p in [self.get_index_path(trial_id), self.get_npy_path(trial_id)]:
            if p.is_file():
                p.unlink()
                deleted = True
        return deleted
