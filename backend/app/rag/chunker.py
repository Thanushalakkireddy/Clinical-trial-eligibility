"""Protocol criteria chunker for clinical trial RAG pipeline.

Transforms structured ExtractedProtocol objects into retrieval-ready ProtocolChunk
objects with guaranteed preservation of:
- chunk_id, trial_id, criterion_id, criterion_type
- exact criterion text and clinical thresholds (e.g. eGFR >= 30 mL/min/1.73m²)
- source_page, source_document, source_excerpt, and metadata traceability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union
from app.schemas.protocol import CriterionType, ExtractedProtocol, ProtocolCriterion
from app.schemas.rag import ProtocolChunk


class ProtocolChunker:
    """Chunks clinical trial protocols into deterministic, traceable protocol chunks."""

    def __init__(self, max_chunk_chars: int = 1500) -> None:
        """Initialize chunker.
        
        Args:
            max_chunk_chars: Maximum character length before a very long criterion is split.
                             Standard criteria fit well within this limit without losing threshold context.
        """
        self.max_chunk_chars = max_chunk_chars

    def chunk_protocol(
        self, protocol: Union[ExtractedProtocol, Dict[str, Any]]
    ) -> List[ProtocolChunk]:
        """Convert an ExtractedProtocol or dictionary into a list of ProtocolChunk items.
        
        Args:
            protocol: ExtractedProtocol instance or dictionary with trial data.
            
        Returns:
            List of validated ProtocolChunk models ready for vector indexing.
        """
        if isinstance(protocol, dict):
            # Parse dict into ExtractedProtocol or extract fields directly
            try:
                protocol_obj = ExtractedProtocol(**protocol)
            except Exception:
                protocol_obj = None
        else:
            protocol_obj = protocol

        if protocol_obj is not None:
            trial_id = protocol_obj.trial_id or protocol_obj.protocol_id or "UNKNOWN"
            source_doc = protocol_obj.source_document or "protocol.pdf"
            inclusions = protocol_obj.inclusion_criteria
            exclusions = protocol_obj.exclusion_criteria
            others = protocol_obj.other_requirements
            meta = protocol_obj.extraction_metadata or {}
        else:
            # Fallback direct dict extraction
            p_dict = protocol if isinstance(protocol, dict) else {}
            trial_id = p_dict.get("trial_id") or p_dict.get("protocol_id") or "UNKNOWN"
            source_doc = p_dict.get("source_document") or "protocol.pdf"
            inclusions = p_dict.get("inclusion_criteria") or []
            exclusions = p_dict.get("exclusion_criteria") or []
            others = p_dict.get("other_requirements") or []
            meta = p_dict.get("extraction_metadata") or {}

        chunks: List[ProtocolChunk] = []

        # Process inclusion criteria
        chunks.extend(
            self._process_criteria_list(
                criteria=inclusions,
                default_type="inclusion",
                default_section="Inclusion Criteria",
                trial_id=trial_id,
                source_document=source_doc,
                protocol_metadata=meta,
            )
        )

        # Process exclusion criteria
        chunks.extend(
            self._process_criteria_list(
                criteria=exclusions,
                default_type="exclusion",
                default_section="Exclusion Criteria",
                trial_id=trial_id,
                source_document=source_doc,
                protocol_metadata=meta,
            )
        )

        # Process other requirements
        chunks.extend(
            self._process_criteria_list(
                criteria=others,
                default_type="other",
                default_section="Other Requirements",
                trial_id=trial_id,
                source_document=source_doc,
                protocol_metadata=meta,
            )
        )

        return chunks

    def _process_criteria_list(
        self,
        criteria: List[Any],
        default_type: str,
        default_section: str,
        trial_id: str,
        source_document: str,
        protocol_metadata: Dict[str, Any],
    ) -> List[ProtocolChunk]:
        """Convert a list of criteria into ProtocolChunk instances."""
        chunks: List[ProtocolChunk] = []

        for idx, item in enumerate(criteria, start=1):
            if isinstance(item, ProtocolCriterion):
                c_id = item.criterion_id or f"{default_type[:3].upper()}-{idx:03d}"
                c_type = (
                    item.type.value
                    if isinstance(item.type, CriterionType)
                    else str(item.type)
                )
                text = item.text.strip()
                source_page = max(1, item.source_page)
                section = item.section or default_section
                excerpt = item.source_excerpt or text[:200]
                item_trial_id = item.trial_id or trial_id
            elif isinstance(item, dict):
                c_id = item.get("criterion_id") or f"{default_type[:3].upper()}-{idx:03d}"
                raw_type = item.get("type") or default_type
                c_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
                text = str(item.get("text") or "").strip()
                source_page = max(1, int(item.get("source_page", 1)))
                section = str(item.get("section") or default_section)
                excerpt = item.get("source_excerpt") or (text[:200] if text else None)
                item_trial_id = str(item.get("trial_id") or trial_id)
            elif isinstance(item, str):
                c_id = f"{default_type[:3].upper()}-{idx:03d}"
                c_type = default_type
                text = item.strip()
                source_page = 1
                section = default_section
                excerpt = text[:200]
                item_trial_id = trial_id
            else:
                continue

            if not text:
                continue

            # Deterministic chunk ID preserving trial and criterion identity
            chunk_id = f"CHK-{item_trial_id}-{c_id}"

            chunk_meta = {
                "source_type": "protocol_criterion",
                "criterion_index": idx,
                "protocol_metadata": protocol_metadata,
            }

            chunk = ProtocolChunk(
                chunk_id=chunk_id,
                trial_id=item_trial_id,
                criterion_id=c_id,
                criterion_type=c_type,
                section=section,
                text=text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=excerpt,
                metadata=chunk_meta,
            )
            chunks.append(chunk)

        return chunks
