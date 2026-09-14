"""Exclusion Detection Agent for Clinical Trial Eligibility.

Evaluates ONLY exclusion criteria for a selected clinical trial against
structured patient profiles. Enforces strict trial isolation, criterion-type validation,
deterministic threshold/operator evaluation, boolean/zero preservation, temporal proximity
calculations, and auditable provenance traceability.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.llm.gemini_service import GeminiLLMService
from app.schemas.exclusion import (
    ExclusionAssessment,
    ExclusionCriterionAssessment,
    ExclusionStatus,
)
from app.schemas.patient import PatientProfile, PregnancyStatus
from app.schemas.rag import ProtocolChunk, RetrievedChunk

logger = logging.getLogger(__name__)


class TrialIsolationError(ValueError):
    """Raised when retrieved evidence does not match the authoritative selected trial."""


class CriterionTypeError(ValueError):
    """Raised when a non-exclusion criterion is submitted to the exclusion agent."""


class ExclusionComparator:
    """Deterministic rule-based clinical comparator for exclusion criteria."""

    # Regex patterns for clinical operator extraction
    _RE_GTE = re.compile(r"(?:>=|≥|greater than or equal to|at least)\s*(?P<val>\d+(?:\.\d+)?)", re.IGNORECASE)
    _RE_GT = re.compile(r"(?:>|greater than|strictly greater than|exceeding|more than)\s*(?P<val>\d+(?:\.\d+)?)", re.IGNORECASE)
    _RE_LTE = re.compile(r"(?:<=|≤|less than or equal to|at most|no more than)\s*(?P<val>\d+(?:\.\d+)?)", re.IGNORECASE)
    _RE_LT = re.compile(r"(?:<|less than|strictly less than|below|under)\s*(?P<val>\d+(?:\.\d+)?)", re.IGNORECASE)
    _RE_RANGE = re.compile(r"(?:between|from)?\s*(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|to|and)\s*(?P<high>\d+(?:\.\d+)?)", re.IGNORECASE)

    # Temporal pattern (e.g., "within 12 months", "within 4 weeks", "within 30 days", "within 1 year")
    _RE_TEMPORAL = re.compile(
        r"within\s*(?P<num>\d+)\s*(?P<unit>day|days|week|weeks|month|months|year|years)",
        re.IGNORECASE,
    )
    _RE_DATE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")

    def evaluate_criterion(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
        reference_date: Optional[date] = None,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        """Evaluates a single exclusion criterion deterministically against the patient profile.

        Returns:
            Tuple of (ExclusionCriterionAssessment, missing_field_identifier or None).
        """
        text_lower = criterion_text.lower()
        ref_dt = reference_date or date(2026, 9, 14)

        # 1. Clinical status: Active Serious Infection
        #    Must be checked BEFORE the temporal handler because protocol text
        #    like "active serious infection ... within 14 days" is a clinical-status
        #    boolean, not a dated therapy event.
        if "active serious infection" in text_lower or "active infection" in text_lower:
            return self._evaluate_infection_status(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 2. Clinical status: Uncontrolled Cardiac Disease
        #    Must be checked BEFORE the temporal handler because protocol text
        #    like "uncontrolled cardiac disease ... within 6 months" is a clinical-status
        #    boolean, not a dated cardiac-event exclusion.
        if "cardiac disease" in text_lower or ("cardiac" in text_lower and "uncontrolled" in text_lower):
            return self._evaluate_cardiac_status(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 3. Temporal exclusions (e.g. stroke within 12 months, systemic therapy within 4 weeks)
        temporal_match = self._RE_TEMPORAL.search(text_lower)
        if temporal_match:
            return self._evaluate_temporal_exclusion(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
                match=temporal_match,
                reference_date=ref_dt,
            )

        # 4. Renal / eGFR exclusions (e.g., "eGFR < 30", "creatinine clearance < 45")
        if "egfr" in text_lower or "glomerular filtration" in text_lower or "creatinine clearance" in text_lower:
            return self._evaluate_egfr(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 5. ECOG Performance Status exclusions (e.g., "ECOG > 1", "ECOG >= 2")
        if "ecog" in text_lower:
            return self._evaluate_ecog(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 6. Hematology: ANC (e.g., "ANC < 1.5", "ANC < 1000")
        if bool(re.search(r"\banc\b", text_lower)) or "absolute neutrophil" in text_lower:
            return self._evaluate_anc(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 7. Hematology: Platelets (e.g., "Platelets < 100,000", "Platelets < 100")
        if "platelet" in text_lower or "platelets" in text_lower or bool(re.search(r"\bplt\b", text_lower)):
            return self._evaluate_platelets(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 8. Hematology: Hemoglobin (e.g., "Hemoglobin < 9.0 g/dL")
        if "hemoglobin" in text_lower or bool(re.search(r"\b(hgb|hb)\b", text_lower)):
            return self._evaluate_hemoglobin(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 9. Hepatic: Bilirubin (e.g., "Bilirubin > 1.5 x ULN")
        if "bilirubin" in text_lower:
            return self._evaluate_bilirubin(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 10. Hepatic: AST / ALT (e.g., "AST > 2.5 x ULN", "ALT > 3.0")
        if bool(re.search(r"\b(ast|alt|sgot|sgpt)\b", text_lower)) or "transaminase" in text_lower:
            return self._evaluate_transaminases(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 11. Blood pressure (e.g., "Systolic BP > 160 mmHg", "Diastolic > 100")
        if "blood pressure" in text_lower or "systolic" in text_lower or "diastolic" in text_lower:
            return self._evaluate_blood_pressure(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 12. Demographics: Pregnancy
        if "pregnant" in text_lower or "pregnancy" in text_lower:
            return self._evaluate_pregnancy(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 13. Demographics: Breastfeeding
        if "breastfeeding" in text_lower or "lactating" in text_lower or "nursing" in text_lower:
            return self._evaluate_breastfeeding(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 14. Age exclusions (e.g. "Age < 18", "Age > 80")
        if bool(re.search(r"\b(age|aged)\b", text_lower)) or "years of age" in text_lower or "years old" in text_lower:
            return self._evaluate_age(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 15. Categorical condition exclusions (e.g., Asthma, Stroke, Brain Metastases)
        return self._evaluate_condition_exclusion(
            trial_id=trial_id,
            criterion_id=criterion_id,
            criterion_text=criterion_text,
            source_page=source_page,
            source_document=source_document,
            source_excerpt=source_excerpt,
            patient_profile=patient_profile,
        )

    # -------------------------------------------------------------------------
    # Numerical Comparison for Exclusions
    # -------------------------------------------------------------------------

    def _compare_numerical_exclusion(
        self,
        value: float,
        value_name: str,
        text: str,
    ) -> Tuple[ExclusionStatus, str, str]:
        """Compares numeric patient fact against an exclusion threshold.
        
        Semantics:
        - If value satisfies the exclusion operator -> TRIGGERED
        - If value does NOT satisfy the exclusion operator -> CLEAR
        - Boundary handling:
          eGFR < 30: value 30 is NOT < 30 -> CLEAR
          eGFR <= 30: value 30 is <= 30 -> TRIGGERED
        """
        # Less than or equal to: e.g. <= 30
        m_lte = self._RE_LTE.search(text)
        if m_lte:
            req = float(m_lte.group("val"))
            expected = f"<= {req}"
            if value <= req:
                return (
                    ExclusionStatus.TRIGGERED,
                    expected,
                    f"Patient {value_name} of {value} satisfies the exclusion condition (<= {req}).",
                )
            return (
                ExclusionStatus.CLEAR,
                expected,
                f"Patient {value_name} of {value} is not less than or equal to exclusion threshold (<= {req}).",
            )

        # Strictly less than: e.g. < 30
        m_lt = self._RE_LT.search(text)
        if m_lt:
            req = float(m_lt.group("val"))
            expected = f"< {req}"
            if value < req:
                return (
                    ExclusionStatus.TRIGGERED,
                    expected,
                    f"Patient {value_name} of {value} satisfies the exclusion threshold (< {req}).",
                )
            return (
                ExclusionStatus.CLEAR,
                expected,
                f"Patient {value_name} of {value} is not less than exclusion threshold (< {req}).",
            )

        # Greater than or equal to: e.g. >= 2.5
        m_gte = self._RE_GTE.search(text)
        if m_gte:
            req = float(m_gte.group("val"))
            expected = f">= {req}"
            if value >= req:
                return (
                    ExclusionStatus.TRIGGERED,
                    expected,
                    f"Patient {value_name} of {value} satisfies the exclusion threshold (>= {req}).",
                )
            return (
                ExclusionStatus.CLEAR,
                expected,
                f"Patient {value_name} of {value} is not greater than or equal to exclusion threshold (>= {req}).",
            )

        # Strictly greater than: e.g. > 1.5
        m_gt = self._RE_GT.search(text)
        if m_gt:
            req = float(m_gt.group("val"))
            expected = f"> {req}"
            if value > req:
                return (
                    ExclusionStatus.TRIGGERED,
                    expected,
                    f"Patient {value_name} of {value} satisfies the exclusion threshold (> {req}).",
                )
            return (
                ExclusionStatus.CLEAR,
                expected,
                f"Patient {value_name} of {value} is not greater than exclusion threshold (> {req}).",
            )

        # Inclusive range
        m_range = self._RE_RANGE.search(text)
        if m_range:
            low = float(m_range.group("low"))
            high = float(m_range.group("high"))
            expected = f"{low} - {high}"
            if low <= value <= high:
                return (
                    ExclusionStatus.TRIGGERED,
                    expected,
                    f"Patient {value_name} of {value} falls within the excluded range ({expected}).",
                )
            return (
                ExclusionStatus.CLEAR,
                expected,
                f"Patient {value_name} of {value} is outside the excluded range ({expected}).",
            )

        return (
            ExclusionStatus.UNKNOWN,
            text,
            f"Could not deterministically extract numerical exclusion operator from: '{text}'.",
        )

    # -------------------------------------------------------------------------
    # Specific Domain Handlers
    # -------------------------------------------------------------------------

    def _evaluate_egfr(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.egfr:
            val = patient_profile.labs.egfr.value

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="eGFR evaluation threshold",
                    rationale="Required laboratory value eGFR is missing from the patient record. Cannot determine exclusion.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.egfr",
            )

        status, req, rationale = self._compare_numerical_exclusion(val, "eGFR", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"labs.egfr": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "labs.egfr",
        )

    def _evaluate_infection_status(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        infection = None
        if patient_profile.clinical_status:
            infection = patient_profile.clinical_status.active_serious_infection

        if infection is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="No active serious infection",
                    rationale="Active serious infection status is not documented. Cannot determine if exclusion condition is present.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.active_serious_infection",
            )

        if infection is True:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.TRIGGERED,
                    criterion_text=criterion_text,
                    patient_value=True,
                    exclusion_requirement="Active serious infection = false",
                    rationale="Patient has documented active serious infection (True), triggering protocol exclusion.",
                    evidence={"clinical_status.active_serious_infection": True},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text=criterion_text,
                patient_value=False,
                exclusion_requirement="Active serious infection = false",
                rationale="Patient is documented as having no active serious infection (False), clearing exclusion.",
                evidence={"clinical_status.active_serious_infection": False},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_cardiac_status(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        cardiac = None
        if patient_profile.clinical_status:
            cardiac = patient_profile.clinical_status.uncontrolled_cardiac_disease

        if cardiac is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="No uncontrolled cardiac disease",
                    rationale="Uncontrolled cardiac disease status is not documented in clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.uncontrolled_cardiac_disease",
            )

        if cardiac is True:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.TRIGGERED,
                    criterion_text=criterion_text,
                    patient_value=True,
                    exclusion_requirement="Uncontrolled cardiac disease = false",
                    rationale="Patient has documented uncontrolled cardiac disease, triggering protocol exclusion.",
                    evidence={"clinical_status.uncontrolled_cardiac_disease": True},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text=criterion_text,
                patient_value=False,
                exclusion_requirement="Uncontrolled cardiac disease = false",
                rationale="Patient is documented as having no uncontrolled cardiac disease (False), clearing exclusion.",
                evidence={"clinical_status.uncontrolled_cardiac_disease": False},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_ecog(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        ecog = None
        if patient_profile.clinical_status:
            ecog = patient_profile.clinical_status.ecog_performance_status

        # ECOG == 0 is NOT missing!
        if ecog is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="ECOG performance status",
                    rationale="ECOG score is not documented in clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.ecog_performance_status",
            )

        text_lower = criterion_text.lower()
        # Common exclusion: "ECOG > 1" or "ECOG >= 2"
        if ">= 2" in text_lower or "> 1" in text_lower or "2 or greater" in text_lower:
            req = "ECOG <= 1 (excluded if >= 2)"
            if ecog >= 2:
                status = ExclusionStatus.TRIGGERED
                rationale = f"Patient ECOG score of {ecog} triggers exclusion (>= 2)."
            else:
                status = ExclusionStatus.CLEAR
                rationale = f"Patient ECOG score of {ecog} does not trigger exclusion (>= 2)."
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=status,
                    criterion_text=criterion_text,
                    patient_value=ecog,
                    exclusion_requirement=req,
                    rationale=rationale,
                    evidence={"clinical_status.ecog_performance_status": ecog},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        status, req, rationale = self._compare_numerical_exclusion(float(ecog), "ECOG", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=ecog,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"clinical_status.ecog_performance_status": ecog},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "clinical_status.ecog_performance_status",
        )

    def _evaluate_anc(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.anc:
            val = patient_profile.labs.anc.value

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="ANC threshold",
                    rationale="Absolute Neutrophil Count (ANC) is missing from patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.anc",
            )

        status, req, rationale = self._compare_numerical_exclusion(val, "ANC", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"labs.anc": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "labs.anc",
        )

    def _evaluate_platelets(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.platelets:
            val = patient_profile.labs.platelets.value

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Platelets threshold",
                    rationale="Platelet count is missing from patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.platelets",
            )

        normalized_text = criterion_text
        if "100,000" in normalized_text and val <= 1000:
            normalized_text = normalized_text.replace("100,000", "100")
        elif "75,000" in normalized_text and val <= 1000:
            normalized_text = normalized_text.replace("75,000", "75")

        status, req, rationale = self._compare_numerical_exclusion(val, "Platelet count", normalized_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"labs.platelets": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "labs.platelets",
        )

    def _evaluate_hemoglobin(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.hemoglobin:
            val = patient_profile.labs.hemoglobin.value

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Hemoglobin threshold",
                    rationale="Hemoglobin measurement is missing from patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.hemoglobin",
            )

        status, req, rationale = self._compare_numerical_exclusion(val, "Hemoglobin", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"labs.hemoglobin": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "labs.hemoglobin",
        )

    def _evaluate_bilirubin(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.bilirubin:
            val = patient_profile.labs.bilirubin.value

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Bilirubin threshold",
                    rationale="Total bilirubin is missing from patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.bilirubin",
            )

        status, req, rationale = self._compare_numerical_exclusion(val, "Bilirubin", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"labs.bilirubin": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "labs.bilirubin",
        )

    def _evaluate_transaminases(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        text_lower = criterion_text.lower()
        ast_val = patient_profile.labs.ast.value if patient_profile.labs and patient_profile.labs.ast else None
        alt_val = patient_profile.labs.alt.value if patient_profile.labs and patient_profile.labs.alt else None

        # Check if AST or ALT is specifically targeted
        if "ast" in text_lower and not ("alt" in text_lower):
            target_val = ast_val
            target_name = "AST"
            field_name = "labs.ast"
        elif "alt" in text_lower and not ("ast" in text_lower):
            target_val = alt_val
            target_name = "ALT"
            field_name = "labs.alt"
        else:
            # Both transaminases or generic transaminase
            vals = [v for v in (ast_val, alt_val) if v is not None]
            target_val = max(vals) if vals else None
            target_name = "AST/ALT max"
            field_name = "labs.ast_alt"

        if target_val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Transaminase threshold",
                    rationale=f"Hepatic transaminase measurement ({target_name}) is missing from patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                field_name,
            )

        status, req, rationale = self._compare_numerical_exclusion(target_val, target_name, criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=target_val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={field_name: target_val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else field_name,
        )

    def _evaluate_blood_pressure(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        bp = None
        if patient_profile.vital_signs:
            bp = patient_profile.vital_signs.blood_pressure

        text_lower = criterion_text.lower()
        if "diastolic" in text_lower and not ("systolic" in text_lower):
            val = bp.diastolic if bp else None
            name = "diastolic blood pressure"
            f_name = "vital_signs.blood_pressure.diastolic"
        else:
            val = bp.systolic if bp else None
            name = "systolic blood pressure"
            f_name = "vital_signs.blood_pressure.systolic"

        if val is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Blood pressure threshold",
                    rationale=f"{name.capitalize()} is missing from vital signs record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                f_name,
            )

        status, req, rationale = self._compare_numerical_exclusion(float(val), name, criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={f_name: val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else f_name,
        )

    def _evaluate_pregnancy(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        preg = None
        if patient_profile.demographics:
            preg = patient_profile.demographics.pregnancy_status

        if preg is None or preg == PregnancyStatus.UNKNOWN:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Documented pregnancy status",
                    rationale="Patient pregnancy status is unknown or not documented.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.pregnancy_status",
            )

        if preg == PregnancyStatus.PREGNANT:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.TRIGGERED,
                    criterion_text=criterion_text,
                    patient_value=preg.value,
                    exclusion_requirement="Not pregnant",
                    rationale="Patient is documented as pregnant, triggering exclusion.",
                    evidence={"demographics.pregnancy_status": preg.value},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text=criterion_text,
                patient_value=preg.value,
                exclusion_requirement="Not pregnant",
                rationale="Patient is documented as not pregnant, clearing exclusion.",
                evidence={"demographics.pregnancy_status": preg.value},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_breastfeeding(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        bf = None
        if patient_profile.demographics:
            bf = patient_profile.demographics.breastfeeding_status

        if bf is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Not breastfeeding",
                    rationale="Patient breastfeeding status is not documented in demographics.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.breastfeeding_status",
            )

        if bf is True:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.TRIGGERED,
                    criterion_text=criterion_text,
                    patient_value=True,
                    exclusion_requirement="Breastfeeding = false",
                    rationale="Patient is documented as breastfeeding, triggering exclusion.",
                    evidence={"demographics.breastfeeding_status": True},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text=criterion_text,
                patient_value=False,
                exclusion_requirement="Breastfeeding = false",
                rationale="Patient is documented as not breastfeeding (False), clearing exclusion.",
                evidence={"demographics.breastfeeding_status": False},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_age(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        age = None
        if patient_profile.demographics:
            age = patient_profile.demographics.age

        if age is None:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement="Age threshold",
                    rationale="Patient age is missing from demographics record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.age",
            )

        status, req, rationale = self._compare_numerical_exclusion(float(age), "age", criterion_text)
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=age,
                exclusion_requirement=req,
                rationale=rationale,
                evidence={"demographics.age": age},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None if status != ExclusionStatus.UNKNOWN else "demographics.age",
        )

    # -------------------------------------------------------------------------
    # Categorical & Condition Exclusions
    # -------------------------------------------------------------------------

    def _evaluate_condition_exclusion(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        """Evaluates categorical condition exclusions (e.g. Asthma, Stroke, Brain Metastases).
        
        CRITICAL SEMANTICS:
        - If condition is documented as active/present -> TRIGGERED
        - If condition is NOT documented -> UNKNOWN (absence of documentation is NOT proof of absence!)
        - Only if explicitly documented as negative/absent -> CLEAR
        """
        text_lower = criterion_text.lower()
        patient_conditions = patient_profile.conditions or []

        # Extract target disease terms
        target_terms: List[str] = []
        if "asthma" in text_lower:
            target_terms = ["asthma"]
        elif "stroke" in text_lower or "tia" in text_lower or "transient ischemic attack" in text_lower:
            target_terms = ["stroke", "tia", "transient ischemic attack", "cerebrovascular accident"]
        elif "myocardial infarction" in text_lower or bool(re.search(r"\bmi\b", text_lower)):
            target_terms = ["myocardial infarction", "heart attack", "mi"]
        elif "brain metastas" in text_lower or "cns metastas" in text_lower:
            target_terms = ["brain metastasis", "brain metastases", "cns metastasis", "cns metastases"]
        elif "autoimmune" in text_lower:
            target_terms = ["autoimmune", "lupus", "rheumatoid arthritis", "crohn", "ulcerative colitis"]
        elif "hiv" in text_lower:
            target_terms = ["hiv", "human immunodeficiency virus"]
        elif "hepatitis b" in text_lower or "hbv" in text_lower:
            target_terms = ["hepatitis b", "hbv"]
        elif "hepatitis c" in text_lower or "hcv" in text_lower:
            target_terms = ["hepatitis c", "hcv"]
        else:
            # Fallback to key meaningful words from criterion
            words = [w for w in re.findall(r"[a-z]+", text_lower) if len(w) > 4 and w not in (
                "patient", "patients", "history", "active", "evidence", "presence", "documented", "protocol", "exclusion"
            )]
            target_terms = words or [criterion_text]

        # 1. Check if patient has matching documented condition
        for cond in patient_conditions:
            if not cond.documented:
                continue
            cond_name_lower = cond.name.lower()
            cond_status_lower = (cond.status or "").lower()

            matches = any(term in cond_name_lower for term in target_terms)
            if matches:
                # Check if documented explicitly as absent/negative
                if any(neg in cond_name_lower or neg in cond_status_lower for neg in ("negative", "none", "no history", "resolved")):
                    return (
                        ExclusionCriterionAssessment(
                            criterion_id=criterion_id,
                            trial_id=trial_id,
                            status=ExclusionStatus.CLEAR,
                            criterion_text=criterion_text,
                            patient_value=f"{cond.name} ({cond.status})",
                            exclusion_requirement=f"Absence of {target_terms[0]}",
                            rationale=f"Condition explicitly documented as inactive/resolved/negative: '{cond.name}'.",
                            evidence={"conditions": cond.name},
                            source_page=source_page,
                            source_document=source_document,
                            source_excerpt=source_excerpt,
                        ),
                        None,
                    )

                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.TRIGGERED,
                        criterion_text=criterion_text,
                        patient_value=f"{cond.name} (status: {cond.status})",
                        exclusion_requirement=f"No {target_terms[0]}",
                        rationale=f"Patient has documented diagnosis of '{cond.name}', triggering protocol exclusion.",
                        evidence={"conditions": cond.name},
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    None,
                )

        # 2. Condition is NOT documented in medical record
        # STRICT RULE: Absence of documentation is NOT proof of absence -> UNKNOWN!
        primary_term = target_terms[0] if target_terms else criterion_text
        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.UNKNOWN,
                criterion_text=criterion_text,
                patient_value=None,
                exclusion_requirement=f"Absence of {primary_term}",
                rationale=f"Medical record does not document presence or explicit absence of '{primary_term}'. Absence of documentation cannot be assumed as CLEAR.",
                evidence=None,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            f"conditions.{primary_term}",
        )

    # -------------------------------------------------------------------------
    # Temporal Exclusions
    # -------------------------------------------------------------------------

    def _evaluate_temporal_exclusion(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
        match: re.Match,
        reference_date: date,
    ) -> Tuple[ExclusionCriterionAssessment, Optional[str]]:
        """Evaluates time-windowed exclusions (e.g. stroke within 12 months, therapy within 4 weeks)."""
        num = int(match.group("num"))
        unit = match.group("unit").lower()

        # Convert window to days
        if "day" in unit:
            window_days = num
        elif "week" in unit:
            window_days = num * 7
        elif "month" in unit:
            window_days = int(num * 30.4375)
        elif "year" in unit:
            window_days = num * 365
        else:
            window_days = num * 30

        text_lower = criterion_text.lower()

        # Case A: Systemic anticancer therapy / chemotherapy / investigational drug
        is_therapy_criterion = any(t in text_lower for t in ("anticancer", "chemotherapy", "systemic therapy", "investigational drug", "treatment"))
        if is_therapy_criterion:
            th = patient_profile.treatment_history
            if not th:
                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.UNKNOWN,
                        criterion_text=criterion_text,
                        patient_value=None,
                        exclusion_requirement=f"No systemic therapy within {num} {unit}",
                        rationale="Treatment history is missing from patient profile.",
                        evidence=None,
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    "treatment_history",
                )

            # If recent therapy is explicitly False
            if th.recent_systemic_anticancer_therapy is False:
                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.CLEAR,
                        criterion_text=criterion_text,
                        patient_value="recent_systemic_anticancer_therapy = False",
                        exclusion_requirement=f"No systemic therapy within {num} {unit}",
                        rationale="Patient is documented as not having received recent systemic anticancer therapy.",
                        evidence={"treatment_history.recent_systemic_anticancer_therapy": False},
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    None,
                )

            # If date is available
            date_str = th.last_treatment_date
            if not date_str:
                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.UNKNOWN,
                        criterion_text=criterion_text,
                        patient_value=f"recent_systemic_anticancer_therapy = {th.recent_systemic_anticancer_therapy}",
                        exclusion_requirement=f"No systemic therapy within {num} {unit}",
                        rationale="Last treatment date is missing; cannot determine temporal proximity.",
                        evidence=None,
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    "treatment_history.last_treatment_date",
                )

            try:
                event_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                diff_days = (reference_date - event_dt).days
                if diff_days < 0:
                    diff_days = 0  # future or same-day
            except Exception:
                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.UNKNOWN,
                        criterion_text=criterion_text,
                        patient_value=date_str,
                        exclusion_requirement=f"No systemic therapy within {num} {unit}",
                        rationale=f"Unable to parse last treatment date: '{date_str}'.",
                        evidence=None,
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    "treatment_history.last_treatment_date",
                )

            if diff_days <= window_days:
                return (
                    ExclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=ExclusionStatus.TRIGGERED,
                        criterion_text=criterion_text,
                        patient_value=f"Last treatment on {date_str} ({diff_days} days prior to ref {reference_date})",
                        exclusion_requirement=f"No systemic therapy within {num} {unit} ({window_days} days)",
                        rationale=f"Last systemic therapy was {diff_days} days prior, which is within the {window_days}-day exclusion window.",
                        evidence={"treatment_history.last_treatment_date": date_str, "reference_date": str(reference_date)},
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    None,
                )

            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.CLEAR,
                    criterion_text=criterion_text,
                    patient_value=f"Last treatment on {date_str} ({diff_days} days prior to ref {reference_date})",
                    exclusion_requirement=f"No systemic therapy within {num} {unit} ({window_days} days)",
                    rationale=f"Last systemic therapy was {diff_days} days prior, safely exceeding the {window_days}-day exclusion window.",
                    evidence={"treatment_history.last_treatment_date": date_str, "reference_date": str(reference_date)},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        # Case B: Condition event (e.g. stroke or MI within N months)
        conditions = patient_profile.conditions or []
        target_cond = None
        cond_event_date = None

        for cond in conditions:
            c_name = cond.name.lower()
            if any(term in c_name for term in ("stroke", "tia", "myocardial infarction", "heart attack", "mi")):
                target_cond = cond
                # Check for embedded date string in source_provenance or name
                text_to_search = f"{cond.name} {cond.source_provenance or ''} {cond.status or ''}"
                date_match = self._RE_DATE.search(text_to_search)
                if date_match:
                    try:
                        cond_event_date = datetime.strptime(date_match.group("date"), "%Y-%m-%d").date()
                    except Exception:
                        pass
                break

        if not target_cond:
            # Condition is not documented at all -> UNKNOWN!
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    exclusion_requirement=criterion_text,
                    rationale="Condition is not documented in clinical record. Absence cannot be assumed as CLEAR.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "conditions.temporal_event",
            )

        if not cond_event_date:
            # Condition is documented, but event date is missing -> UNKNOWN!
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=f"{target_cond.name} (undated)",
                    exclusion_requirement=f"Event outside {num} {unit}",
                    rationale=f"Patient has documented diagnosis of '{target_cond.name}', but event date is missing. Cannot calculate proximity to reference date.",
                    evidence={"conditions": target_cond.name},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "conditions.event_date",
            )

        diff_days = (reference_date - cond_event_date).days
        if diff_days <= window_days:
            return (
                ExclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=ExclusionStatus.TRIGGERED,
                    criterion_text=criterion_text,
                    patient_value=f"{target_cond.name} on {cond_event_date} ({diff_days} days prior to ref {reference_date})",
                    exclusion_requirement=f"Event outside {num} {unit} ({window_days} days)",
                    rationale=f"Documented event '{target_cond.name}' occurred {diff_days} days prior, which is within the {window_days}-day exclusion window.",
                    evidence={"conditions": target_cond.name, "date": str(cond_event_date), "reference_date": str(reference_date)},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        return (
            ExclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text=criterion_text,
                patient_value=f"{target_cond.name} on {cond_event_date} ({diff_days} days prior to ref {reference_date})",
                exclusion_requirement=f"Event outside {num} {unit} ({window_days} days)",
                rationale=f"Documented event '{target_cond.name}' occurred {diff_days} days prior, safely outside the {window_days}-day exclusion window.",
                evidence={"conditions": target_cond.name, "date": str(cond_event_date), "reference_date": str(reference_date)},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )


class ExclusionDetectionAgent:
    """Agent that performs criterion-by-criterion detection of exclusion requirements.
    
    Adheres strictly to:
    - Authoritative trial isolation (rejects cross-trial evidence with TrialIsolationError).
    - Criterion-type validation (rejects non-exclusion criteria with CriterionTypeError).
    - Deterministic threshold and operator evaluation (Python-based).
    - Preserves False and 0 numeric/boolean values.
    - Mandatory UNKNOWN outcome when patient information is missing (never assumes missing = CLEAR).
    - Traceable provenance linking to source documents and page numbers.
    """

    def __init__(
        self,
        comparator: Optional[ExclusionComparator] = None,
        llm_service: Optional[GeminiLLMService] = None,
    ) -> None:
        self.comparator = comparator or ExclusionComparator()
        self.llm_service = llm_service or GeminiLLMService()

    async def evaluate(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        retrieved_evidence: List[Union[RetrievedChunk, ProtocolChunk, Dict[str, Any]]],
        reference_date: Optional[Union[date, str]] = None,
    ) -> ExclusionAssessment:
        """Evaluates exclusion criteria for the selected trial against the patient profile.

        Args:
            trial_id: Authoritative clinical trial ID (e.g. 'SYN-ONC-001').
            patient_profile: Structured patient clinical profile.
            retrieved_evidence: List of protocol chunks or retrieved criteria.
            reference_date: Optional evaluation date for temporal calculations.

        Returns:
            ExclusionAssessment containing criterion-level and overall assessments.

        Raises:
            ValueError: If trial_id is empty or no evidence is provided.
            TrialIsolationError: If any evidence chunk belongs to a different trial.
            CriterionTypeError: If any evidence chunk is an inclusion criterion.
        """
        clean_trial_id = (trial_id or "").strip()
        if not clean_trial_id:
            raise ValueError("trial_id must not be empty.")

        if not retrieved_evidence:
            logger.warning("Empty retrieved evidence provided for trial %s", clean_trial_id)
            return ExclusionAssessment(
                trial_id=clean_trial_id,
                patient_profile_id=patient_profile.patient_profile_id,
                overall_status=ExclusionStatus.UNKNOWN,
                criteria=[],
                missing_information=[],
                warnings=["No exclusion criteria provided for evaluation."],
            )

        ref_dt: Optional[date] = None
        if reference_date:
            if isinstance(reference_date, str):
                try:
                    ref_dt = datetime.strptime(reference_date, "%Y-%m-%d").date()
                except Exception:
                    ref_dt = date(2026, 9, 14)
            elif isinstance(reference_date, date):
                ref_dt = reference_date

        criteria_assessments: List[ExclusionCriterionAssessment] = []
        missing_information_set: set[str] = set()
        warnings: List[str] = []

        for chunk in retrieved_evidence:
            # 1. Normalize chunk properties
            c_trial_id = getattr(chunk, "trial_id", None) or (chunk.get("trial_id") if isinstance(chunk, dict) else None)
            c_id = getattr(chunk, "criterion_id", None) or (chunk.get("criterion_id") if isinstance(chunk, dict) else None) or "EXC-UNKNOWN"
            c_type = getattr(chunk, "criterion_type", None) or (chunk.get("criterion_type") if isinstance(chunk, dict) else None) or ""
            c_text = getattr(chunk, "text", None) or (chunk.get("text") if isinstance(chunk, dict) else None) or ""
            c_page = getattr(chunk, "source_page", None) or (chunk.get("source_page") if isinstance(chunk, dict) else 1)
            c_doc = getattr(chunk, "source_document", None) or (chunk.get("source_document") if isinstance(chunk, dict) else "unknown_document")
            c_excerpt = getattr(chunk, "source_excerpt", None) or (chunk.get("source_excerpt") if isinstance(chunk, dict) else None)

            # 2. TRIAL ISOLATION CHECK
            # If evidence belongs to another trial: DO NOT evaluate it. Reject immediately.
            if c_trial_id != clean_trial_id:
                msg = (
                    f"Trial isolation violation: retrieved exclusion criterion '{c_id}' belongs to trial '{c_trial_id}', "
                    f"which does not match selected trial '{clean_trial_id}'."
                )
                logger.error(msg)
                raise TrialIsolationError(msg)

            # 3. CRITERION TYPE VALIDATION
            # Only evaluate criterion_type == exclusion. Reject inclusion or other types.
            if c_type.lower() != "exclusion":
                msg = (
                    f"Criterion type validation error: criterion '{c_id}' has type '{c_type}'. "
                    f"The Exclusion Detection Agent only accepts exclusion criteria."
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
                reference_date=ref_dt,
            )

            # 5. OPTIONAL GEMINI NARRATIVE INTERPRETATION
            # Only use Gemini if deterministic evaluation yielded UNKNOWN due to narrative complexity
            # (NOT due to missing patient data) AND Gemini is configured.
            if (
                assessment.status == ExclusionStatus.UNKNOWN
                and missing_field is None
                and self.llm_service.is_configured
            ):
                assessment = await self._try_narrative_interpretation(
                    assessment=assessment,
                    patient_profile=patient_profile,
                )

            if missing_field:
                missing_information_set.add(missing_field)

            criteria_assessments.append(assessment)

        # 6. OVERALL STATUS COMPUTATION
        # - If ANY exclusion criterion is TRIGGERED -> overall_status = TRIGGERED
        # - If no criterion is TRIGGERED but AT LEAST ONE is UNKNOWN -> overall_status = UNKNOWN
        # - Only if EVERY required exclusion criterion is CLEAR -> overall_status = CLEAR
        has_triggered = any(c.status == ExclusionStatus.TRIGGERED for c in criteria_assessments)
        has_unknown = any(c.status == ExclusionStatus.UNKNOWN for c in criteria_assessments)

        if has_triggered:
            overall_status = ExclusionStatus.TRIGGERED
        elif has_unknown:
            overall_status = ExclusionStatus.UNKNOWN
        else:
            overall_status = ExclusionStatus.CLEAR

        return ExclusionAssessment(
            trial_id=clean_trial_id,
            patient_profile_id=patient_profile.patient_profile_id,
            overall_status=overall_status,
            criteria=criteria_assessments,
            missing_information=sorted(list(missing_information_set)),
            warnings=warnings,
        )

    async def _try_narrative_interpretation(
        self,
        assessment: ExclusionCriterionAssessment,
        patient_profile: PatientProfile,
    ) -> ExclusionCriterionAssessment:
        """Invokes GeminiLLMService strictly for narrative exclusion interpretation."""
        prompt = (
            f"You are a clinical protocol reviewer assessing a patient against a single clinical trial EXCLUSION criterion.\n"
            f"Protocol Exclusion Requirement: \"{assessment.criterion_text}\"\n"
            f"Patient Profile Facts:\n{patient_profile.model_dump_json(indent=2)}\n\n"
            f"STRICT RULES:\n"
            f"1. Use ONLY the supplied patient facts. Do not assume or invent missing data.\n"
            f"2. If relevant patient information is not documented, status MUST be 'UNKNOWN'.\n"
            f"3. Return ONLY valid JSON with keys: 'status' ('TRIGGERED', 'CLEAR', or 'UNKNOWN'), "
            f"'patient_value' (extracted string/fact or null), 'exclusion_requirement' (string), "
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
                if raw_status in ("TRIGGERED", "CLEAR", "UNKNOWN"):
                    status = ExclusionStatus(raw_status)
                    return ExclusionCriterionAssessment(
                        criterion_id=assessment.criterion_id,
                        trial_id=assessment.trial_id,
                        status=status,
                        criterion_text=assessment.criterion_text,
                        patient_value=res.get("patient_value", assessment.patient_value),
                        exclusion_requirement=res.get("exclusion_requirement", assessment.exclusion_requirement),
                        rationale=res.get("rationale", assessment.rationale),
                        evidence=assessment.evidence,
                        source_page=assessment.source_page,
                        source_document=assessment.source_document,
                        source_excerpt=assessment.source_excerpt,
                    )
        except Exception as err:
            logger.warning("Gemini narrative interpretation fallback failed for exclusion: %s", err)

        return assessment
