"""Checkpoint serializer for workflow state.

LangGraph's default ``JsonPlusSerializer`` encodes Pydantic models and restores
them as the original model classes when a checkpoint is read back, which keeps
graph nodes working with real typed objects after a resume. (An explicit
``allowed_msgpack_modules`` allowlist was evaluated, but it degraded Pydantic
models to plain dicts on deserialize, so the default serializer is used.)
"""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def make_checkpoint_serializer() -> JsonPlusSerializer:
    """Return the default checkpoint serializer used by every checkpointer."""
    return JsonPlusSerializer()