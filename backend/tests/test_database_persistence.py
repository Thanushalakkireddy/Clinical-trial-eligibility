"""Tests for Checkpoint 3: optional persistent database layer.

The suite must never require a production database. Each database test
installs an isolated file-based SQLite database (via aiosqlite) using
configure_database(), creates the schema, and disposes the engine afterwards.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import persistence, repository, serialization, session as db_session
from app.graph.workflow import run_workflow
from app.main import create_app
from app.schemas.rag import RetrievedChunk
from tests.test_workflow import build_eligible_oncology_patient, build_synonc001_evidence


# =============================================================================
# Serialization & URL hygiene (no database required)
# =============================================================================

@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "postgresql+asyncpg://root:s3cret@db.example.com:5432/eligibility",
            "postgresql+asyncpg://root:***@db.example.com:5432/eligibility",
        ),
        (
            "postgresql+asyncpg://root:@db.example.com:5432/eligibility",
            "postgresql+asyncpg://root:***@db.example.com:5432/eligibility",
        ),
        (
            "sqlite+aiosqlite:///C:/tmp/test.db",
            "sqlite+aiosqlite:///C:/tmp/test.db",
        ),
    ],
)
def test_redact_database_url_masks_credentials(url, expected):
    assert db_session.redact_database_url(url) == expected


def test_json_roundtrip_and_assessment_id():
    payload = {"decision": "ELIGIBLE", "flags": [1, 2, 3], "nested": {"a": None}}
    encoded = serialization.encode_json(payload)
    assert isinstance(encoded, str)
    assert serialization.decode_json(encoded) == payload
    assert serialization.decode_json(None) is None
    assert serialization.decode_json("not-json", default="fallback") == "fallback"

    assessment_id = serialization.mint_assessment_id()
    assert len(assessment_id) == 36


def test_serialize_schema_from_pydantic():
    chunk = RetrievedChunk(
        chunk_id="C1",
        trial_id="T1",
        criterion_id="INC-1",
        criterion_type="inclusion",
        text="Age >= 18",
        score=0.9,
        source_page=1,
        source_document="protocol.pdf",
    )
    data = serialization.serialize_evidence([chunk])
    assert data[0]["criterion_id"] == "INC-1"
    assert serialization.serialize_schema(None) is None


# =============================================================================
# Disabled-by-default behavior (only valid when no DATABASE_URL is configured)
# =============================================================================

def _skip_if_persistence_configured():
    if db_session.get_database_url() is not None:
        pytest.skip("DATABASE_URL is configured in this environment; skipping disabled-mode tests.")


def test_persistence_disabled_without_database_url():
    _skip_if_persistence_configured()
    assert db_session.persist_is_configured() is False
    assert persistence.persist_is_enabled() is False
    with pytest.raises(RuntimeError):
        db_session.get_engine()
    with pytest.raises(RuntimeError):
        db_session.get_session_maker()


# =============================================================================
# Database-backed tests (isolated SQLite)
# =============================================================================

@pytest_asyncio.fixture
async def isolated_db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/persist_test.db"
    db_session.configure_database(url)
    await db_session.create_schema()
    yield url
    db_session.dispose_database()


@pytest.mark.asyncio
async def test_schema_tables_created(isolated_db):
    session_maker = db_session.get_session_maker()
    async with session_maker() as session:
        result = await session.execute(
            __import__("sqlalchemy").text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )
        tables = {row[0] for row in result.fetchall()}
    assert {"clinical_trial_protocols", "patient_profiles", "assessment_runs", "assessment_traces"} <= tables


@pytest.mark.asyncio
async def test_repository_protocol_and_patient_reuse(isolated_db):
    session_maker = db_session.get_session_maker()
    async with session_maker() as session:
        protocol = await repository.create_protocol(
            session,
            trial_id="SYN-ONC-001",
            protocol_metadata={"source": "test"},
            source_document="SYN-ONC-001_protocol.pdf",
            source_page_count=1,
            criteria=[{"criterion_id": "INC-001"}],
        )
        assert protocol.trial_id == "SYN-ONC-001"
        patient = await repository.create_patient(
            session,
            patient_profile_id="PAT-1",
            profile_json={"age": 52},
            source_type="api_request",
        )
        assert patient.patient_profile_id == "PAT-1"

        updated = await repository.create_protocol(
            session,
            trial_id="SYN-ONC-001",
            protocol_metadata={"source": "test-2"},
            criteria=[{"criterion_id": "INC-002"}],
        )
        assert updated.source_page_count == 1
        await session.commit()

    async with session_maker() as session:
        fetched = await repository.get_protocol(session, "SYN-ONC-001")
        assert fetched is not None
        assert serialization.decode_json(fetched.criteria)[0]["criterion_id"] == "INC-002"
        assert await repository.get_protocol(session, "NO-SUCH-TRIAL") is None
        patient = await repository.get_patient(session, "PAT-1")
        assert patient.profile_json is not None


@pytest.mark.asyncio
async def test_repository_assessment_and_trace_lifecycle(isolated_db):
    session_maker = db_session.get_session_maker()
    assessment_id = serialization.mint_assessment_id()
    async with session_maker() as session:
        await repository.create_assessment(
            session,
            assessment_id=assessment_id,
            trial_id="SYN-ONC-001",
            patient_profile_id="PAT-1",
            reference_date="2026-01-15",
        )
        await session.commit()

    async with session_maker() as session:
        await repository.update_assessment(
            session,
            assessment_id,
            workflow_status="COMPLETED",
            final_decision="ELIGIBLE",
            current_step="decision",
            warnings=["w1"],
            errors=[],
            snapshot={"k": "v"},
        )
        await repository.save_assessment_traces(
            session,
            assessment_id,
            [
                {"stage": "start", "status": "RUNNING", "payload": {}},
                {"stage": "complete", "status": "COMPLETED", "payload": {"done": True}},
            ],
        )
        await session.commit()

    async with session_maker() as session:
        rec = await repository.get_assessment(session, assessment_id)
        assert rec is not None
        assert rec.workflow_status == "COMPLETED"
        assert rec.final_decision == "ELIGIBLE"
        assert rec.reference_date == "2026-01-15"
        assert serialization.decode_json(rec.warnings_json) == ["w1"]
        traces = await repository.get_assessment_traces(session, assessment_id)
        assert [(t.stage, t.sequence) for t in traces] == [("start", 1), ("complete", 2)]
        assert serialization.decode_json(traces[1].payload_json) == {"done": True}
        assert await repository.get_assessment(session, "missing-id") is None


@pytest.mark.asyncio
async def test_repository_list_assessments_order_and_filters(isolated_db):
    session_maker = db_session.get_session_maker()
    ids = [serialization.mint_assessment_id() for _ in range(3)]
    async with session_maker() as session:
        for aid in ids:
            await repository.create_assessment(
                session,
                assessment_id=aid,
                trial_id="SYN-ONC-001",
                patient_profile_id=f"PAT-{aid[:4]}",
            )
        await session.commit()

    async with session_maker() as session:
        all_rows = await repository.list_assessments(session, limit=10)
        assert {r.assessment_id for r in all_rows} == set(ids)
        filtered = await repository.list_assessments(
            session, trial_id="SYN-ONC-001", patient_profile_id=f"PAT-{ids[0][:4]}"
        )
        assert [r.assessment_id for r in filtered] == [ids[0]]


@pytest.mark.asyncio
async def test_persistence_service_full_assessment_flow(isolated_db):
    """Run the real LangGraph workflow and persist its complete audit trail."""
    patient = build_eligible_oncology_patient(
        infection=False,
        cardiac=False,
        profile_id="SYN-PAT-PERSIST-001",
    )
    evidence = build_synonc001_evidence()

    assessment_id = await persistence.persist_assessment_start(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        reference_date="2026-01-15",
        protocol_evidence=evidence,
    )
    assert assessment_id is not None

    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        reference_date="2026-01-15",
        protocol_evidence=evidence,
    )

    await persistence.persist_assessment_complete(
        assessment_id,
        final_state,
        reference_date="2026-01-15",
    )

    session_maker = db_session.get_session_maker()
    async with session_maker() as session:
        rec = await repository.get_assessment(session, assessment_id)
        assert rec is not None
        assert rec.workflow_status == "COMPLETED"
        assert rec.final_decision == "ELIGIBLE"
        assert rec.current_step == "decision"

        snapshot = serialization.decode_json(rec.snapshot_json)
        assert snapshot["trial_id"] == "SYN-ONC-001"
        assert snapshot["decision_assessment"]["final_status"] == "ELIGIBLE"
        assert len(snapshot["protocol_evidence"]) == 9

        traces = await repository.get_assessment_traces(session, assessment_id)
        stages = [t.stage for t in traces]
        assert stages == ["start", "inclusion", "exclusion", "contradiction", "decision", "complete"]
        assert all(s is not None for s in [t.status for t in traces])

        protocol = await repository.get_protocol(session, "SYN-ONC-001")
        assert protocol is not None
        assert serialization.decode_json(protocol.criteria) is not None
        patient_row = await repository.get_patient(session, "SYN-PAT-PERSIST-001")
        assert patient_row is not None


@pytest.mark.asyncio
async def test_persist_assessment_fail_marks_failure(isolated_db):
    patient = build_eligible_oncology_patient(infection=False, cardiac=False)
    assessment_id = await persistence.persist_assessment_start(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        reference_date=None,
        protocol_evidence=[],
    )
    await persistence.persist_assessment_fail(assessment_id, ["boom"])

    session_maker = db_session.get_session_maker()
    async with session_maker() as session:
        rec = await repository.get_assessment(session, assessment_id)
        assert rec.workflow_status == "FAILED"
        assert serialization.decode_json(rec.errors_json) == ["boom"]


@pytest.mark.asyncio
async def test_persistence_disabled_returns_no_assessment_id(isolated_db):
    """persist_assessment_start must return None when persistence is disabled."""
    db_session.dispose_database()
    if db_session.get_database_url() is not None:
        pytest.skip("Environment has DATABASE_URL; cannot exercise disabled mode.")
    patient = build_eligible_oncology_patient(infection=False, cardiac=False)
    assert await persistence.persist_assessment_start(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        reference_date=None,
        protocol_evidence=[],
    ) is None


# =============================================================================
# Endpoint integration tests
# =============================================================================

def _workflow_payload():
    patient = build_eligible_oncology_patient(
        infection=False,
        cardiac=False,
        profile_id="SYN-PAT-PERSIST-API",
    )
    return {
        "trial_id": "SYN-ONC-001",
        "patient_profile": patient.model_dump(mode="json"),
        "protocol_evidence": [c.model_dump(mode="json") for c in build_synonc001_evidence()],
        "reference_date": "2026-01-15",
    }


@pytest.mark.asyncio
async def test_evaluate_endpoint_persists_assessment_and_api_reads_it(isolated_db):
    app_obj = create_app()
    transport = ASGITransport(app=app_obj)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/workflow/evaluate", json=_workflow_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["errors"] == []
        assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
        assert "assessment_id" in data
        assert len(data["assessment_id"]) == 36

        assessment_id = data["assessment_id"]

        listed = await client.get(
            "/api/v1/assessments",
            params={"trial_id": "SYN-ONC-001", "limit": 5},
        )
        assert listed.status_code == 200
        rows = listed.json()
        assert any(row["assessment_id"] == assessment_id for row in rows)
        summary = next(row for row in rows if row["assessment_id"] == assessment_id)
        assert summary["workflow_status"] == "COMPLETED"
        assert summary["final_decision"] == "ELIGIBLE"

        detail = await client.get(f"/api/v1/assessments/{assessment_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["workflow_status"] == "COMPLETED"
        assert len(body["traces"]) == 6
        assert body["snapshot"]["decision_assessment"]["final_status"] == "ELIGIBLE"

        missing = await client.get("/api/v1/assessments/no-such-assessment")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_endpoint_survives_persistence_update_failure(isolated_db, monkeypatch):
    """A persistence failure must not change the eligibility response."""
    app_obj = create_app()
    transport = ASGITransport(app=app_obj)

    async def boom(*args, **kwargs):
        raise RuntimeError("database dropped mid-run")

    monkeypatch.setattr(persistence, "persist_assessment_complete", boom)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/workflow/evaluate", json=_workflow_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision_assessment"]["final_status"] == "ELIGIBLE"
        assert data["assessment_id"] is not None
        assert any("could not be completed" in w for w in data["warnings"])


@pytest.mark.asyncio
async def test_persistence_api_503_when_disabled(isolated_db):
    db_session.dispose_database()
    if db_session.get_database_url() is not None:
        pytest.skip("Environment still provides DATABASE_URL after dispose; skipping.")
    app_obj = create_app()
    transport = ASGITransport(app=app_obj)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/assessments")
        assert resp.status_code == 503
        assert "DATABASE_URL" in resp.json()["detail"]