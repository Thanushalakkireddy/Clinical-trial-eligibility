"""Trial and protocol API router for FastAPI backend.

Handles PDF upload and triggers the ProtocolExtractionAgent pipeline.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.agents.protocol_extraction_agent import (
    ProtocolExtractionAgent,
    ProtocolExtractionError,
)
from app.config import settings
from app.pdf.processor import (
    PDFCorruptError,
    PDFNotFoundError,
    PDFProcessor,
)
from app.schemas.protocol import ExtractedProtocol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trials", tags=["Trials & Protocol Extraction"])


def _sanitize_filename(name: str) -> str:
    """Strip unsafe path traversal characters from upload filename."""
    clean = Path(name).name
    # Keep alphanumeric, dot, underscore, dash
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean)
    if clean in (".", "..", ""):
        return "protocol.pdf"
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
    "/{trial_id}/extract-protocol",
    response_model=ExtractedProtocol,
    status_code=status.HTTP_200_OK,
    summary="Extract structured eligibility protocol from a clinical trial PDF",
)
async def extract_protocol_endpoint(
    trial_id: str,
    file: UploadFile = File(..., description="Clinical trial protocol PDF file"),
) -> ExtractedProtocol:
    """Upload a clinical trial protocol PDF and extract structured eligibility criteria.

    - Validates file format and size limits.
    - Saves document to configurable storage path `PDF_STORAGE_DIR`.
    - Parses text page-by-page preserving page numbers.
    - Invokes ProtocolExtractionAgent via GeminiLLMService.
    - Returns strictly validated ExtractedProtocol schema.
    """
    # Validate trial_id
    clean_trial_id = re.sub(r"[^a-zA-Z0-9_-]", "", trial_id.strip())
    if not clean_trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid trial_id format. Must be non-empty alphanumeric.",
        )

    # Validate file extension and MIME type
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Uploaded file must be a PDF document (.pdf).",
        )

    # Ensure storage directory exists
    storage_root = Path(settings.pdf_storage_dir)
    trial_storage_dir = storage_root / clean_trial_id
    trial_storage_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(filename)
    target_path = trial_storage_dir / safe_name

    # Stream file to disk and enforce file size constraints
    total_bytes = 0
    try:
        with open(target_path, "wb") as buffer:
            while chunk := await file.read(64 * 1024):  # 64KB chunks
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_size_bytes:
                    buffer.close()
                    _safe_unlink(target_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Uploaded file exceeds maximum allowed size of {settings.max_upload_size_bytes} bytes.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        _safe_unlink(target_path)
        logger.error("Failed to save uploaded protocol PDF: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the uploaded protocol PDF.",
        ) from e
    finally:
        await file.close()

    if total_bytes == 0:
        _safe_unlink(target_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF file is empty (0 bytes).",
        )

    # Extract page-numbered text using PyMuPDF
    try:
        pdf_doc = PDFProcessor.extract_pages(target_path)
    except (PDFNotFoundError, PDFCorruptError) as err:
        _safe_unlink(target_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF document is unreadable or corrupted.",
        ) from err
    except Exception as err:
        _safe_unlink(target_path)
        logger.error("Unexpected failure reading PDF: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected failure reading the uploaded PDF.",
        ) from err

    # Execute Protocol Extraction Agent
    agent = ProtocolExtractionAgent()
    try:
        extracted = await agent.extract_protocol(pdf_doc=pdf_doc, trial_id=clean_trial_id)
        return extracted
    except ProtocolExtractionError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Protocol extraction validation failed.",
        ) from err
    except Exception as err:
        logger.error("Protocol extraction error: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Protocol extraction failed.",
        ) from err
