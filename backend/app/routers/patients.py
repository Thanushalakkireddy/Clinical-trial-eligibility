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
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.agents.patient_profile_agent import PatientProfileAgent
from app.config import settings
from app.database.repository import create_patient, get_patient, list_patients
from app.database.serialization import decode_json, encode_json
from app.database.session import get_session_maker, persist_is_configured
from app.pdf.processor import (
    PDFCorruptError,
    PDFNotFoundError,
    PDFProcessor,
)
from app.schemas.patient import ExtractedPatientResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients", tags=["Patients & Profile Extraction"])

# In-memory store for fast client retrieval when running without SQL database
_IN_MEMORY_PATIENTS: Dict[str, Dict[str, Any]] = {}


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


async def _handle_patient_extraction(
    request: Request,
    file: Optional[UploadFile] = None,
) -> ExtractedPatientResult:
    """Core handler for patient extraction from PDF file, JSON file, or JSON request body."""
    agent = PatientProfileAgent()

    # Case 1: Uploaded file (either PDF or JSON)
    if file is not None and file.filename:
        filename = file.filename
        lower_name = filename.lower()

        # Handle JSON file upload
        if lower_name.endswith(".json"):
            try:
                content = await file.read()
                data = json.loads(content.decode("utf-8"))
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded patient JSON file is malformed or invalid JSON.",
                ) from e
            finally:
                await file.close()

            if not isinstance(data, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Patient JSON payload must be an object.",
                )

            result = agent.process_json(data, source_document=filename)
            _IN_MEMORY_PATIENTS[result.patient_profile_id] = result.profile.model_dump(mode="json")
            return result

        # Handle PDF file upload
        if not lower_name.endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file format. Patient document must be a PDF (.pdf) or JSON (.json) file.",
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
            _safe_unlink(target_path)

        _IN_MEMORY_PATIENTS[result.patient_profile_id] = result.profile.model_dump(mode="json")
        return result

    # Case 2: JSON Payload in body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request. Provide either a JSON body or a file upload.",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient JSON payload must be an object.",
        )

    result = agent.process_json(body, source_document="patient_record.json")
    _IN_MEMORY_PATIENTS[result.patient_profile_id] = result.profile.model_dump(mode="json")
    return result


@router.post(
    "/extract-document",
    response_model=ExtractedPatientResult,
    status_code=status.HTTP_200_OK,
    summary="Extract patient profile from uploaded document (PDF or JSON) or JSON body",
)
async def extract_patient_document_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(default=None, description="Patient PDF or JSON document"),
) -> ExtractedPatientResult:
    """Primary endpoint called by frontend Patient Records UI to extract patient profile."""
    return await _handle_patient_extraction(request=request, file=file)


@router.post(
    "/extract-profile",
    response_model=ExtractedPatientResult,
    status_code=status.HTTP_200_OK,
    summary="Extract and normalize patient profile (backward compatibility endpoint)",
)
async def extract_patient_profile_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(default=None, description="Patient PDF or JSON document"),
) -> ExtractedPatientResult:
    """Backward compatibility endpoint for extracting patient profiles."""
    return await _handle_patient_extraction(request=request, file=file)


@router.post(
    "/profile",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Save or update a patient profile",
)
async def save_patient_profile_endpoint(request: Request) -> Dict[str, Any]:
    """Persist a patient profile in memory and database if configured."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        )

    patient_id = payload.get("patient_profile_id") or payload.get("patient_id") or payload.get("id")
    if not patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patient_profile_id is required.",
        )

    # Cache in memory
    _IN_MEMORY_PATIENTS[patient_id] = payload

    # Save to database if available
    if persist_is_configured():
        try:
            async with get_session_maker()() as session:
                await create_patient(
                    session=session,
                    patient_profile_id=patient_id,
                    profile_json=payload,
                    source_type=payload.get("source_type") or payload.get("sourceType"),
                    source_document=payload.get("source_document") or payload.get("sourceDocument"),
                )
                await session.commit()
        except Exception as err:
            logger.warning("Failed to persist patient to database: %s", err)

    return payload


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List stored patient profiles",
)
async def list_patients_endpoint() -> List[Dict[str, Any]]:
    """Return all stored patient profiles from memory or database."""
    patients_map: Dict[str, Dict[str, Any]] = dict(_IN_MEMORY_PATIENTS)

    if persist_is_configured():
        try:
            async with get_session_maker()() as session:
                records = await list_patients(session)
                for rec in records:
                    if rec.profile_json:
                        data = decode_json(rec.profile_json)
                        if isinstance(data, dict):
                            pid = rec.patient_profile_id
                            patients_map[pid] = data
                            _IN_MEMORY_PATIENTS[pid] = data
        except Exception as err:
            logger.warning("Failed to fetch patients from database: %s", err)

    return list(patients_map.values())


@router.get(
    "/{patient_profile_id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get patient profile by ID",
)
async def get_patient_profile_endpoint(patient_profile_id: str) -> Dict[str, Any]:
    """Fetch patient profile by ID."""
    if patient_profile_id in _IN_MEMORY_PATIENTS:
        return _IN_MEMORY_PATIENTS[patient_profile_id]

    if persist_is_configured():
        try:
            async with get_session_maker()() as session:
                record = await get_patient(session, patient_profile_id)
                if record and record.profile_json:
                    data = decode_json(record.profile_json)
                    if isinstance(data, dict):
                        _IN_MEMORY_PATIENTS[patient_profile_id] = data
                        return data
        except Exception as err:
            logger.warning("Failed to fetch patient from database: %s", err)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Patient profile {patient_profile_id} not found.",
    )
