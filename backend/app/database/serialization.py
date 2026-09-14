"""Pydantic <-> persistence serialization helpers.

The application's domain layer stays Pydantic; these helpers produce plain
JSON-compatible structures to store in the database and rebuild Pydantic
models from stored structures. Sensitive values (credentials) are never
included in stored payloads.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


def mint_assessment_id() -> str:
    """Generate a new assessment identifier (UUID v4, 36 chars)."""
    return str(uuid.uuid4())


def serialize_schema(obj: Optional[BaseModel]) -> Optional[dict]:
    """Serialize a Pydantic model to a JSON-safe dict, or None."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return json.loads(json.dumps(obj, default=str))
    if isinstance(obj, list):
        return {
            "items": json.loads(json.dumps([_to_jsonable(i) for i in obj], default=str))
        }
    return json.loads(json.dumps(obj, default=str))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def serialize_evidence(chunks: Optional[List[Any]]) -> List[dict]:
    """Serialize retrieved protocol evidence (RetrievedChunk) to JSON-safe dicts."""
    if not chunks:
        return []
    out: List[dict] = []
    for chunk in chunks:
        data = chunk.model_dump(mode="json") if isinstance(chunk, BaseModel) else chunk
        if isinstance(data, dict):
            out.append(data)
    return out


def encode_json(value: Any) -> str:
    """Encode an arbitrary JSON-safe value to a string for storage."""
    if value is None:
        return "null"
    return json.dumps(value, default=str)


def decode_json(raw: Optional[str], default: Any = None) -> Any:
    """Decode a stored JSON string back to its structured value."""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def build_assessment_snapshot(
    trial_id: str,
    patient_profile_id: str,
    patient_profile: Optional[BaseModel],
    reference_date: Optional[str],
    protocol_evidence: Optional[List[Any]],
    inclusion_assessment: Optional[BaseModel],
    exclusion_assessment: Optional[BaseModel],
    contradiction_assessment: Optional[BaseModel],
    decision_assessment: Optional[BaseModel],
    warnings: Optional[List[str]],
    errors: Optional[List[str]],
    current_step: str,
) -> dict:
    """Build a reproducible snapshot of the workflow result for audit purposes."""
    return {
        "version": "1.0",
        "trial_id": trial_id,
        "patient_profile_id": patient_profile_id,
        "reference_date": reference_date,
        "patient_profile": serialize_schema(patient_profile),
        "protocol_evidence": serialize_evidence(protocol_evidence),
        "inclusion_assessment": serialize_schema(inclusion_assessment),
        "exclusion_assessment": serialize_schema(exclusion_assessment),
        "contradiction_assessment": serialize_schema(contradiction_assessment),
        "decision_assessment": serialize_schema(decision_assessment),
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "current_step": current_step,
    }