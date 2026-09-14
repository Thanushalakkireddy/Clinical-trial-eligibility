"""Metadata store for persisting chunk metadata alongside FAISS indices.

Persists chunk metadata to:
    storage/faiss/<trial_id>/metadata.json

Sanitizes trial_id to prevent directory traversal or invalid path characters.
Preserves exact 1:1 mapping between FAISS vector row index and ProtocolChunk metadata.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from app.schemas.rag import ProtocolChunk

logger = logging.getLogger(__name__)

DEFAULT_FAISS_STORAGE_BASE = Path("./storage/faiss")


def sanitize_trial_id(trial_id: str) -> str:
    """Sanitize trial_id for safe filesystem paths.
    
    Replaces any character that is not alphanumeric, hyphen, or underscore with '_'.
    Prevents path traversal attacks (e.g. '../', '/').
    """
    if not trial_id or not trial_id.strip():
        return "UNKNOWN_TRIAL"
    # Strip leading/trailing whitespaces and path separators
    cleaned = trial_id.strip().replace("/", "_").replace("\\", "_")
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", cleaned)
    # Prevent empty or dot-only names
    if not cleaned or cleaned.replace("_", "").replace("-", "") == "":
        return "TRIAL"
    return cleaned


class MetadataStore:
    """Manages serialization and retrieval of ProtocolChunk metadata for each trial."""

    def __init__(self, base_dir: Path = DEFAULT_FAISS_STORAGE_BASE) -> None:
        self.base_dir = Path(base_dir)

    def get_trial_dir(self, trial_id: str) -> Path:
        """Return the directory path for a trial's FAISS and metadata storage."""
        safe_id = sanitize_trial_id(trial_id)
        return self.base_dir / safe_id

    def get_metadata_path(self, trial_id: str) -> Path:
        """Return path to metadata.json for the specified trial."""
        return self.get_trial_dir(trial_id) / "metadata.json"

    def exists(self, trial_id: str) -> bool:
        """Check if metadata exists for the given trial."""
        return self.get_metadata_path(trial_id).is_file()

    def save(self, trial_id: str, chunks: List[ProtocolChunk]) -> Path:
        """Save list of chunks as metadata.json for the specified trial.
        
        Args:
            trial_id: Clinical trial identifier.
            chunks: List of ProtocolChunk instances matching the FAISS index order.
            
        Returns:
            Path to the written metadata.json file.
        """
        trial_dir = self.get_trial_dir(trial_id)
        trial_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.get_metadata_path(trial_id)

        data = {
            "trial_id": trial_id,
            "count": len(chunks),
            "chunks": [chunk.model_dump() for chunk in chunks],
        }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Saved %d metadata chunks for trial %s at %s", len(chunks), trial_id, meta_path)
        return meta_path

    def load(self, trial_id: str) -> List[ProtocolChunk]:
        """Load list of chunks for the specified trial.
        
        Args:
            trial_id: Clinical trial identifier.
            
        Returns:
            List of ProtocolChunk instances matching the FAISS index order.
            Returns empty list if file not found.
        """
        meta_path = self.get_metadata_path(trial_id)
        if not meta_path.is_file():
            logger.warning("Metadata file not found for trial %s at %s", trial_id, meta_path)
            return []

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_chunks = data.get("chunks", [])
            chunks = [ProtocolChunk(**c) for c in raw_chunks]
            return chunks
        except Exception as e:
            logger.error("Failed to load metadata for trial %s: %s", trial_id, e)
            return []

    def clear(self, trial_id: str) -> bool:
        """Delete metadata file for the specified trial."""
        meta_path = self.get_metadata_path(trial_id)
        if meta_path.is_file():
            meta_path.unlink()
            return True
        return False
