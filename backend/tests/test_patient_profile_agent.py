"""Comprehensive unit and integration tests for PatientProfileAgent, JSON & PDF extraction, and API endpoint.

Covers:
1. Complete JSON patient profile
2. Partial JSON patient profile
3. Empty JSON patient profile
4. Nested laboratory extraction
5. Nested blood pressure extraction
6. Boolean false preservation
7. Numeric zero preservation
8. Missing fields become missing_information
9. Numeric string parsing
10. Unit-suffixed numeric parsing
11. Alias handling (eGFR, egfr, ecog, ecog_score, ecog_performance_status, ANC, anc, platelets)
12. Provenance preservation
13. No diagnosis inference
14. PDF page traceability
15. FastAPI endpoint success (both JSON and PDF)
16. Invalid patient input handling
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

from app.agents.patient_profile_agent import PatientProfileAgent
from app.llm.gemini_service import GeminiLLMService
from app.main import create_app
from app.pdf.processor import PDFDocument, PDFProcessor
from app.schemas.patient import (
    ExtractedPatientResult,
    PregnancyStatus,
    Sex,
)


@pytest.fixture
def synthetic_patient_pdf(tmp_path: Path) -> Path:
    """Generate a valid, deterministic two-page clinical patient medical record PDF."""
    pdf_path = tmp_path / "synthetic_patient.pdf"
    doc = fitz.open()

    # Page 1: Demographics and Clinical Status
    page1 = doc.new_page()
    page1_text = (
        "PATIENT MEDICAL RECORD\n"
        "Patient ID: PT-10023\n"
        "Age: 58 years old. Sex: Female.\n"
        "Pregnancy status: Not pregnant. Breastfeeding: No.\n"
        "Clinical Status:\n"
        "ECOG performance status: 1.\n"
        "Active serious infection: No active infection documented.\n"
        "Cardiac disease: No uncontrolled cardiac disease.\n"
    )
    page1.insert_text((50, 72), page1_text, fontsize=11)

    # Page 2: Laboratories and Vital Signs
    page2 = doc.new_page()
    page2_text = (
        "LABORATORY RESULTS & VITALS\n"
        "eGFR: 64 mL/min/1.73m²\n"
        "Absolute Neutrophil Count (ANC): 2100 cells/mcL\n"
        "Platelet Count: 195000 cells/mcL\n"
        "Blood Pressure: 128/82 mmHg\n"
        "Heart Rate: 72 bpm\n"
        "Medications: No recent systemic anticancer therapy within past 4 weeks.\n"
    )
    page2.insert_text((50, 72), page2_text, fontsize=11)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_complete_json_patient_profile():
    """Verify complete JSON record extracts all fields into normalized PatientProfile."""
    agent = PatientProfileAgent()
    payload = {
        "patient_profile_id": "patient-001",
        "demographics": {
            "age": 52,
            "sex": "female",
            "pregnancy_status": "not_pregnant",
            "breastfeeding_status": False,
        },
        "conditions": [
            {"name": "advanced solid tumor", "status": "active", "documented": True}
        ],
        "clinical_status": {
            "ecog_performance_status": 1,
            "active_serious_infection": False,
            "uncontrolled_cardiac_disease": False,
        },
        "labs": {
            "anc": {"value": 2400, "unit": "cells/mcL"},
            "platelets": {"value": 185000, "unit": "cells/mcL"},
            "egfr": {"value": 68, "unit": "mL/min/1.73m²"},
        },
        "vital_signs": {
            "blood_pressure": {"systolic": 125, "diastolic": 78, "unit": "mmHg"}
        },
        "allergies": [],
        "medications": {
            "recent_systemic_anticancer_therapy": False
        },
    }

    result = agent.process_json(payload)
    assert isinstance(result, ExtractedPatientResult)
    assert result.patient_profile_id == "patient-001"
    assert result.profile.demographics.age == 52
    assert result.profile.demographics.sex == Sex.FEMALE
    assert result.profile.demographics.pregnancy_status == PregnancyStatus.NOT_PREGNANT
    assert result.profile.demographics.breastfeeding_status is False
    assert result.profile.clinical_status.ecog_performance_status == 1
    assert result.profile.clinical_status.active_serious_infection is False
    assert result.profile.clinical_status.uncontrolled_cardiac_disease is False
    assert result.profile.labs.egfr.value == 68.0
    assert result.profile.labs.anc.value == 2400.0
    assert result.profile.labs.platelets.value == 185000.0
    assert result.profile.vital_signs.blood_pressure.systolic == 125
    assert result.profile.vital_signs.blood_pressure.diastolic == 78
    assert result.profile.treatment_history.recent_systemic_anticancer_therapy is False
    assert len(result.missing_information) == 0


def test_boolean_false_and_zero_preservation():
    """CRITICAL: Test that False and 0 are preserved and NEVER treated as missing."""
    agent = PatientProfileAgent()
    payload = {
        "patient_profile_id": "test-zero-false",
        "demographics": {
            "age": 40,
            "sex": "male",
            "breastfeeding_status": False,
            "pregnancy_status": "not_pregnant",
        },
        "clinical_status": {
            "ecog_performance_status": 0,
            "active_serious_infection": False,
            "uncontrolled_cardiac_disease": False,
        },
        "labs": {
            "egfr": 0,  # e.g., severe documented anuria or dialysis index
            "anc": 1500,
            "platelets": 150000,
        },
        "vital_signs": {
            "blood_pressure": {"systolic": 110, "diastolic": 70}
        },
        "treatment_history": {
            "recent_systemic_anticancer_therapy": False,
        },
    }

    result = agent.process_json(payload)
    # Check boolean false values
    assert result.profile.clinical_status.active_serious_infection is False
    assert result.profile.clinical_status.uncontrolled_cardiac_disease is False
    assert result.profile.demographics.breastfeeding_status is False
    assert result.profile.treatment_history.recent_systemic_anticancer_therapy is False

    # Check numeric zero values
    assert result.profile.clinical_status.ecog_performance_status == 0
    assert result.profile.labs.egfr.value == 0.0

    # Ensure NONE of these documented False/0 fields appear in missing_information!
    assert "clinical_status.active_serious_infection" not in result.missing_information
    assert "clinical_status.uncontrolled_cardiac_disease" not in result.missing_information
    assert "clinical_status.ecog_performance_status" not in result.missing_information
    assert "labs.egfr" not in result.missing_information
    assert "demographics.breastfeeding_status" not in result.missing_information
    assert "treatment_history.recent_systemic_anticancer_therapy" not in result.missing_information


def test_partial_and_empty_json_patient_profile():
    """Verify empty and partial records populate missing_information explicitly."""
    agent = PatientProfileAgent()
    empty_result = agent.process_json({})

    assert isinstance(empty_result, ExtractedPatientResult)
    assert len(empty_result.missing_information) > 0
    assert "demographics.age" in empty_result.missing_information
    assert "demographics.sex" in empty_result.missing_information
    assert "clinical_status.ecog_performance_status" in empty_result.missing_information
    assert "clinical_status.active_serious_infection" in empty_result.missing_information
    assert "labs.egfr" in empty_result.missing_information
    assert "labs.anc" in empty_result.missing_information
    assert "labs.platelets" in empty_result.missing_information
    assert "vital_signs.blood_pressure" in empty_result.missing_information


def test_alias_handling():
    """Verify alias mapping for eGFR, ECOG, ANC, and Platelets across flat and nested keys."""
    agent = PatientProfileAgent()
    payload = {
        "ecog_score": "1",
        "eGFR": "68 mL/min/1.73m²",
        "ANC": "2500",
        "platelet_count": "210000 cells/mcL",
    }
    result = agent.process_json(payload)

    assert result.profile.clinical_status.ecog_performance_status == 1
    assert result.profile.labs.egfr.value == 68.0
    assert result.profile.labs.egfr.unit == "mL/min/1.73m²"
    assert result.profile.labs.anc.value == 2500.0
    assert result.profile.labs.platelets.value == 210000.0


def test_numeric_and_unit_string_parsing():
    """Verify string numbers with commas and units are normalized properly."""
    agent = PatientProfileAgent()
    payload = {
        "demographics": {"age": "62"},
        "labs": {
            "platelets": "185,000 /mcL",
            "egfr": "45.5 mL/min",
        },
        "vital_signs": {
            "blood_pressure": "130/85 mmHg"
        }
    }
    result = agent.process_json(payload)

    assert result.profile.demographics.age == 62
    assert result.profile.labs.platelets.value == 185000.0
    assert result.profile.labs.egfr.value == 45.5
    assert result.profile.vital_signs.blood_pressure.systolic == 130
    assert result.profile.vital_signs.blood_pressure.diastolic == 85


def test_provenance_preservation():
    """Verify auditable provenance records are created for extracted clinical facts."""
    agent = PatientProfileAgent()
    payload = {
        "demographics": {"age": 55},
        "labs": {"egfr": {"value": 72, "unit": "mL/min/1.73m²"}},
    }
    result = agent.process_json(payload, source_document="test_record.json")

    assert len(result.evidence) >= 2
    fields = {e.field: e for e in result.evidence}
    assert "demographics.age" in fields
    assert fields["demographics.age"].value == 55
    assert fields["demographics.age"].source == "patient_json"
    assert "labs.egfr" in fields
    assert fields["labs.egfr"].value == 72.0
    assert fields["labs.egfr"].unit == "mL/min/1.73m²"


def test_no_diagnosis_inference():
    """Verify that clinical conditions are recorded as stated without inferring uncontrolled status."""
    agent = PatientProfileAgent()
    payload = {
        "conditions": [{"name": "Hypertension", "status": "active"}],
        "vital_signs": {"blood_pressure": {"systolic": 140, "diastolic": 90}}
    }
    result = agent.process_json(payload)

    assert len(result.profile.conditions) == 1
    assert result.profile.conditions[0].name == "Hypertension"
    # Agent MUST NOT infer uncontrolled cardiac disease from hypertension + elevated BP
    assert result.profile.clinical_status.uncontrolled_cardiac_disease is None
    assert "clinical_status.uncontrolled_cardiac_disease" in result.missing_information


@pytest.mark.asyncio
async def test_pdf_patient_extraction_with_mocked_gemini(synthetic_patient_pdf: Path):
    """Verify PDF extraction pipeline preserves 1-indexed page citations and normalizes patient profile."""
    pdf_doc = PDFProcessor.extract_pages(synthetic_patient_pdf)

    mock_llm_json = {
        "patient_profile_id": "PT-10023",
        "demographics": {
            "age": 58,
            "sex": "female",
            "pregnancy_status": "not_pregnant",
            "breastfeeding_status": False,
        },
        "clinical_status": {
            "ecog_performance_status": 1,
            "active_serious_infection": False,
            "uncontrolled_cardiac_disease": False,
        },
        "labs": {
            "egfr": {"value": 64.0, "unit": "mL/min/1.73m²"},
            "anc": {"value": 2100.0, "unit": "cells/mcL"},
            "platelets": {"value": 195000.0, "unit": "cells/mcL"},
        },
        "vital_signs": {
            "blood_pressure": {"systolic": 128, "diastolic": 82, "unit": "mmHg"}
        },
        "treatment_history": {
            "recent_systemic_anticancer_therapy": False
        },
        "page_evidence": [
            {
                "field": "demographics.age",
                "value": 58,
                "source_page": 1,
                "source_excerpt": "Age: 58 years old. Sex: Female.",
            },
            {
                "field": "labs.egfr",
                "value": 64.0,
                "unit": "mL/min/1.73m²",
                "source_page": 2,
                "source_excerpt": "eGFR: 64 mL/min/1.73m²",
            },
        ],
    }

    mock_llm = GeminiLLMService(api_key="mock")
    mock_llm.generate_json = AsyncMock(return_value=mock_llm_json)

    agent = PatientProfileAgent(llm_service=mock_llm)
    result = await agent.process_pdf(pdf_doc, patient_profile_id="PT-10023")

    assert isinstance(result, ExtractedPatientResult)
    assert result.patient_profile_id == "PT-10023"
    assert result.source_type == "patient_pdf"
    assert result.profile.demographics.age == 58
    assert result.profile.labs.egfr.value == 64.0

    # Verify Page 1 vs Page 2 traceability
    evidence_by_field = {e.field: e for e in result.evidence if e.source_page is not None}
    assert "demographics.age" in evidence_by_field
    assert evidence_by_field["demographics.age"].source_page == 1
    assert "labs.egfr" in evidence_by_field
    assert evidence_by_field["labs.egfr"].source_page == 2


def test_api_extract_patient_profile_json():
    """Test FastAPI POST /api/v1/patients/extract-profile with JSON payload."""
    app = create_app()
    with TestClient(app) as client:
        payload = {
            "patient_profile_id": "PT-API-01",
            "demographics": {"age": 49, "sex": "male"},
            "clinical_status": {"active_serious_infection": False},
            "labs": {"egfr": 80},
        }
        response = client.post("/api/v1/patients/extract-profile", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["patient_profile_id"] == "PT-API-01"
        assert data["profile"]["demographics"]["age"] == 49
        assert data["profile"]["clinical_status"]["active_serious_infection"] is False
        assert "demographics.pregnancy_status" in data["missing_information"]
        assert "clinical_status.active_serious_infection" not in data["missing_information"]


def test_api_extract_patient_profile_pdf(synthetic_patient_pdf: Path):
    """Test FastAPI POST /api/v1/patients/extract-profile with PDF file upload."""
    app = create_app()

    mock_llm_json = {
        "patient_profile_id": "PT-PDF-TEST",
        "demographics": {"age": 58, "sex": "female", "pregnancy_status": "not_pregnant"},
        "clinical_status": {"active_serious_infection": False},
        "labs": {"egfr": {"value": 64.0, "unit": "mL/min/1.73m²"}},
    }

    with patch("app.agents.patient_profile_agent.GeminiLLMService.generate_json", AsyncMock(return_value=mock_llm_json)), \
         patch("app.llm.xai_service.XAiLLMService.generate_json", AsyncMock(return_value=mock_llm_json)):
        with TestClient(app) as client:
            with open(synthetic_patient_pdf, "rb") as pdf_bytes:
                files = {"file": ("patient_record.pdf", pdf_bytes, "application/pdf")}
                response = client.post("/api/v1/patients/extract-profile", files=files)

            assert response.status_code == 200, response.text
            data = response.json()
            assert data["patient_profile_id"] == "PT-PDF-TEST"
            assert data["source_type"] == "patient_pdf"
            assert data["profile"]["demographics"]["age"] == 58


def test_api_invalid_patient_input():
    """Verify invalid payloads return appropriate 400 Bad Request."""
    app = create_app()
    with TestClient(app) as client:
        # Invalid content type / body
        response = client.post("/api/v1/patients/extract-profile", content="Not json", headers={"content-type": "application/json"})
        assert response.status_code == 400


def test_api_extract_patient_document_pdf(synthetic_patient_pdf: Path):
    """Test POST /api/v1/patients/extract-document with PDF upload and UI compatibility fields."""
    app = create_app()

    mock_llm_json = {
        "patient_profile_id": "PT-DOC-001",
        "demographics": {"age": 58, "sex": "female", "pregnancy_status": "not_pregnant"},
        "clinical_status": {"active_serious_infection": False, "uncontrolled_cardiac_disease": False},
        "labs": {
            "egfr": {"value": 64.0, "unit": "mL/min/1.73m²"},
            "anc": {"value": 2100.0, "unit": "cells/mcL"},
        },
        "page_evidence": [
            {"field": "labs.egfr", "value": 64.0, "unit": "mL/min/1.73m²", "source_page": 2, "source_excerpt": "eGFR: 64"}
        ],
    }

    with patch("app.agents.patient_profile_agent.GeminiLLMService.generate_json", AsyncMock(return_value=mock_llm_json)), \
         patch("app.llm.xai_service.XAiLLMService.generate_json", AsyncMock(return_value=mock_llm_json)):
        with TestClient(app) as client:
            with open(synthetic_patient_pdf, "rb") as pdf_bytes:
                files = {"file": ("synthetic_patient.pdf", pdf_bytes, "application/pdf")}
                response = client.post("/api/v1/patients/extract-document", files=files)

            assert response.status_code == 200, response.text
            data = response.json()
            assert data["patient_profile_id"] == "PT-DOC-001"
            assert data["sourceType"] == "Uploaded PDF"
            assert data["sourceDocument"] == "synthetic_patient.pdf"
            assert isinstance(data["extractedFields"], list)
            assert "demographics.age" in data["extractedFields"]
            assert "labs.egfr" in data["extractedFields"]
            assert len(data["profile"]["lab_values"]) >= 2
            assert any(lv["name"] == "eGFR" for lv in data["profile"]["lab_values"])
            assert isinstance(data["profile"]["missing_information"], list)


def test_api_extract_patient_document_pdf_without_llm_deterministic_fallback(synthetic_patient_pdf: Path):
    """Test POST /api/v1/patients/extract-document succeeds via deterministic fallback when LLM fails."""
    app = create_app()

    # Simulate LLM complete outage / failure (e.g. XAiAPIError or network offline)
    with patch(
        "app.agents.patient_profile_agent.GeminiLLMService.generate_json",
        AsyncMock(side_effect=RuntimeError("xKiro / LLM offline")),
    ), patch(
        "app.llm.xai_service.XAiLLMService.generate_json",
        AsyncMock(side_effect=RuntimeError("xKiro / LLM offline")),
    ):
        with TestClient(app) as client:
            with open(synthetic_patient_pdf, "rb") as pdf_bytes:
                files = {"file": ("synthetic_patient.pdf", pdf_bytes, "application/pdf")}
                response = client.post("/api/v1/patients/extract-document", files=files)

            assert response.status_code == 200, response.text
            data = response.json()
            assert data["patient_profile_id"] == "PT-10023"
            assert data["profile"]["demographics"]["age"] == 58
            assert data["profile"]["demographics"]["sex"] == "female"
            assert data["profile"]["demographics"]["pregnancy_status"] == "not_pregnant"
            assert data["profile"]["clinical_status"]["active_serious_infection"] is False
            assert data["profile"]["clinical_status"]["uncontrolled_cardiac_disease"] is False
            assert data["profile"]["labs"]["egfr"]["value"] == 64.0
            assert data["profile"]["labs"]["anc"]["value"] == 2100.0
            assert data["profile"]["labs"]["platelets"]["value"] == 195000.0
            assert data["sourceType"] == "Uploaded PDF"
            assert len(data["profile"]["lab_values"]) >= 3


def test_api_extract_patient_document_json_file_upload():
    """Test POST /api/v1/patients/extract-document with a .json file upload."""
    app = create_app()
    with TestClient(app) as client:
        json_content = b'{"patient_profile_id": "PT-JSON-FILE", "demographics": {"age": 62, "sex": "male"}, "labs": {"egfr": 75.5}}'
        files = {"file": ("patient_record.json", json_content, "application/json")}
        response = client.post("/api/v1/patients/extract-document", files=files)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["patient_profile_id"] == "PT-JSON-FILE"
        assert data["profile"]["demographics"]["age"] == 62
        assert data["profile"]["labs"]["egfr"]["value"] == 75.5
        assert data["sourceType"] == "Uploaded JSON"
        assert data["sourceDocument"] == "patient_record.json"


def test_api_extract_patient_document_json_body():
    """Test POST /api/v1/patients/extract-document with raw JSON body."""
    app = create_app()
    with TestClient(app) as client:
        payload = {
            "patient_profile_id": "PT-BODY-01",
            "demographics": {"age": 45, "sex": "female"},
            "labs": {"platelets": 250000},
        }
        response = client.post("/api/v1/patients/extract-document", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["patient_profile_id"] == "PT-BODY-01"
        assert data["profile"]["demographics"]["age"] == 45


def test_api_patient_save_and_list():
    """Test POST /api/v1/patients/profile and GET /api/v1/patients."""
    app = create_app()
    with TestClient(app) as client:
        profile = {
            "patient_profile_id": "PT-PERSIST-01",
            "demographics": {"age": 55, "sex": "male"},
        }
        save_resp = client.post("/api/v1/patients/profile", json=profile)
        assert save_resp.status_code == 200
        saved_data = save_resp.json()
        assert saved_data["patient_profile_id"] == "PT-PERSIST-01"

        # List patients
        list_resp = client.get("/api/v1/patients")
        assert list_resp.status_code == 200
        patients = list_resp.json()
        assert any(p.get("patient_profile_id") == "PT-PERSIST-01" for p in patients)

        # Get specific patient
        get_resp = client.get("/api/v1/patients/PT-PERSIST-01")
        assert get_resp.status_code == 200
        assert get_resp.json()["patient_profile_id"] == "PT-PERSIST-01"

