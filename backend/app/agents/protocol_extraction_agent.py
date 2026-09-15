"""Protocol Extraction Agent implementation.

Analyzes page-numbered clinical trial protocol documents using GeminiLLMService
and outputs structured, validated, evidence-traceable Pydantic ExtractedProtocol models.
Enforces zero-hallucination constraints, deterministic IDs, and page citation tracking.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.llm import GeminiLLMService, LLMServiceType, get_llm_service
from app.pdf.processor import PDFDocument
from app.schemas.protocol import (
    CriterionType,
    ExtractedProtocol,
    ProtocolCriterion,
)

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_INSTRUCTION = (
    "You are a clinical trial protocol extraction assistant. "
    "Extract only eligibility criteria explicitly present in the supplied protocol pages. "
    "Identify inclusion criteria separately from exclusion criteria. "
    "Do not infer medical criteria. "
    "Do not create criteria from general medical knowledge. "
    "Do not modify numeric thresholds, units, time windows, medication names, diagnoses, age limits, laboratory limits, or other protocol conditions. "
    "Preserve the meaning and wording of the protocol. "
    "For every criterion provide its exact 1-indexed source page. "
    "If something is ambiguous, preserve the ambiguity rather than inventing information. "
    "Do not make any eligibility or patient decisions. Your sole purpose is faithful structured protocol extraction."
)


class ProtocolExtractionError(Exception):
    """Raised when protocol extraction fails validation or LLM processing."""


class ProtocolExtractionAgent:
    """Agent responsible for parsing clinical trial protocol documents into structured criteria."""

    def __init__(self, llm_service: Optional[LLMServiceType] = None) -> None:
        """Initialize the agent with a centralized LLM service instance.

        Args:
            llm_service: Reusable LLM service instance (instantiated via provider factory if omitted).
        """
        self.llm_service = llm_service or get_llm_service()

    async def extract_protocol(
        self,
        pdf_doc: PDFDocument,
        trial_id: str,
    ) -> ExtractedProtocol:
        """Extract eligibility criteria from a parsed PDFDocument.

        Args:
            pdf_doc: Document containing page-numbered text.
            trial_id: Identifier for the trial.

        Returns:
            ExtractedProtocol containing validated criteria and traceability.

        Raises:
            ProtocolExtractionError: If document is empty or LLM response fails validation.
        """
        if not pdf_doc.pages or pdf_doc.total_pages == 0:
            raise ProtocolExtractionError("Cannot extract protocol from an empty PDF document.")

        total_text_len = sum(len(p.text) for p in pdf_doc.pages)
        logger.info(
            "Starting protocol extraction: trial_id=%s filename=%s pages=%d chars=%d",
            trial_id,
            pdf_doc.filename,
            pdf_doc.total_pages,
            total_text_len,
        )

        prompt = self._build_extraction_prompt(pdf_doc, trial_id)

        raw_result = None
        llm_error: Optional[Exception] = None
        try:
            raw_result = await self.llm_service.generate_json(
                prompt=prompt,
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                temperature=0.0,  # Zero temperature for deterministic, factual extraction
            )
        except Exception as err:
            llm_error = err
            logger.warning(
                "LLM extraction unavailable for trial %s (%s: %s). Falling back to deterministic protocol parser...",
                trial_id,
                type(err).__name__,
                str(err),
            )

        if isinstance(raw_result, dict):
            try:
                protocol = self._build_and_validate_protocol(raw_result, pdf_doc, trial_id)
                if len(protocol.inclusion_criteria) > 0 or len(protocol.exclusion_criteria) > 0:
                    return protocol
            except Exception as val_err:
                logger.warning(
                    "LLM response parsing/validation yielded no criteria for trial %s (%s). Attempting deterministic fallback...",
                    trial_id,
                    val_err,
                )

        # Fallback to deterministic document parsing from PDF pages
        deterministic_protocol = self._extract_deterministically(pdf_doc, trial_id)
        if (
            len(deterministic_protocol.inclusion_criteria) > 0
            or len(deterministic_protocol.exclusion_criteria) > 0
        ):
            logger.info(
                "Deterministic extraction succeeded for trial %s: %d inclusions, %d exclusions",
                trial_id,
                len(deterministic_protocol.inclusion_criteria),
                len(deterministic_protocol.exclusion_criteria),
            )
            return deterministic_protocol

        # If both LLM and deterministic extraction failed to identify criteria
        if llm_error is not None:
            raise ProtocolExtractionError(
                f"Document '{pdf_doc.filename}' contains no identifiable clinical trial inclusion or exclusion criteria "
                f"(LLM extraction failed: {type(llm_error).__name__}). Non-protocol documents (e.g. resumes, invoices, general texts) cannot be processed."
            )
        raise ProtocolExtractionError(
            f"Protocol validation failed: Document '{pdf_doc.filename}' contains no identifiable clinical trial "
            "inclusion or exclusion criteria. Non-protocol documents (e.g. resumes, invoices, general texts) cannot be processed."
        )

    def _build_extraction_prompt(self, pdf_doc: PDFDocument, trial_id: str) -> str:
        """Construct prompt packaging page-numbered text with instructions."""
        formatted_pages: List[str] = []
        for page in pdf_doc.pages:
            formatted_pages.append(
                f"--- BEGIN PAGE {page.page_number} ---\n"
                f"{page.text}\n"
                f"--- END PAGE {page.page_number} ---"
            )

        pages_payload = "\n\n".join(formatted_pages)

        prompt = f"""
