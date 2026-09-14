"""Patient record API router for FastAPI backend.

Accepts patient records as JSON payload or PDF file upload, and produces normalized,
evidence-auditable ExtractedPatientResult models.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.agents.patient_profile_agent import PatientProfileAgent
from app.config import settings
from app.pdf.processor import (
    PDFCorruptError,
    PDFNotFoundError,
    PDFProcessor,
)
from app.schemas.patient import ExtractedPatientResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients", tags=["Patients & Profile Extraction"])


def _sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal."""
    clean = Path(name).name
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    if clean in (".", "..", ""):
        return "patient_record.pdf"
    return clean


def _safe_unlink(path: Path, attempts: int = 20) -> None:
    """Best-effort delete that tolerates transient OS file locks (e.g. Windows)."""
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.05)
    logger.warning("Could not remove temporary upload file: %s", Path(path).name)


@router.post(
    "/extract-profile",
    response_model=ExtractedPatientResult,
    status_code=status.HTTP_200_OK,
    summary="Extract and normalize patient profile from JSON or PDF record",
)
async def extract_patient_profile_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(default=None, description="Optional patient PDF record"),
) -> ExtractedPatientResult:
    """Extract and normalize a patient profile.

    Accepts:
    1. Direct JSON body (`application/json`) with clinical facts.
    2. Multipart form upload (`multipart/form-data`) with `file` as PDF document.

    Outputs normalized PatientProfile, explicit missing information list, and audit evidence.
    """
    agent = PatientProfileAgent()
    content_type = request.headers.get("content-type", "")

    # Path A: File Upload (PDF)
    if file is not None and file.filename:
        filename = file.filename
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file format. Patient document must be a PDF file (.pdf).",
            )

        storage_root = Path(settings.pdf_storage_dir) / "patients"
        storage_root.mkdir(parents=True, exist_ok=True)
        safe_name = _sanitize_filename(filename)
        target_path = storage_root / safe_name

        total_bytes = 0
        try:
            with open(target_path, "wb") as buffer:
                while chunk := await file.read(64 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > settings.max_upload_size_bytes:
                        buffer.close()
                        _safe_unlink(target_path)
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Uploaded patient PDF exceeds size limits.",
                        )
                    buffer.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            _safe_unlink(target_path)
            logger.error("Failed to save uploaded patient PDF: %s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save the uploaded patient PDF.",
            ) from e
        finally:
            await file.close()

        if total_bytes == 0:
            _safe_unlink(target_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded patient PDF is empty (0 bytes).",
            )

        try:
            pdf_doc = PDFProcessor.extract_pages(target_path)
        except (PDFNotFoundError, PDFCorruptError) as err:
            _safe_unlink(target_path)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Patient PDF document is unreadable or corrupted.",
            ) from err

        try:
            result = await agent.process_pdf(pdf_doc)
        except Exception as e:
            logger.error("Patient PDF profile extraction failed: %s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Patient PDF profile extraction failed.",
            ) from e
        finally:
            # Patient records are sensitive PHI: never retain the raw document
            # after extraction, regardless of success or failure.
            _safe_unlink(target_path)

        return result

    # Path B: JSON Payload
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request. Provide either a JSON body or a PDF file upload.",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient JSON payload must be an object.",
        )

    result = agent.process_json(body)
    return result