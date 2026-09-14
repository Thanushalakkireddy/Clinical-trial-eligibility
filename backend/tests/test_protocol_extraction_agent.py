"""Unit and integration tests for ProtocolExtractionAgent, PyMuPDF PDFProcessor, and API endpoint.

Uses synthetic 2-page PDF fixture and mocks GeminiLLMService.
No real Gemini API calls are made in automated tests.
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

from app.agents.protocol_extraction_agent import (
    ProtocolExtractionAgent,
    ProtocolExtractionError,
)
from app.llm.gemini_service import GeminiLLMService
from app.main import create_app
from app.pdf.processor import (
    PDFCorruptError,
    PDFDocument,
    PDFNotFoundError,
    PDFProcessor,
)
from app.schemas.protocol import (
    CriterionType,
    ExtractedProtocol,
)


@pytest.fixture
def synthetic_two_page_pdf(tmp_path: Path) -> Path:
    """Generate a valid, deterministic two-page clinical trial protocol PDF."""
    pdf_path = tmp_path / "synthetic_protocol.pdf"
    doc = fitz.open()

    # Page 1: Protocol Header and Inclusion Criteria
    page1 = doc.new_page()
    page1_text = (
        "CLINICAL TRIAL PROTOCOL\n"
        "Protocol ID: TEST-ONC-001\n"
        "Title: Phase 2 Study of Targeted Kinase Inhibitor in Advanced Solid Tumors\n\n"
        "Inclusion Criteria:\n"
        "1. Age 18 years or older at the time of signing informed consent.\n"
        "2. Histologically confirmed advanced solid tumor refractory to standard therapy.\n"
        "3. ECOG performance status 0 or 1.\n"
        "4. Adequate renal function: eGFR must be at least 30 mL/min/1.73m².\n"
    )
    page1.insert_text((50, 72), page1_text, fontsize=11)

    # Page 2: Exclusion Criteria and Study Parameters
    page2 = doc.new_page()
    page2_text = (
        "Exclusion Criteria:\n"
        "1. Active serious infection requiring systemic intravenous antibiotic therapy.\n"
        "2. Recent myocardial infarction within 6 months prior to study enrollment.\n"
        "3. Concurrent participation in another investigational interventional study.\n\n"
        "Study Parameters:\n"
        "Patients must agree to undergo baseline tumor biopsy."
    )
    page2.insert_text((50, 72), page2_text, fontsize=11)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pdf_processor_page_extraction_preserves_page_numbers(synthetic_two_page_pdf: Path):
    """Verify PyMuPDF extracts text page-by-page and accurately tracks 1-indexed page numbers."""
    pdf_doc = PDFProcessor.extract_pages(synthetic_two_page_pdf)

    assert isinstance(pdf_doc, PDFDocument)
    assert pdf_doc.total_pages == 2
    assert len(pdf_doc.pages) == 2

    # Check Page 1
    p1 = pdf_doc.pages[0]
    assert p1.page_number == 1
    assert "Protocol ID: TEST-ONC-001" in p1.text
    assert "Inclusion Criteria:" in p1.text
    assert "ECOG performance status 0 or 1" in p1.text

    # Check Page 2
    p2 = pdf_doc.pages[1]
    assert p2.page_number == 2
    assert "Exclusion Criteria:" in p2.text
    assert "Active serious infection" in p2.text
    assert "Recent myocardial infarction" in p2.text


def test_pdf_processor_missing_file():
    """Verify missing file raises PDFNotFoundError."""
    with pytest.raises(PDFNotFoundError):
        PDFProcessor.extract_pages("/non/existent/path/protocol.pdf")


def test_pdf_processor_corrupt_file(tmp_path: Path):
    """Verify corrupted non-PDF file raises PDFCorruptError."""
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_text("Not a valid PDF file stream")
    with pytest.raises(PDFCorruptError):
        PDFProcessor.extract_pages(bad_file)


@pytest.mark.asyncio
async def test_protocol_extraction_agent_mocked_gemini(synthetic_two_page_pdf: Path):
    """Verify ProtocolExtractionAgent extracts structured criteria, preserves page numbers, and generates deterministic IDs."""
    pdf_doc = PDFProcessor.extract_pages(synthetic_two_page_pdf)

    # Mock structured JSON response mimicking faithful Gemini extraction
    mock_llm_response = {
        "protocol_id": "TEST-ONC-001",
        "title": "Phase 2 Study of Targeted Kinase Inhibitor in Advanced Solid Tumors",
        "inclusion_criteria": [
            {
                "text": "Age 18 years or older at the time of signing informed consent.",
                "source_page": 1,
                "section": "Inclusion Criteria",
                "source_excerpt": "Age 18 years or older at the time of signing",
            },
            {
                "text": "ECOG performance status 0 or 1.",
                "source_page": 1,
                "section": "Inclusion Criteria",
                "source_excerpt": "ECOG performance status 0 or 1.",
            },
            {
                "text": "Adequate renal function: eGFR must be at least 30 mL/min/1.73m².",
                "source_page": 1,
                "section": "Inclusion Criteria",
                "source_excerpt": "eGFR must be at least 30 mL/min/1.73m².",
            },
        ],
        "exclusion_criteria": [
            {
                "text": "Active serious infection requiring systemic intravenous antibiotic therapy.",
                "source_page": 2,
                "section": "Exclusion Criteria",
                "source_excerpt": "Active serious infection requiring systemic intravenous",
            },
            {
                "text": "Recent myocardial infarction within 6 months prior to study enrollment.",
                "source_page": 2,
                "section": "Exclusion Criteria",
                "source_excerpt": "Recent myocardial infarction within 6 months",
            },
        ],
        "other_requirements": [
            {
                "text": "Patients must agree to undergo baseline tumor biopsy.",
                "source_page": 2,
                "section": "Study Parameters",
                "source_excerpt": "agree to undergo baseline tumor biopsy",
            }
        ],
    }

    mock_llm_service = GeminiLLMService(api_key="mock-key")
    mock_llm_service.generate_json = AsyncMock(return_value=mock_llm_response)

    agent = ProtocolExtractionAgent(llm_service=mock_llm_service)
    result = await agent.extract_protocol(pdf_doc=pdf_doc, trial_id="SYN-TRIAL-001")

    assert isinstance(result, ExtractedProtocol)
    assert result.trial_id == "SYN-TRIAL-001"
    assert result.protocol_id == "TEST-ONC-001"
    assert result.title == "Phase 2 Study of Targeted Kinase Inhibitor in Advanced Solid Tumors"

    # Verify Inclusion Criteria & Page Numbers
    assert len(result.inclusion_criteria) == 3
    assert result.inclusion_criteria[0].criterion_id == "INC-001"
    assert result.inclusion_criteria[0].type == CriterionType.INCLUSION
    assert result.inclusion_criteria[0].source_page == 1
    assert "Age 18" in result.inclusion_criteria[0].text

    assert result.inclusion_criteria[1].criterion_id == "INC-002"
    assert result.inclusion_criteria[2].criterion_id == "INC-003"
    assert result.inclusion_criteria[2].source_page == 1

    # Verify Exclusion Criteria & Page Numbers (Must be on Page 2!)
    assert len(result.exclusion_criteria) == 2
    assert result.exclusion_criteria[0].criterion_id == "EXC-001"
    assert result.exclusion_criteria[0].type == CriterionType.EXCLUSION
    assert result.exclusion_criteria[0].source_page == 2
    assert "Active serious infection" in result.exclusion_criteria[0].text

    assert result.exclusion_criteria[1].criterion_id == "EXC-002"
    assert result.exclusion_criteria[1].source_page == 2

    # Verify Other Requirements
    assert len(result.other_requirements) == 1
    assert result.other_requirements[0].criterion_id == "OTHER-001"
    assert result.other_requirements[0].type == CriterionType.OTHER
    assert result.other_requirements[0].source_page == 2


@pytest.mark.asyncio
async def test_protocol_extraction_empty_document_error():
    """Verify extracting from an empty document raises ProtocolExtractionError."""
    empty_doc = PDFDocument(filename="empty.pdf", file_path="/tmp/empty.pdf", total_pages=0, pages=[])
    agent = ProtocolExtractionAgent(llm_service=GeminiLLMService(api_key="mock"))

    with pytest.raises(ProtocolExtractionError, match="Cannot extract protocol from an empty PDF"):
        await agent.extract_protocol(empty_doc, trial_id="TRIAL-01")


def test_api_extract_protocol_endpoint(synthetic_two_page_pdf: Path):
    """Test FastAPI POST /api/v1/trials/{trial_id}/extract-protocol with synthetic PDF upload."""
    app = create_app()

    mock_llm_response = {
        "protocol_id": "TEST-ONC-001",
        "title": "Synthetic Protocol",
        "inclusion_criteria": [
            {
                "text": "Age 18 years or older.",
                "source_page": 1,
                "section": "Inclusion Criteria",
                "source_excerpt": "Age 18 years or older",
            }
        ],
        "exclusion_criteria": [
            {
                "text": "Active serious infection.",
                "source_page": 2,
                "section": "Exclusion Criteria",
                "source_excerpt": "Active serious infection",
            }
        ],
        "other_requirements": [],
    }

    with patch("app.agents.protocol_extraction_agent.GeminiLLMService.generate_json", AsyncMock(return_value=mock_llm_response)):
        with TestClient(app) as client:
            with open(synthetic_two_page_pdf, "rb") as pdf_bytes:
                files = {"file": ("protocol.pdf", pdf_bytes, "application/pdf")}
                response = client.post("/api/v1/trials/TRIAL-999/extract-protocol", files=files)

            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["trial_id"] == "TRIAL-999"
            assert payload["protocol_id"] == "TEST-ONC-001"
            assert len(payload["inclusion_criteria"]) == 1
            assert payload["inclusion_criteria"][0]["criterion_id"] == "INC-001"
            assert payload["inclusion_criteria"][0]["source_page"] == 1
            assert len(payload["exclusion_criteria"]) == 1
            assert payload["exclusion_criteria"][0]["criterion_id"] == "EXC-001"
            assert payload["exclusion_criteria"][0]["source_page"] == 2


def test_api_extract_protocol_invalid_extension():
    """Verify uploading non-pdf file returns 400 Bad Request."""
    app = create_app()
    with TestClient(app) as client:
        files = {"file": ("notes.txt", BytesIO(b"Some text"), "text/plain")}
        response = client.post("/api/v1/trials/TRIAL-999/extract-protocol", files=files)
        assert response.status_code == 400
        assert "must be a PDF document" in response.json()["detail"]
