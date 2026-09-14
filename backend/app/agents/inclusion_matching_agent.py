"""Inclusion Matching Agent for Clinical Trial Eligibility.

Evaluates ONLY inclusion criteria for a selected clinical trial against
structured patient profiles. Enforces strict trial isolation, criterion-type validation,
deterministic threshold comparison, zero/false preservation, and complete evidence traceability.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from app.agents.deterministic_comparator import DeterministicComparator
from app.llm.gemini_service import GeminiLLMService
from app.schemas.inclusion import (
    InclusionAssessment,
    InclusionCriterionAssessment,
    InclusionStatus,
)
from app.schemas.patient import PatientProfile
from app.schemas.rag import ProtocolChunk, RetrievedChunk
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)


class TrialIsolationError(ValueError):
    """Raised when retrieved evidence does not match the authoritative selected trial."""


class CriterionTypeError(ValueError):
    """Raised when a non-inclusion criterion is submitted to the inclusion agent."""


class InclusionMatchingAgent:
    """Agent that performs criterion-by-criterion evaluation of inclusion requirements.
    
    Adheres strictly to:
    - Selected trial authoritative scoping (trial isolation).
    - Rejection of cross-trial evidence or exclusion criteria.
    - Deterministic numerical and boolean comparison.
    - Zero (0) and False boolean preservation (not treated as missing).
    - Mandatory UNKNOWN outcome when patient information is missing.
    - Traceable provenance linking to source documents and page numbers.
    """

    def __init__(
        self,
        comparator: Optional[DeterministicComparator] = None,
        llm_service: Optional[GeminiLLMService] = None,
    ) -> None:
        self.comparator = comparator or DeterministicComparator()
        self.llm_service = llm_service or GeminiLLMService()

    async def evaluate(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        retrieved_evidence: List[Union[RetrievedChunk, ProtocolChunk, Dict[str, Any]]],
    ) -> InclusionAssessment:
        """Evaluate inclusion criteria for the selected trial against the patient profile.

        Args:
            trial_id: Authoritative clinical trial ID (e.g. 'SYN-ONC-001').
            patient_profile: Structured patient clinical profile.
            retrieved_evidence: List of protocol chunks or retrieved criteria.

        Returns:
            InclusionAssessment containing criterion-level and overall assessments.

        Raises:
            ValueError: If trial_id is empty or no evidence is provided.
            TrialIsolationError: If any evidence chunk belongs to a different trial.
            CriterionTypeError: If any evidence chunk is an exclusion criterion.
        """
        clean_trial_id = (trial_id or "").strip()
        if not clean_trial_id:
            raise ValueError("trial_id must not be empty.")

        if not retrieved_evidence:
            logger.warning("Empty retrieved evidence provided for trial %s", clean_trial_id)
            return InclusionAssessment(
                trial_id=clean_trial_id,
                patient_profile_id=patient_profile.patient_profile_id,
                overall_status=InclusionStatus.UNKNOWN,
                criteria=[],
                missing_information=[],
                warnings=["No inclusion criteria provided for evaluation."],
            )

        criteria_assessments: List[InclusionCriterionAssessment] = []
        missing_information_set: set[str] = set()
        warnings: List[str] = []

        for chunk in retrieved_evidence:
            # 1. Normalize chunk properties
            c_trial_id = getattr(chunk, "trial_id", None) or (chunk.get("trial_id") if isinstance(chunk, dict) else None)
            c_id = getattr(chunk, "criterion_id", None) or (chunk.get("criterion_id") if isinstance(chunk, dict) else None) or "INC-UNKNOWN"
            c_type = getattr(chunk, "criterion_type", None) or (chunk.get("criterion_type") if isinstance(chunk, dict) else None) or ""
            c_text = getattr(chunk, "text", None) or (chunk.get("text") if isinstance(chunk, dict) else None) or ""
            c_page = getattr(chunk, "source_page", None) or (chunk.get("source_page") if isinstance(chunk, dict) else 1)
            c_doc = getattr(chunk, "source_document", None) or (chunk.get("source_document") if isinstance(chunk, dict) else "unknown_document")
            c_excerpt = getattr(chunk, "source_excerpt", None) or (chunk.get("source_excerpt") if isinstance(chunk, dict) else None)

            # 2. TRIAL ISOLATION CHECK
            # If evidence belongs to another trial: DO NOT evaluate it. Reject immediately.
            if c_trial_id != clean_trial_id:
                msg = (
                    f"Trial isolation violation: retrieved criterion '{c_id}' belongs to trial '{c_trial_id}', "
                    f"which does not match selected trial '{clean_trial_id}'."
                )
                logger.error(msg)
                raise TrialIsolationError(msg)

            # 3. CRITERION TYPE VALIDATION
            # Only evaluate criterion_type == inclusion. Reject exclusion or other types.
            if c_type.lower() != "inclusion":
                msg = (
                    f"Criterion type validation error: criterion '{c_id}' has type '{c_type}'. "
                    f"The Inclusion Matching Agent only accepts inclusion criteria."
                )
                logger.error(msg)
                raise CriterionTypeError(msg)

            # 4. DETERMINISTIC COMPARISON
            assessment, missing_field = self.comparator.evaluate_criterion(
                trial_id=clean_trial_id,
                criterion_id=c_id,
                criterion_text=c_text,
                source_page=int(c_page),
                source_document=str(c_doc),
                source_excerpt=c_excerpt,
                patient_profile=patient_profile,
            )

            # 5. OPTIONAL GEMINI NARRATIVE INTERPRETATION
            # Only use Gemini if deterministic evaluation yielded UNKNOWN due to narrative complexity
            # (NOT due to missing patient data) AND Gemini is configured.
            if (
                assessment.status == InclusionStatus.UNKNOWN
                and missing_field is None
                and self.llm_service.is_configured
            ):
                narrative_timer = start_timer()
                assessment = await self._try_narrative_interpretation(
                    assessment=assessment,
                    patient_profile=patient_profile,
                )
                log_stage(
                    "inclusion.narrative",
                    narrative_timer.elapsed_ms(),
                    ok=True,
                    detail=f"trial={clean_trial_id} criterion={c_id}",
                )

            if missing_field:
                missing_information_set.add(missing_field)

            criteria_assessments.append(assessment)

        # 6. OVERALL STATUS COMPUTATION
        # - If ANY inclusion criterion is FAIL: overall_status = FAIL
        # - If no criterion is FAIL but ANY required criterion is UNKNOWN: overall_status = UNKNOWN
        # - Only if ALL required inclusion criteria PASS: overall_status = PASS
        has_fail = any(c.status == InclusionStatus.FAIL for c in criteria_assessments)
        has_unknown = any(c.status == InclusionStatus.UNKNOWN for c in criteria_assessments)

        if has_fail:
            overall_status = InclusionStatus.FAIL
        elif has_unknown:
            overall_status = InclusionStatus.UNKNOWN
        else:
            overall_status = InclusionStatus.PASS

        return InclusionAssessment(
            trial_id=clean_trial_id,
            patient_profile_id=patient_profile.patient_profile_id,
            overall_status=overall_status,
            criteria=criteria_assessments,
            missing_information=sorted(list(missing_information_set)),
            warnings=warnings,
        )

    async def _try_narrative_interpretation(
        self,
        assessment: InclusionCriterionAssessment,
        patient_profile: PatientProfile,
    ) -> InclusionCriterionAssessment:
        """Invokes GeminiLLMService strictly for narrative criteria interpretation."""
        prompt = (
            f"You are a clinical protocol reviewer assessing a patient against a single clinical trial INCLUSION criterion.\n"
            f"Protocol Requirement: \"{assessment.criterion_text}\"\n"
            f"Patient Profile Facts:\n{patient_profile.model_dump_json(indent=2)}\n\n"
            f"STRICT RULES:\n"
            f"1. Use ONLY the supplied patient facts. Do not assume or invent missing data.\n"
            f"2. If relevant patient information is not documented, status MUST be 'UNKNOWN'.\n"
            f"3. Return ONLY valid JSON with keys: 'status' ('PASS', 'FAIL', or 'UNKNOWN'), "
            f"'patient_value' (extracted string/fact or null), 'expected_requirement' (string), "
            f"'rationale' (string explanation).\n"
            f"4. Do NOT make an overall trial eligibility decision."
        )

        try:
            res = await self.llm_service.generate_json(
                prompt=prompt,
                temperature=0.0,
            )
            if isinstance(res, dict):
                raw_status = str(res.get("status", "UNKNOWN")).upper()
                if raw_status in ("PASS", "FAIL", "UNKNOWN"):
                    status = InclusionStatus(raw_status)
                    return InclusionCriterionAssessment(
                        criterion_id=assessment.criterion_id,
                        trial_id=assessment.trial_id,
                        status=status,
                        criterion_text=assessment.criterion_text,
                        patient_value=res.get("patient_value", assessment.patient_value),
                        expected_requirement=res.get("expected_requirement", assessment.expected_requirement),
                        rationale=res.get("rationale", assessment.rationale),
                        evidence=assessment.evidence,
                        source_page=assessment.source_page,
                        source_document=assessment.source_document,
                        source_excerpt=assessment.source_excerpt,
                    )
        except Exception as err:
            logger.warning("Gemini narrative interpretation fallback failed: %s", err)

        return assessment
