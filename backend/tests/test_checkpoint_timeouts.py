"""Checkpoint 8A regression tests: bounded checkpointer/DB/Gemini timeouts.

Verifies that the LangGraph PostgreSQL checkpointer connection and setup cannot
hang a request indefinitely, that failures degrade to the existing deterministic
fallback without fabricating a decision, that a healthy checkpointer is reused
(not rebuilt per request), that thread_id stays equal to assessment_id, and that
assessment isolation is preserved.

All failure/timeout tests use fakes/mocks — never a live PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.checkpoint import dispose_checkpointer, get_langgraph_checkpointer
from app.database import session as db_session
from app.main import create_app
from tests.test_workflow import build_eligible_oncology_patient, build_synonc001_evidence


# =============================================================================
# Helpers
# =============================================================================

def _postgres_url() -> str:
    return "postgres://user:pass@localhost:5432/eligibility"


def _patient(profile_id: str):
    return build_eligible_oncology_patient(
        infection=False,
        cardiac=False,
        profile_id=profile_id,
    )


def _workflow_payload(patient):
    return {
        "trial_id": "SYN-ONC-001",
        "patient_profile": patient.model_dump(mode="json"),
        "protocol_evidence": [c.model_dump(mode="json") for c in build_synonc001_evidence()],
        "reference_date": "2026-01-15",
    }


@pytest_asyncio.fixture
async def sqlite_ckpt_db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/ckpt_8a.db"
    db_session.configure_database(url)
    await db_session.create_schema()
    yield url
    db_session.dispose_database()
    await dispose_checkpointer()


# =============================================================================
# A. PostgreSQL checkpointer connection timeout
# =============================================================================

@pytest.mark.asyncio
async def test_postgres_checkpointer_connect_is_bounded(monkeypatch):
    db_session.configure_database(_postgres_url())
    monkeypatch.setattr("app.config.settings.checkpointer_connect_timeout_seconds", 1)
    monkeypatch.setattr("app.config.settings.checkpointer_setup_timeout_seconds", 5)

    async def slow_connect(*args, **kwargs):
        await asyncio.sleep(30)
        raise AssertionError("connect should have been cancelled by the timeout")

    monkeypatch.setattr("psycopg.AsyncConnection.connect", slow_connect)

    try:
        start = time.perf_counter()
        with pytest.raises(asyncio.TimeoutError):
            await get_langgraph_checkpointer()
        elapsed = time.perf_counter() - start
        assert elapsed < 5, "connect timeout must fail fast, not hang for minutes"
    finally:
        db_session.dispose_database()
        await dispose_checkpointer()


# =============================================================================
# B. Checkpointer setup timeout
# =============================================================================

class _FakeConn:
    close_called = False

    async def close(self):
        _FakeConn.close_called = True


class _SlowSetupSaver:
    def __init__(self, conn, serde=None):
        self.conn = conn

    async def setup(self):
        await asyncio.sleep(30)


class _HealthySaver:
    setup_calls = 0

    def __init__(self, conn, serde=None):
        self.conn = conn

    async def setup(self):
        type(self).setup_calls += 1

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_postgres_checkpointer_setup_is_bounded(monkeypatch):
    db_session.configure_database(_postgres_url())
    monkeypatch.setattr("app.config.settings.checkpointer_connect_timeout_seconds", 5)
    monkeypatch.setattr("app.config.settings.checkpointer_setup_timeout_seconds", 1)

    async def fake_connect(*args, **kwargs):
        return _FakeConn()

    monkeypatch.setattr("psycopg.AsyncConnection.connect", fake_connect)
    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", _SlowSetupSaver
    )

    try:
        start = time.perf_counter()
        with pytest.raises(asyncio.TimeoutError):
            await get_langgraph_checkpointer()
        elapsed = time.perf_counter() - start
        assert elapsed < 5, "setup timeout must fail fast, not hang for minutes"
        assert _FakeConn.close_called, "connection must be closed after a setup timeout"
    finally:
        db_session.dispose_database()
        await dispose_checkpointer()


# =============================================================================
# E. Healthy PostgreSQL checkpointer still works (simulated) + reuse + timeout plumbing
# =============================================================================

@pytest.mark.asyncio
async def test_postgres_checkpointer_healthy_and_reused(monkeypatch):
    await dispose_checkpointer()
    db_session.configure_database(_postgres_url())
    monkeypatch.setattr("app.config.settings.checkpointer_connect_timeout_seconds", 5)
    monkeypatch.setattr("app.config.settings.checkpointer_setup_timeout_seconds", 5)

    captured_kwargs = {}

    async def fake_connect(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return _FakeConn()

    monkeypatch.setattr("psycopg.AsyncConnection.connect", fake_connect)
    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", _HealthySaver
    )

    try:
        saver1 = await get_langgraph_checkpointer()
        assert isinstance(saver1, _HealthySaver)
        assert captured_kwargs.get("connect_timeout") == 5, (
            "psycopg connect must receive an explicit connect_timeout"
        )

        saver2 = await get_langgraph_checkpointer()
        assert saver2 is saver1, "healthy checkpointer must be cached and reused"
        assert _HealthySaver.setup_calls == 1, "setup must run only once per process"
    finally:
        db_session.dispose_database()
        await dispose_checkpointer()


# =============================================================================
# C + D. Checkpointer failure does not fabricate a decision; fallback works
# =============================================================================

@pytest.mark.asyncio
async def test_checkpointer_timeout_failure_returns_deterministic_decision(
    sqlite_ckpt_db, monkeypatch
):
    """A setup TimeoutError must degrade to the deterministic run with a warning,
    and must NOT fabricate an eligibility decision."""
    async def timeout_during_setup():
        raise asyncio.TimeoutError("checkpoint setup timed out")

    monkeypatch.setattr("app.routers.workflow.get_langgraph_checkpointer", timeout_during_setup)

    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-TIMEOUT"))
        )
    assert response.status_code == 200
    data = response.json()
    # Real deterministic eligibility still computed (health-check, not fabricated).
    assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
    assert data["errors"] == []
    assert any("checkpointing" in w.lower() for w in data["warnings"])
    # The assessment record was still persisted (fallback remains safe).
    assert len(data["assessment_id"]) == 36


# =============================================================================
# F. Assessment persistence failure behavior
# =============================================================================

@pytest.mark.asyncio
async def test_persistence_start_failure_degrades_cleanly(sqlite_ckpt_db, monkeypatch):
    """persist start failure -> no assessment_id, no checkpointer attempt,
    deterministic decision returned with the configured fallback."""
    calls = {"checkpointer": 0}

    async def boom(*args, **kwargs):
        raise RuntimeError("database unreachable at request start")

    async def spy_checkpointer():
        calls["checkpointer"] += 1
        return None

    monkeypatch.setattr("app.routers.workflow.db_persistence.persist_assessment_start", boom)
    monkeypatch.setattr("app.routers.workflow.get_langgraph_checkpointer", spy_checkpointer)

    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-PERSIST-FAIL"))
        )
    assert response.status_code == 200
    data = response.json()
    assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
    assert data["assessment_id"] is None
    assert calls["checkpointer"] == 0, "checkpointer must be skipped when persistence start fails"


# =============================================================================
# G + H. thread_id == assessment_id and assessment isolation
# =============================================================================

@pytest.mark.asyncio
async def test_thread_id_equals_assessment_id_and_isolation(sqlite_ckpt_db):
    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-ISOLATE-A"))
        )
        second = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-ISOLATE-B"))
        )

    assert first.status_code == 200 and second.status_code == 200
    first_data, second_data = first.json(), second.json()

    # Distinct assessment_ids -> distinct LangGraph threads.
    assert len(first_data["assessment_id"]) == 36
    assert len(second_data["assessment_id"]) == 36
    assert first_data["assessment_id"] != second_data["assessment_id"]

    saver = await get_langgraph_checkpointer()
    assert saver is not None

    threads = set()
    async for c in saver.alist({}):
        threads.add(c["configurable"]["thread_id"])
    # Exactly the two assessment ids, never a shared/generated thread.
    assert threads == {first_data["assessment_id"], second_data["assessment_id"]}

    # Per-thread state stays isolated (read back through the compiled graph).
    from app.graph.workflow import build_workflow

    graph = build_workflow(checkpointer=saver)
    snapshot_a = await graph.aget_state(
        {"configurable": {"thread_id": first_data["assessment_id"]}}
    )
    assert snapshot_a.values["patient_profile_id"] == "PAT-ISOLATE-A"
    snapshot_b = await graph.aget_state(
        {"configurable": {"thread_id": second_data["assessment_id"]}}
    )
    assert snapshot_b.values["patient_profile_id"] == "PAT-ISOLATE-B"