"""Security & production-hardening regression tests (Checkpoint 6).

Covers:
1. CORS: default config must not allow a wildcard origin; env-configurable.
2. CORS: preflight from a disallowed origin is not mirrored; a whitelisted
   origin is mirrored with credentials.
3. Security headers are emitted on API responses.
4. Workflow API enforces Pydantic validation (clean 4xx, no internals leaked).
5. Internal failures never leak exception internals in 500 responses.
6. Upload filename sanitization blocks directory traversal.
7. Patient PDF upload is cleaned up after processing (PHI not retained) and
   malformed PDFs return 422 without leaking internals or leaving files.
8. Trial protocol PDF upload cleans up malformed files (no orphaned uploads).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routers.patients import _sanitize_filename as patient_sanitize
from app.routers.trials import _sanitize_filename as trial_sanitize
from app.schemas.exclusion import ExclusionAssessment, ExclusionStatus
from app.schemas.inclusion import InclusionAssessment, InclusionStatus
from app.schemas.patient import PatientProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_patient() -> PatientProfile:
    return PatientProfile(patient_profile_id="PAT-SEC-001")


def make_decision_payload() -> dict:
    return {
        "trial_id": "TRIAL-SEC-001",
        "patient_profile": make_patient().model_dump(),
        "inclusion_assessment": InclusionAssessment(
            trial_id="TRIAL-SEC-001",
            patient_profile_id="PAT-SEC-001",
            overall_status=InclusionStatus.PASS,
            criteria=[],
            missing_information=[],
            warnings=[],
        ).model_dump(),
        "exclusion_assessment": ExclusionAssessment(
            trial_id="TRIAL-SEC-001",
            patient_profile_id="PAT-SEC-001",
            overall_status=ExclusionStatus.CLEAR,
            criteria=[],
            missing_information=[],
            warnings=[],
        ).model_dump(),
    }


def make_pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Security regression test PDF")
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------------------
# 1 & 2. CORS
# ---------------------------------------------------------------------------

def test_cors_default_has_no_wildcard():
    assert "*" not in Settings().cors_origins


def test_cors_is_environment_configurable(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://care.example.com"]')
    assert Settings().cors_origins == ["https://care.example.com"]
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com,https://b.example.com")
    assert Settings().cors_origins == ["https://a.example.com", "https://b.example.com"]
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert Settings().cors_origins == []


def test_cors_allowed_origin_is_mirrored_with_credentials(client: TestClient):
    resp = client.options(
        "/api/v1/assessments",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_disallowed_origin_is_rejected(client: TestClient):
    resp = client.options(
        "/api/v1/assessments",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") in (None, "")


# ---------------------------------------------------------------------------
# 3. Security headers
# ---------------------------------------------------------------------------

def test_security_headers_present(client: TestClient):
    resp = client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
    assert resp.headers.get("referrer-policy") == "same-origin"


# ---------------------------------------------------------------------------
# 4. Pydantic validation for workflow requests
# ---------------------------------------------------------------------------

def test_workflow_evaluate_rejects_malformed_payload(client: TestClient):
    # Missing required patient_profile -> clean 422 from Pydantic.
    resp = client.post("/api/v1/workflow/evaluate", json={"trial_id": "TRIAL-SEC-001"})
    assert resp.status_code == 422
    body = resp.text.lower()
    assert "stack" not in body
    assert "traceback" not in body


def test_workflow_evaluate_rejects_garbage_body(client: TestClient):
    resp = client.post(
        "/api/v1/workflow/evaluate",
        content="not-json-at-all",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code in (400, 422)


def test_decision_validation_rejects_bad_status(client: TestClient):
    payload = make_decision_payload()
    payload["inclusion_assessment"]["overall_status"] = "MADE_UP_STATUS"
    resp = client.post("/api/v1/decision/evaluate", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Internal exception detail is never leaked
# ---------------------------------------------------------------------------

def test_rag_index_internal_failure_does_not_leak_internals(client: TestClient, monkeypatch):
    class Boom:
        def index_protocol(self, protocol, trial_id=None):
            raise RuntimeError("secret-internal-token-xyz")

    monkeypatch.setattr("app.routers.rag.get_rag_service", lambda: Boom())
    resp = client.post(
        "/api/v1/rag/index",
        json={"trial_id": "TRIAL-SEC-001", "protocol": {"trial_id": "TRIAL-SEC-001"}},
    )
    assert resp.status_code == 500
    assert "secret-internal-token-xyz" not in resp.text


def test_decision_internal_failure_does_not_leak_internals(client: TestClient, monkeypatch):
    from app.agents.decision_reviewer_agent import DecisionReviewerAgent

    def boom(self, **kwargs):
        raise RuntimeError("secret-internal-token-xyz")

    monkeypatch.setattr(DecisionReviewerAgent, "evaluate", boom)
    resp = client.post("/api/v1/decision/evaluate", json=make_decision_payload())
    assert resp.status_code == 500
    assert "secret-internal-token-xyz" not in resp.text


def test_patient_upload_failure_does_not_leak_internals(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.pdf_storage_dir", str(tmp_path / "storage" / "pdfs"))

    async def boom(self, pdf_doc):
        raise RuntimeError("secret-internal-token-xyz")

    monkeypatch.setattr("app.routers.patients.PatientProfileAgent.process_pdf", boom)
    resp = client.post(
        "/api/v1/patients/extract-profile",
        files={"file": ("record.pdf", make_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 500
    assert "secret-internal-token-xyz" not in resp.text


# ---------------------------------------------------------------------------
# 6. Filename sanitization (path traversal)
# ---------------------------------------------------------------------------

def test_patient_filename_sanitization_blocks_traversal():
    assert "/" not in patient_sanitize("../../etc/passwd.pdf")
    assert "\\" not in patient_sanitize("..\\..\\etc\\passwd.pdf")
    assert patient_sanitize("../../etc/passwd.pdf") == "passwd.pdf"
    assert patient_sanitize('"><script>.pdf') == "___script_.pdf"
    assert patient_sanitize("normal_record.pdf") == "normal_record.pdf"
    assert patient_sanitize("..") == "patient_record.pdf"
    assert patient_sanitize(".") == "patient_record.pdf"


def test_trial_filename_sanitization_blocks_traversal():
    assert "/" not in trial_sanitize("../../etc/passwd.pdf")
    assert "\\" not in trial_sanitize("..\\..\\etc\\passwd.pdf")
    assert trial_sanitize("../../etc/passwd.pdf") == "passwd.pdf"
    assert trial_sanitize("..") == "protocol.pdf"


# ---------------------------------------------------------------------------
# 7. Patient PDF cleanup (PHI not retained)
# ---------------------------------------------------------------------------

def test_patient_pdf_upload_removes_document_after_success(client: TestClient, monkeypatch, tmp_path):
    storage = tmp_path / "storage" / "pdfs"
    monkeypatch.setattr("app.config.settings.pdf_storage_dir", str(storage))
    from app.schemas.patient import ExtractedPatientResult

    async def fake_process_pdf(self, pdf_doc):
        return ExtractedPatientResult(
            patient_profile_id="PAT-SEC-001",
            profile=make_patient(),
            missing_information=[],
            evidence=[],
            source_type="patient_pdf",
        )

    monkeypatch.setattr("app.routers.patients.PatientProfileAgent.process_pdf", fake_process_pdf)
    resp = client.post(
        "/api/v1/patients/extract-profile",
        files={"file": ("phi_patient.pdf", make_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    files_left = list(storage.rglob("*.pdf"))
    assert files_left == []


def test_patient_pdf_malformed_returns_422_and_cleans_up(client: TestClient, monkeypatch, tmp_path):
    storage = tmp_path / "storage" / "pdfs"
    monkeypatch.setattr("app.config.settings.pdf_storage_dir", str(storage))
    resp = client.post(
        "/api/v1/patients/extract-profile",
        files={"file": ("not_a_pdf.pdf", b"this is definitely not pdf content", "application/pdf")},
    )
    assert resp.status_code == 422
    assert "secret" not in resp.text.lower()
    assert list(storage.rglob("*.pdf")) == []


# ---------------------------------------------------------------------------
# 8. Trial protocol PDF cleanup on malformed upload
# ---------------------------------------------------------------------------

def test_trial_protocol_malformed_pdf_returns_422_and_cleans_up(client: TestClient, monkeypatch, tmp_path):
    storage = tmp_path / "storage" / "pdfs"
    monkeypatch.setattr("app.config.settings.pdf_storage_dir", str(storage))
    resp = client.post(
        "/api/v1/trials/TRIAL-SEC-001/extract-protocol",
        files={"file": ("broken_protocol.pdf", b"this is definitely not pdf content", "application/pdf")},
    )
    assert resp.status_code == 422
    assert "secret" not in resp.text.lower()
    assert list(storage.rglob("*.pdf")) == []


def test_trial_protocol_non_pdf_extension_rejected_without_file(client: TestClient, monkeypatch, tmp_path):
    storage = tmp_path / "storage" / "pdfs"
    monkeypatch.setattr("app.config.settings.pdf_storage_dir", str(storage))
    resp = client.post(
        "/api/v1/trials/TRIAL-SEC-001/extract-protocol",
        files={"file": ("protocol.docx", b"anything", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert list(storage.rglob("*")) == []