"""Tests for Checkpoint 4: LangGraph persistent state / checkpointing.

Coverage (per checkpoint contract):
- checkpointer configuration & backend detection
- workflow thread / run identifier
- checkpoint creation
- checkpoint retrieval
- state recovery at an intermediate checkpoint
- workflow continuation from a saved checkpoint
- cross-assessment (thread) isolation
- no-DATABASE_URL behavior
- checkpoint failure behavior

All persistence tests use an isolated file-based SQLite checkpointer so no
production database is required. State is exercised through the real LangGraph
checkpointer API (ainvoke / aget_state / alist), never by copying a dict.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.checkpoint import (
    checkpoint_backend,
    checkpoint_is_available,
    dispose_checkpointer,
    get_langgraph_checkpointer,
    make_checkpoint_serializer,
)
from app.checkpoint.provider import _sqlite_path
from app.database import session as db_session
from app.graph.state import create_initial_state
from app.graph.workflow import build_workflow, run_workflow
from app.main import create_app
from app.schemas.patient import Demographics, PatientProfile
from app.schemas.rag import RetrievedChunk
from tests.test_workflow import build_eligible_oncology_patient, build_synonc001_evidence


# =============================================================================
# Helpers
# =============================================================================

async def _make_sqlite_saver(path: str):
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    conn = await aiosqlite.connect(path)
    saver = AsyncSqliteSaver(conn, serde=make_checkpoint_serializer())
    await saver.setup()
    return saver


def _patient(profile_id: str, infection: bool | None = False) -> PatientProfile:
    return build_eligible_oncology_patient(
        infection=infection,
        cardiac=False,
        profile_id=profile_id,
    )


def _initial_state(patient: PatientProfile):
    return create_initial_state(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        reference_date="2026-01-15",
        protocol_evidence=build_synonc001_evidence(),
    )


def _skip_if_env_database_url():
    if db_session.get_database_url() is not None:
        pytest.skip("DATABASE_URL is configured in this environment; skipping disabled-mode test.")


# =============================================================================
# 1. Checkpointer configuration
# =============================================================================

def test_checkpoint_serializer_allowlist_roundtrips_app_types():
    serde = make_checkpoint_serializer()
    patient = PatientProfile(
        patient_profile_id="PAT-SERDE",
        demographics=Demographics(age=52),
    )
    chunk = RetrievedChunk(
        chunk_id="C1",
        trial_id="SYN-ONC-001",
        criterion_id="INC-001",
        criterion_type="inclusion",
        text="Age >= 18",
        score=0.9,
        source_page=1,
        source_document="protocol.pdf",
    )
    for obj in (patient, chunk):
        typ, raw = serde.dumps_typed(obj)
        restored = serde.loads_typed((typ, raw))
        # The default serializer restores the original model class.
        assert type(restored) is type(obj)
        assert restored.model_dump() == obj.model_dump()


def test_checkpoint_backend_detection_uses_database_url():
    db_session.dispose_database()
    if db_session.get_database_url() is not None:
        pytest.skip("Environment provides DATABASE_URL; cannot lock-down detection.")
    assert checkpoint_backend() is None
    assert checkpoint_is_available() is False

    try:
        db_session.configure_database("sqlite+aiosqlite:///C:/tmp/ckpt_detect.db")
        assert checkpoint_backend() == "sqlite"
        assert checkpoint_is_available() is True

        db_session.configure_database("postgresql+asyncpg://user:pass@localhost:5432/eligibility")
        assert checkpoint_backend() == "postgres"
        assert checkpoint_is_available() is True

        # Render exposes its PostgreSQL URLs with the `postgres://` scheme.
        db_session.configure_database("postgres://user:pass@localhost:5432/eligibility")
        assert checkpoint_backend() == "postgres"
        assert checkpoint_is_available() is True
    finally:
        db_session.dispose_database()


def test_sqlite_path_extraction():
    assert _sqlite_path("sqlite+aiosqlite:///C:/tmp/ckpt.db") == "C:/tmp/ckpt.db"
    assert _sqlite_path("sqlite:///relative/ckpt.db") == "relative/ckpt.db"
    assert _sqlite_path("sqlite+aiosqlite:///:memory:") == ":memory:"


@pytest.mark.asyncio
async def test_checkpointer_none_when_disabled():
    db_session.dispose_database()
    _skip_if_env_database_url()
    with pytest.raises(RuntimeError):
        db_session.get_engine()
    assert await get_langgraph_checkpointer() is None


# =============================================================================
# 2. Thread / run identifier + checkpoint creation & retrieval
# =============================================================================

@pytest.mark.asyncio
async def test_workflow_thread_id_creates_persistent_checkpoints(tmp_path):
    db_file = os.path.join(tmp_path, "ckpt.db")
    saver = await _make_sqlite_saver(db_file)

    final = await run_workflow(
        _initial_state(_patient("PAT-THREAD")),
        checkpointer=saver,
        thread_id="ASSESS-THREAD-1",
    )
    assert final["decision_assessment"].final_status.value == "ELIGIBLE"

    con = sqlite3.connect(db_file)
    try:
        rows = con.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id=?", ("ASSESS-THREAD-1",)
        ).fetchall()
    finally:
        con.close()
    assert rows, "checkpoint rows must exist for the provided thread_id"

    await saver.conn.close()


@pytest.mark.asyncio
async def test_checkpoint_retrieval_after_full_run(tmp_path):
    saver = await _make_sqlite_saver(os.path.join(tmp_path, "ckpt.db"))
    graph = build_workflow(checkpointer=saver)
    config = {"configurable": {"thread_id": "ASSESS-FULL-1"}}

    final = await graph.ainvoke(_initial_state(_patient("PAT-FULL")), config)
    assert final["decision_assessment"].final_status.value == "ELIGIBLE"

    snapshot = await graph.aget_state(config)
    assert snapshot.values["trial_id"] == "SYN-ONC-001"
    assert snapshot.values["patient_profile_id"] == "PAT-FULL"
    assert snapshot.values["inclusion_assessment"] is not None
    assert snapshot.values["decision_assessment"].final_status.value == "ELIGIBLE"
    assert list(snapshot.next) == []

    await saver.conn.close()


# =============================================================================
# 3. State recovery + workflow continuation (real checkpointer, no dict copy)
# =============================================================================

@pytest.mark.asyncio
async def test_state_recovery_at_intermediate_checkpoint(tmp_path):
    """Interrupt mid-run, save (real checkpointer), then recover the state."""
    saver = await _make_sqlite_saver(os.path.join(tmp_path, "ckpt.db"))
    graph = build_workflow(checkpointer=saver)
    config = {"configurable": {"thread_id": "ASSESS-RECOVERY-1"}}

    interrupted = await graph.ainvoke(
        _initial_state(_patient("PAT-RECOVERY")),
        config,
        interrupt_before=["inclusion"],
    )
    assert interrupted["inclusion_assessment"] is None

    saved = await graph.aget_state(config)
    # The real checkpointer must report the pending node and keep key fields.
    assert saved.next == ("inclusion",)
    assert saved.values["trial_id"] == "SYN-ONC-001"
    assert saved.values["patient_profile"].patient_profile_id == "PAT-RECOVERY"
    assert saved.values["patient_profile"].demographics.age > 0
    assert saved.values["inclusion_assessment"] is None
    assert saved.values["decision_assessment"] is None
    assert len(saved.values["protocol_evidence"]) == 9

    await saver.conn.close()


@pytest.mark.asyncio
async def test_workflow_continuation_reaches_terminal_decision(tmp_path):
    """Resume from the saved intermediate checkpoint to the terminal decision."""
    saver = await _make_sqlite_saver(os.path.join(tmp_path, "ckpt.db"))
    config = {"configurable": {"thread_id": "ASSESS-RESUME-1"}}

    graph = build_workflow(checkpointer=saver)
    await graph.ainvoke(
        _initial_state(_patient("PAT-RESUME")),
        config,
        interrupt_before=["inclusion"],
    )

    # A freshly compiled graph bound to the same saver continues the thread
    # from where it stopped — state is read from the checkpointer, not memory.
    graph_resumed = build_workflow(checkpointer=saver)
    resumed = await graph_resumed.ainvoke(None, config)

    assert resumed["current_step"] == "decision"
    assert resumed["errors"] == []
    assert resumed["inclusion_assessment"] is not None
    assert resumed["exclusion_assessment"] is not None
    assert resumed["contradiction_assessment"] is not None
    assert resumed["decision_assessment"].final_status.value == "ELIGIBLE"

    await saver.conn.close()


# =============================================================================
# 4. Assessment isolation across threads
# =============================================================================

@pytest.mark.asyncio
async def test_assessment_isolation_between_threads(tmp_path):
    saver = await _make_sqlite_saver(os.path.join(tmp_path, "ckpt.db"))
    graph = build_workflow(checkpointer=saver)

    config_a = {"configurable": {"thread_id": "ASSESS-A"}}
    state_a = await graph.ainvoke(_initial_state(_patient("PAT-A")), config_a)
    assert state_a["decision_assessment"].final_status.value == "ELIGIBLE"

    config_b = {"configurable": {"thread_id": "ASSESS-B"}}
    state_b = await graph.ainvoke(
        _initial_state(_patient("PAT-B", infection=True)), config_b
    )
    assert state_b["decision_assessment"].final_status.value == "NOT_ELIGIBLE"
    assert state_b["patient_profile_id"] == "PAT-B"

    snapshot_a = await graph.aget_state(config_a)
    assert snapshot_a.values["patient_profile_id"] == "PAT-A"
    assert snapshot_a.values["inclusion_assessment"].overall_status.value == "PASS"
    assert snapshot_a.values["decision_assessment"].final_status.value == "ELIGIBLE"
    exc_a = snapshot_a.values["exclusion_assessment"]
    assert any(c.criterion_id == "EXC-001" for c in exc_a.criteria)

    # Assessment B's more-information-required fields never leak into A.
    assert exc_a.missing_information == []

    await saver.conn.close()


# =============================================================================
# 5. No DATABASE_URL: deterministic workflow un-changed
# =============================================================================

@pytest.mark.asyncio
async def test_no_database_url_deterministic_workflow_still_works():
    db_session.dispose_database()
    _skip_if_env_database_url()

    assert await get_langgraph_checkpointer() is None

    final = await run_workflow(_initial_state(_patient("PAT-NO-DB")), thread_id="GHOST")
    assert final["errors"] == []
    assert final["decision_assessment"].final_status.value == "ELIGIBLE"


# =============================================================================
# 6. Endpoint integration (checkpointer == assessment_id == thread_id)
# =============================================================================

@pytest_asyncio.fixture
async def ckpt_endpoint_db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/ckpt_e2e.db"
    db_session.configure_database(url)
    await db_session.create_schema()
    yield url, tmp_path
    db_session.dispose_database()
    await dispose_checkpointer()


def _workflow_payload(patient: PatientProfile):
    return {
        "trial_id": "SYN-ONC-001",
        "patient_profile": patient.model_dump(mode="json"),
        "protocol_evidence": [c.model_dump(mode="json") for c in build_synonc001_evidence()],
        "reference_date": "2026-01-15",
    }


@pytest.mark.asyncio
async def test_endpoint_uses_assessment_id_as_thread_id(ckpt_endpoint_db):
    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-API"))
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == []
    assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
    assert len(data["assessment_id"]) == 36

    saver = await get_langgraph_checkpointer()
    assert saver is not None
    checkpoints = [
        c async for c in saver.alist({"configurable": {"thread_id": data["assessment_id"]}})
    ]
    assert checkpoints, "endpoint must persist checkpoints under assessment_id as thread_id"


@pytest.mark.asyncio
async def test_endpoint_checkpoint_setup_failure_still_returns_decision(
    ckpt_endpoint_db, monkeypatch
):
    """Checkpoint setup failure must not change the eligibility decision."""
    async def failing_setup():
        raise RuntimeError("checkpoint database unreachable")

    monkeypatch.setattr("app.routers.workflow.get_langgraph_checkpointer", failing_setup)

    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-DEGRADE"))
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
    assert data["assessment_id"] is not None
    assert any("checkpointing" in w.lower() for w in data["warnings"])


@pytest.mark.asyncio
async def test_endpoint_checkpoint_write_failure_marks_failed_no_decision(
    ckpt_endpoint_db, monkeypatch, tmp_path
):
    """A failing checkpointer must not fabricate a decision; run is marked FAILED."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    class FailingSaver(AsyncSqliteSaver):
        async def aput(self, *args, **kwargs):
            raise RuntimeError("checkpoint write failed")

    conn = await aiosqlite.connect(os.path.join(tmp_path, "failing.db"))
    failing = FailingSaver(conn, serde=make_checkpoint_serializer())
    await failing.setup()

    async def provide_failing():
        return failing

    monkeypatch.setattr("app.routers.workflow.get_langgraph_checkpointer", provide_failing)

    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/workflow/evaluate", json=_workflow_payload(_patient("PAT-FAIL"))
        )

    assert resp.status_code == 500
    body = resp.json()
    assert "decision_assessment" not in body
    assert "detail" in body

    # The existing assessment record is marked FAILED (persistence preserved).
    from app.database import repository
    from app.database.serialization import decode_json

    session_maker = db_session.get_session_maker()
    async with session_maker() as session:
        rows = await repository.list_assessments(session, limit=10)
        assert rows
        record = await repository.get_assessment(session, rows[0].assessment_id)
        assert record.workflow_status == "FAILED"
        assert decode_json(record.errors_json)

    await conn.close()