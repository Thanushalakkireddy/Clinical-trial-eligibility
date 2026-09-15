"""Trial and protocol API router for FastAPI backend.

Handles PDF upload and triggers the ProtocolExtractionAgent pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.agents.protocol_extraction_agent import (
    ProtocolExtractionAgent,
    ProtocolExtractionError,
)
from app.config import settings
from app.database.repository import (
    create_protocol,
    get_protocol,
    list_protocols,
)
from app.database.serialization import decode_json, encode_json
from app.database.session import get_session_maker, persist_is_configured
from app.pdf.processor import (
    PDFCorruptError,
    PDFNotFoundError,
    PDFProcessor,
)
from app.schemas.protocol import ExtractedProtocol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trials", tags=["Trials & Protocol Extraction"])

# In-memory trial cache for fast retrieval and fallback when database is unconfigured
_IN_MEMORY_TRIALS: Dict[str, Dict[str, Any]] = {}


def _load_persisted_trials_from_disk() -> None:
    """Load existing protocol JSON files from disk into memory cache."""
    try:
        storage_root = Path(settings.pdf_storage_dir)
        if storage_root.exists():
            for json_path in storage_root.glob("*_protocol.json"):
                try:
                    content = json.loads(json_path.read_text(encoding="utf-8"))
                    tid = content.get("trial_id")
                    if tid and tid not in _IN_MEMORY_TRIALS:
                        if not content.get("trial_title") and content.get("title"):
                            content["trial_title"] = content["title"]
                        if not content.get("title") and content.get("trial_title"):
                            content["title"] = content["trial_title"]
                        if not content.get("trial_identifier"):
                            content["trial_identifier"] = content.get("protocol_id") or tid
                        _IN_MEMORY_TRIALS[tid] = content
                except Exception:
                    pass
    except Exception:
        pass


_load_persisted_trials_from_disk()


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
        logger.info(
            "Protocol extracted successfully: trial_id=%s inclusions=%d exclusions=%d others=%d",
            clean_trial_id,
            len(extracted.inclusion_criteria),
            len(extracted.exclusion_criteria),
            len(extracted.other_requirements),
        )

        # Build dictionary representation for persistence
        trial_data = extracted.model_dump(mode="json")
        trial_title = extracted.title or safe_name.replace(".pdf", "").replace("_", " ")
        trial_identifier = extracted.protocol_id or clean_trial_id

        trial_data["trial_id"] = clean_trial_id
        trial_data["trial_title"] = trial_title
        trial_data["title"] = trial_title
        trial_data["protocol_id"] = trial_identifier
        trial_data["trial_identifier"] = trial_identifier
        trial_data["processing_status"] = "completed"
        trial_data["source_document"] = extracted.source_document or safe_name
        trial_data["total_pages_analyzed"] = pdf_doc.total_pages

        # Cache in memory
        _IN_MEMORY_TRIALS[clean_trial_id] = trial_data
        if extracted.trial_id and extracted.trial_id != clean_trial_id:
            _IN_MEMORY_TRIALS[extracted.trial_id] = trial_data

        # Durable disk fallback in storage/pdfs
        try:
            proto_path = storage_root / f"{clean_trial_id}_protocol.json"
            proto_path.write_text(json.dumps(trial_data, indent=2), encoding="utf-8")
        except Exception as disk_err:
            logger.warning("Could not write protocol JSON to disk: %s", disk_err)

        # Persist to PostgreSQL database if configured
        if persist_is_configured():
            try:
                session_maker = get_session_maker()
                async with session_maker() as session:
                    all_criteria = [
                        c.model_dump(mode="json")
                        for c in (
                            extracted.inclusion_criteria
                            + extracted.exclusion_criteria
                            + extracted.other_requirements
                        )
                    ]
                    page_count = (
                        extracted.extraction_metadata.get("page_count")
                        or extracted.extraction_metadata.get("total_pages")
                        or pdf_doc.total_pages
                    )
                    await create_protocol(
                        session=session,
                        trial_id=clean_trial_id,
                        protocol_metadata=trial_data,
                        source_document=extracted.source_document or safe_name,
                        source_page_count=page_count,
                        criteria=all_criteria,
                    )
                    if extracted.trial_id and extracted.trial_id != clean_trial_id:
                        await create_protocol(
                            session=session,
                            trial_id=extracted.trial_id,
                            protocol_metadata=trial_data,
                            source_document=extracted.source_document or safe_name,
                            source_page_count=page_count,
                            criteria=all_criteria,
                        )
                    await session.commit()
                    logger.info("Persisted ProtocolRecord to PostgreSQL database: trial_id=%s", clean_trial_id)
            except Exception as db_err:
                logger.warning("Failed to persist protocol to PostgreSQL database: %s", db_err)

        return extracted
    except ProtocolExtractionError as err:
        safe_msg = str(err)
        text_len = sum(len(p.text) for p in pdf_doc.pages)
        logger.warning(
            "Protocol extraction validation failed: trial_id=%s filename=%s bytes=%d pages=%d text_len=%d error=%s",
            clean_trial_id,
            safe_name,
            total_bytes,
            pdf_doc.total_pages,
            text_len,
            safe_msg,
        )
        detail_msg = (
            safe_msg
            if safe_msg.startswith("Protocol extraction validation failed")
            else f"Protocol extraction validation failed: {safe_msg}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail_msg,
        ) from err
    except Exception as err:
        logger.error("Protocol extraction error: %s: %s", type(err).__name__, err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Protocol extraction failed.",
        ) from err


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List stored clinical trial protocols",
)
async def list_trials_endpoint() -> List[Dict[str, Any]]:
    """Return all stored clinical trial protocols from PostgreSQL database or in-memory cache.

    Guarantees trial_id, trial_title, protocol_id, trial_identifier, criteria, and provenance.
    """
    trials_map: Dict[str, Dict[str, Any]] = dict(_IN_MEMORY_TRIALS)

    if persist_is_configured():
        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                records = await list_protocols(session)
                for rec in records:
                    meta = decode_json(rec.protocol_metadata, default={}) or {}
                    criteria_list = decode_json(rec.criteria, default=[]) or []

                    inclusion = meta.get("inclusion_criteria") or [
                        c for c in criteria_list if "inc" in str(c.get("type", "")).lower()
                    ]
                    exclusion = meta.get("exclusion_criteria") or [
                        c for c in criteria_list if "exc" in str(c.get("type", "")).lower()
                    ]
                    other = meta.get("other_requirements") or [
                        c for c in criteria_list if "other" in str(c.get("type", "")).lower()
                    ]

                    title = meta.get("title") or meta.get("trial_title") or rec.trial_id
                    trial_title = meta.get("trial_title") or meta.get("title") or rec.trial_id
                    proto_id = meta.get("protocol_id") or rec.trial_id
                    identifier = meta.get("trial_identifier") or proto_id

                    item = {
                        "trial_id": rec.trial_id,
                        "protocol_id": proto_id,
                        "trial_identifier": identifier,
                        "title": title,
                        "trial_title": trial_title,
                        "source_document": rec.source_document or meta.get("source_document") or f"{rec.trial_id}.pdf",
                        "total_pages_analyzed": rec.source_page_count or meta.get("total_pages_analyzed") or 1,
                        "inclusion_criteria": inclusion,
                        "exclusion_criteria": exclusion,
                        "other_requirements": other,
                        "extraction_metadata": meta.get("extraction_metadata") or {},
                        "processing_status": meta.get("processing_status") or "completed",
                        "status": "processed",
                    }
                    trials_map[rec.trial_id] = item
                    _IN_MEMORY_TRIALS[rec.trial_id] = item
        except Exception as err:
            logger.warning("Failed to fetch trials from database: %s", err)

    return list(trials_map.values())


@router.get(
    "/{trial_id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get clinical trial protocol by ID",
)
async def get_trial_endpoint(trial_id: str) -> Dict[str, Any]:
    """Fetch clinical trial protocol by ID from PostgreSQL database or cache."""
    clean_trial_id = re.sub(r"[^a-zA-Z0-9_-]", "", trial_id.strip())

    if persist_is_configured():
        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                rec = await get_protocol(session, clean_trial_id)
                if rec is not None:
                    meta = decode_json(rec.protocol_metadata, default={}) or {}
                    criteria_list = decode_json(rec.criteria, default=[]) or []

                    inclusion = meta.get("inclusion_criteria") or [
                        c for c in criteria_list if "inc" in str(c.get("type", "")).lower()
                    ]
                    exclusion = meta.get("exclusion_criteria") or [
                        c for c in criteria_list if "exc" in str(c.get("type", "")).lower()
                    ]
                    other = meta.get("other_requirements") or [
                        c for c in criteria_list if "other" in str(c.get("type", "")).lower()
                    ]

                    title = meta.get("title") or meta.get("trial_title") or rec.trial_id
                    trial_title = meta.get("trial_title") or meta.get("title") or rec.trial_id
                    proto_id = meta.get("protocol_id") or rec.trial_id
                    identifier = meta.get("trial_identifier") or proto_id

                    item = {
                        "trial_id": rec.trial_id,
                        "protocol_id": proto_id,
                        "trial_identifier": identifier,
                        "title": title,
                        "trial_title": trial_title,
                        "source_document": rec.source_document or meta.get("source_document") or f"{rec.trial_id}.pdf",
                        "total_pages_analyzed": rec.source_page_count or meta.get("total_pages_analyzed") or 1,
                        "inclusion_criteria": inclusion,
                        "exclusion_criteria": exclusion,
                        "other_requirements": other,
                        "extraction_metadata": meta.get("extraction_metadata") or {},
                        "processing_status": meta.get("processing_status") or "completed",
                        "status": "processed",
                    }
                    _IN_MEMORY_TRIALS[clean_trial_id] = item
                    return item
        except Exception as err:
            logger.warning("Failed to fetch trial %s from database: %s", clean_trial_id, err)

    if clean_trial_id in _IN_MEMORY_TRIALS:
        return _IN_MEMORY_TRIALS[clean_trial_id]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Clinical trial protocol '{clean_trial_id}' not found.",
    )


@router.post(
    "",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Save or register a clinical trial protocol",
)
async def save_trial_endpoint(trial_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a clinical trial protocol to memory and PostgreSQL database."""
    trial_id = trial_payload.get("trial_id") or trial_payload.get("protocol_id")
    if not trial_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trial_id or protocol_id is required in trial payload.",
        )
    clean_trial_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(trial_id).strip())

    trial_data = dict(trial_payload)
    trial_data["trial_id"] = clean_trial_id
    trial_data["trial_title"] = trial_data.get("trial_title") or trial_data.get("title") or clean_trial_id
    trial_data["title"] = trial_data["trial_title"]
    trial_data["trial_identifier"] = trial_data.get("trial_identifier") or clean_trial_id
    trial_data["processing_status"] = trial_data.get("processing_status") or "completed"

    _IN_MEMORY_TRIALS[clean_trial_id] = trial_data

    # Write to storage/pdfs as fallback
    try:
        storage_root = Path(settings.pdf_storage_dir)
        storage_root.mkdir(parents=True, exist_ok=True)
        proto_file = storage_root / f"{clean_trial_id}_protocol.json"
        proto_file.write_text(json.dumps(trial_data, indent=2), encoding="utf-8")
    except Exception as disk_err:
        logger.warning("Could not write trial JSON to disk: %s", disk_err)

    if persist_is_configured():
        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                criteria = (
                    trial_data.get("inclusion_criteria", [])
                    + trial_data.get("exclusion_criteria", [])
                    + trial_data.get("other_requirements", [])
                )
                await create_protocol(
                    session=session,
                    trial_id=clean_trial_id,
                    protocol_metadata=trial_data,
                    source_document=trial_data.get("source_document") or f"{clean_trial_id}.pdf",
                    source_page_count=trial_data.get("total_pages_analyzed") or 1,
                    criteria=criteria,
                )
                await session.commit()
                logger.info("Saved ProtocolRecord to PostgreSQL: trial_id=%s", clean_trial_id)
        except Exception as err:
            logger.warning("Failed to persist trial to database: %s", err)

    return trial_data