Clinical Trial ID: {trial_id}
Document Filename: {pdf_doc.filename}
Total Pages: {pdf_doc.total_pages}

PROTOCOL DOCUMENT PAGES:
{pages_payload}

INSTRUCTIONS:
1. Extract the official protocol_id (e.g., 'SYN-ONC-001') if explicitly present in the text. If not present, use '{trial_id}'.
2. Extract the clinical trial title if mentioned.
3. Extract all explicit INCLUSION CRITERIA.
4. Extract all explicit EXCLUSION CRITERIA.
5. Extract any OTHER explicit eligibility requirements (e.g. study design parameters, age restrictions not listed under inclusion/exclusion).
6. For EACH criterion, you MUST accurately record:
   - "text": Exact/faithful text of the requirement
   - "source_page": The integer page number (1-indexed) where this criterion appears in the text above
   - "section": The section title where it appears (e.g., "Inclusion Criteria", "Exclusion Criteria", "Eligibility")
   - "source_excerpt": A brief direct excerpt (10-30 words) from that specific page serving as source citation

Respond strictly with valid JSON conforming to this schema:
{{
  "protocol_id": "string",
  "title": "string",
  "inclusion_criteria": [
    {{
      "text": "string",
      "source_page": 1,
      "section": "Inclusion Criteria",
      "source_excerpt": "string"
    }}
  ],
  "exclusion_criteria": [
    {{
      "text": "string",
      "source_page": 2,
      "section": "Exclusion Criteria",
      "source_excerpt": "string"
    }}
  ],
  "other_requirements": [
    {{
      "text": "string",
      "source_page": 1,
      "section": "Study Overview",
      "source_excerpt": "string"
    }}
  ]
}}
"""
        return prompt.strip()

    def _build_and_validate_protocol(
        self,
        raw_data: Dict[str, Any],
        pdf_doc: PDFDocument,
        trial_id: str,
    ) -> ExtractedProtocol:
        """Map and normalize raw JSON into validated ExtractedProtocol with deterministic IDs."""
        extracted_protocol_id = str(raw_data.get("protocol_id") or "").strip()
        if not extracted_protocol_id or extracted_protocol_id.lower() in ("unknown", "none", "null"):
            extracted_protocol_id = trial_id

        title = str(raw_data.get("title") or "").strip()

        # Parse inclusion criteria with deterministic IDs (INC-001, INC-002, ...)
        raw_inclusions = (
            raw_data.get("inclusion_criteria")
            or raw_data.get("inclusions")
            or raw_data.get("inclusion")
            or raw_data.get("key_inclusion_criteria")
            or []
        )
        inclusion_criteria: List[ProtocolCriterion] = []
        for idx, item in enumerate(raw_inclusions, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="INC",
                index=idx,
                criterion_type=CriterionType.INCLUSION,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                inclusion_criteria.append(crit)

        # Parse exclusion criteria with deterministic IDs (EXC-001, EXC-002, ...)
        raw_exclusions = (
            raw_data.get("exclusion_criteria")
            or raw_data.get("exclusions")
            or raw_data.get("exclusion")
            or raw_data.get("key_exclusion_criteria")
            or []
        )
        exclusion_criteria: List[ProtocolCriterion] = []
        for idx, item in enumerate(raw_exclusions, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="EXC",
                index=idx,
                criterion_type=CriterionType.EXCLUSION,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                exclusion_criteria.append(crit)

        # Parse other requirements with deterministic IDs (OTHER-001, ...)
        raw_others = (
            raw_data.get("other_requirements")
            or raw_data.get("other_criteria")
            or raw_data.get("other")
            or []
        )
        other_requirements: List[ProtocolCriterion] = []
        for idx, item in enumerate(raw_others, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="OTHER",
                index=idx,
                criterion_type=CriterionType.OTHER,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                other_requirements.append(crit)

        if len(inclusion_criteria) == 0 and len(exclusion_criteria) == 0:
            raise ProtocolExtractionError(
                f"Protocol validation failed: Document '{pdf_doc.filename}' contains no identifiable clinical trial "
                "inclusion or exclusion criteria. Non-protocol documents (e.g. resumes, invoices, general texts) cannot be processed."
            )

        return ExtractedProtocol(
            trial_id=trial_id,
            protocol_id=extracted_protocol_id,
            title=title,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
            other_requirements=other_requirements,
            source_document=pdf_doc.filename,
            extraction_metadata={
                "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "total_pages": pdf_doc.total_pages,
                "model": getattr(self.llm_service, "model", "unknown"),
                "inclusion_count": len(inclusion_criteria),
                "exclusion_count": len(exclusion_criteria),
                "other_count": len(other_requirements),
            },
        )

    def _normalize_criterion(
        self,
        item: Any,
        prefix: str,
        index: int,
        criterion_type: CriterionType,
        trial_id: str,
        total_pages: int,
    ) -> Optional[ProtocolCriterion]:
        """Validate and construct an individual criterion with deterministic ID."""
        if isinstance(item, str):
            clean_str = item.strip()
            # Strip leading numbering like '1. ', '1) ', or bullet
            clean_str = re.sub(r"^(?:(?:\d+|[a-zA-Z])[\.\)]|\u2022|\-|\*|\[\d+\])\s*", "", clean_str).strip()
            if not clean_str:
                return None
            return ProtocolCriterion(
                criterion_id=f"{prefix}-{index:03d}",
                type=criterion_type,
                text=clean_str,
                source_page=1,
                section=f"{criterion_type.value.capitalize()} Criteria",
                source_excerpt=clean_str[:200],
                trial_id=trial_id,
            )

        if not isinstance(item, dict):
            return None

        text = str(
            item.get("text")
            or item.get("criterion")
            or item.get("description")
            or item.get("requirement")
            or ""
        ).strip()
        if not text:
            return None

        # Validate source page
        raw_page = item.get("source_page", item.get("page", item.get("page_number", 1)))
        try:
            page_num = int(raw_page)
            if page_num < 1:
                page_num = 1
            elif total_pages > 0 and page_num > total_pages:
                page_num = total_pages
        except (ValueError, TypeError):
            page_num = 1

        section = str(item.get("section") or item.get("heading") or f"{criterion_type.value.capitalize()} Criteria").strip()
        source_excerpt = item.get("source_excerpt") or item.get("excerpt") or item.get("quote")
        if source_excerpt:
            source_excerpt = str(source_excerpt).strip()
        else:
            source_excerpt = text[:200]

        criterion_id = f"{prefix}-{index:03d}"

        return ProtocolCriterion(
            criterion_id=criterion_id,
            type=criterion_type,
            text=text,
            source_page=page_num,
            section=section,
            source_excerpt=source_excerpt,
            trial_id=trial_id,
        )

    def _extract_deterministically(
        self,
        pdf_doc: PDFDocument,
        trial_id: str,
    ) -> ExtractedProtocol:
        """Deterministically extract protocol criteria from PDFDocument pages.

        Acts as a reliable, grounded fallback when LLM service is offline or fails.
        Extracts sections, assigns exact 1-indexed source pages, excerpts, and deterministic IDs.
        """
        inc_raw: List[Dict[str, Any]] = []
        exc_raw: List[Dict[str, Any]] = []
        other_raw: List[Dict[str, Any]] = []

        extracted_protocol_id = trial_id
        extracted_title = ""

        item_re = re.compile(
            r"^(?:(?:INC|EXC|OTHER)[-_]?\d+\s*[:\.\)]|\bCriterion\s*\d+\s*[:\.\)]|(?:\d+|[a-zA-Z])[\.\)]|\u2022|\-|\*|\[\d+\])\s*(.+)",
            re.UNICODE | re.IGNORECASE,
        )

        current_mode: Optional[str] = None  # 'INC', 'EXC', 'OTHER'
        current_text: str = ""
        current_page: int = 1
        current_section: str = ""

        def flush_current():
            nonlocal current_text, current_mode, current_page, current_section
            if not current_text or not current_mode:
                current_text = ""
                return
            cleaned = re.sub(r"\s+", " ", current_text).strip()
            if len(cleaned) >= 8:
                item = {
                    "text": cleaned,
                    "source_page": current_page,
                    "section": current_section,
                    "source_excerpt": cleaned[:200],
                }
                if current_mode == "INC":
                    inc_raw.append(item)
                elif current_mode == "EXC":
                    exc_raw.append(item)
                elif current_mode == "OTHER":
                    other_raw.append(item)
            current_text = ""

        for p in pdf_doc.pages:
            lines = [l.strip() for l in p.text.splitlines() if l.strip()]
            for line in lines:
                # Look for protocol ID e.g. Protocol ID: SYN-CARDIO-001
                if not extracted_protocol_id or extracted_protocol_id == trial_id:
                    proto_m = re.search(r"(?:protocol\s*(?:id|number|no\.?|code)\s*[:#-]?\s*)([A-Za-z0-9_-]{4,30})", line, re.I)
                    if proto_m:
                        extracted_protocol_id = proto_m.group(1).strip()

                # Look for title on first page
                if not extracted_title and p.page_number == 1:
                    if "protocol" in line.lower() and not re.search(r"protocol\s*id", line, re.I):
                        extracted_title = line.strip()

                # Section header detection
                if re.search(r"^(?:key\s+)?inclusion\s+(?:criteria|requirements)\b", line, re.I):
                    flush_current()
                    current_mode = "INC"
                    current_page = p.page_number
                    current_section = "Inclusion Criteria"
                    continue
                elif re.search(r"^(?:key\s+)?exclusion\s+(?:criteria|requirements)\b", line, re.I):
                    flush_current()
                    current_mode = "EXC"
                    current_page = p.page_number
                    current_section = "Exclusion Criteria"
                    continue
                elif re.search(r"^(?:study\s+parameters|other\s+requirements|eligibility\s+overview)\b", line, re.I):
                    flush_current()
                    current_mode = "OTHER"
                    current_page = p.page_number
                    current_section = "Other Requirements"
                    continue
                elif re.search(
                    r"^(?:required\s+screening|investigations|study\s+treatment|endpoints|study\s+procedures|safety\s+monitoring|statistical\s+analysis|discontinuation|withdrawal|references)\b",
                    line,
                    re.I,
                ):
                    flush_current()
                    current_mode = None
                    continue

                if current_mode:
                    # Check for multiple criteria packed into a single line (e.g. EXC-007: ... EXC-008: ...)
                    inline_splits = re.split(r"(?=(?:INC|EXC|OTHER)[-_]?\d+\s*[:\.\)])", line, flags=re.I)
                    if len(inline_splits) > 1 and any(re.match(r"^(?:INC|EXC|OTHER)[-_]?\d+", s, re.I) for s in inline_splits if s.strip()):
                        for chunk in inline_splits:
                            chunk = chunk.strip()
                            if not chunk:
                                continue
                            m_chunk = item_re.match(chunk)
                            if m_chunk:
                                flush_current()
                                current_text = m_chunk.group(1)
                                current_page = p.page_number
                            elif current_text:
                                current_text += " " + chunk
                        continue

                    m = item_re.match(line)
                    if m:
                        flush_current()
                        current_text = m.group(1)
                        current_page = p.page_number
                    elif current_text:
                        current_text += " " + line
                    elif len(line) >= 20 and not re.match(r"^(?:inclusion|exclusion|criteria|section|page)\b", line, re.I):
                        current_text = line
                        current_page = p.page_number

        flush_current()

        # Build normalized criteria
        inclusions: List[ProtocolCriterion] = []
        for idx, item in enumerate(inc_raw, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="INC",
                index=idx,
                criterion_type=CriterionType.INCLUSION,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                inclusions.append(crit)

        exclusions: List[ProtocolCriterion] = []
        for idx, item in enumerate(exc_raw, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="EXC",
                index=idx,
                criterion_type=CriterionType.EXCLUSION,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                exclusions.append(crit)

        others: List[ProtocolCriterion] = []
        for idx, item in enumerate(other_raw, start=1):
            crit = self._normalize_criterion(
                item=item,
                prefix="OTHER",
                index=idx,
                criterion_type=CriterionType.OTHER,
                trial_id=trial_id,
                total_pages=pdf_doc.total_pages,
            )
            if crit:
                others.append(crit)

        if not extracted_title:
            extracted_title = pdf_doc.filename.replace(".pdf", "").replace("_", " ")

        return ExtractedProtocol(
            trial_id=trial_id,
            protocol_id=extracted_protocol_id or trial_id,
            title=extracted_title,
            inclusion_criteria=inclusions,
            exclusion_criteria=exclusions,
            other_requirements=others,
            source_document=pdf_doc.filename,
            extraction_metadata={
                "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "total_pages": pdf_doc.total_pages,
                "model": "deterministic_fallback_extractor",
                "inclusion_count": len(inclusions),
                "exclusion_count": len(exclusions),
                "other_count": len(others),
            },
        )
