"""Deterministic Clinical Comparison Layer.

Provides rule-based, deterministic evaluation of inclusion criteria against
structured patient profiles without arithmetic hallucinations or model inference.
Handles numerical bounds, ranges, categorical matches, boolean requirements,
and missing-field tracking with strict zero/false preservation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.inclusion import InclusionCriterionAssessment, InclusionStatus
from app.schemas.patient import PatientProfile, PregnancyStatus


class DeterministicComparator:
    """Evaluates clinical criteria deterministically against structured patient facts."""

    # Regex patterns for clinical threshold extraction
    _RE_RANGE = re.compile(
        r"(?:between\s+)?(?P<low>\d+(?:\.\d+)?)\s*(?:-|to|and)\s*(?P<high>\d+(?:\.\d+)?)(?:\s*%)?",
        re.IGNORECASE,
    )
    _RE_GTE = re.compile(
        r"(?:>=|≥|at\s+least|minimum(?:\s+of)?)\s*(?P<val>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _RE_GT = re.compile(
        r"(?:>|greater\s+than|exceeding)\s*(?P<val>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _RE_LTE = re.compile(
        r"(?:<=|≤|at\s+most|maximum(?:\s+of)?|no\s+more\s+than|up\s+to)\s*(?P<val>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _RE_LT = re.compile(
        r"(?:<|less\s+than)\s*(?P<val>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    def evaluate_criterion(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        """Evaluate an inclusion criterion deterministically.

        Returns:
            Tuple of (InclusionCriterionAssessment, missing_field_name_or_None)
        """
        text_lower = criterion_text.lower()

        # 1. Age criteria
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

        # 2. ECOG Performance Status
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

        # 3. Renal / eGFR
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

        # 4. Hematology: ANC (Absolute Neutrophil Count)
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

        # 5. Hematology: Platelets
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

        # 6. Hematology: Hemoglobin
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

        # 7. Hepatic: Bilirubin
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

        # 8. Hepatic: AST / ALT
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

        # 9. Pulmonary: FEV1/FVC ratio
        if "fev1/fvc" in text_lower:
            return self._evaluate_fev1_fvc(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 10. Pulmonary: FEV1 percentage
        if "fev1" in text_lower:
            return self._evaluate_fev1(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 11. Pulmonary: CAT score
        if "cat score" in text_lower or (bool(re.search(r"\bcat\b", text_lower)) and "score" in text_lower):
            return self._evaluate_cat_score(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 12. Pulmonary: Smoking pack-years
        if "pack-year" in text_lower or "pack year" in text_lower:
            return self._evaluate_pack_years(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 13. Clinical status: Active Serious Infection
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

        # 14. Clinical status: Uncontrolled Cardiac Disease
        if "cardiac disease" in text_lower or "cardiac" in text_lower and "uncontrolled" in text_lower:
            return self._evaluate_cardiac_status(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 15. Demographics: Pregnancy status
        if "pregnant" in text_lower or "pregnancy" in text_lower:
            return self._evaluate_pregnancy_status(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 16. Demographics: Breastfeeding status
        if "breastfeeding" in text_lower or "lactating" in text_lower or "nursing" in text_lower:
            return self._evaluate_breastfeeding_status(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 17. Blood pressure
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

        # 18. Documented Condition requirement (e.g. solid tumor, COPD, asthma, etc.)
        if any(w in text_lower for w in ["tumor", "cancer", "copd", "asthma", "disease", "diagnos"]):
            return self._evaluate_condition_match(
                trial_id=trial_id,
                criterion_id=criterion_id,
                criterion_text=criterion_text,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
                patient_profile=patient_profile,
            )

        # 19. Fallback: Cannot safely evaluate deterministically
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.UNKNOWN,
                criterion_text=criterion_text,
                patient_value=None,
                expected_requirement=criterion_text,
                rationale="Criterion requires narrative clinical evaluation or unstructured patient documentation.",
                evidence=None,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    # -------------------------------------------------------------------------
    # Numerical Comparison Helper
    # -------------------------------------------------------------------------

    def _compare_numerical(
        self,
        value: float,
        text: str,
        value_name: str,
    ) -> Tuple[InclusionStatus, str, str]:
        """Compares a numeric value against patterns extracted from text.

        Returns:
            Tuple of (InclusionStatus, expected_requirement, rationale)
        """
        # 1. Range check (e.g. 40-80 or 0-1)
        # Check range pattern: "40-80", "40 to 80", "between 40 and 80"
        m_range = self._RE_RANGE.search(text)
        if m_range:
            low = float(m_range.group("low"))
            high = float(m_range.group("high"))
            expected = f"{low} - {high}"
            if low <= value <= high:
                return (
                    InclusionStatus.PASS,
                    expected,
                    f"Patient {value_name} of {value} is within the required range [{low}, {high}].",
                )
            return (
                InclusionStatus.FAIL,
                expected,
                f"Patient {value_name} of {value} is outside the required range [{low}, {high}].",
            )

        # 2. Greater than or equal (>=)
        m_gte = self._RE_GTE.search(text)
        if m_gte:
            req = float(m_gte.group("val"))
            expected = f">= {req}"
            if value >= req:
                return (
                    InclusionStatus.PASS,
                    expected,
                    f"Patient {value_name} of {value} satisfies protocol requirement (>= {req}).",
                )
            return (
                InclusionStatus.FAIL,
                expected,
                f"Patient {value_name} of {value} does not meet protocol minimum (>= {req}).",
            )

        # 3. Strictly greater than (>)
        m_gt = self._RE_GT.search(text)
        if m_gt:
            req = float(m_gt.group("val"))
            expected = f"> {req}"
            if value > req:
                return (
                    InclusionStatus.PASS,
                    expected,
                    f"Patient {value_name} of {value} satisfies protocol requirement (> {req}).",
                )
            return (
                InclusionStatus.FAIL,
                expected,
                f"Patient {value_name} of {value} does not exceed protocol threshold (> {req}).",
            )

        # 4. Less than or equal (<=)
        m_lte = self._RE_LTE.search(text)
        if m_lte:
            req = float(m_lte.group("val"))
            expected = f"<= {req}"
            if value <= req:
                return (
                    InclusionStatus.PASS,
                    expected,
                    f"Patient {value_name} of {value} satisfies protocol requirement (<= {req}).",
                )
            return (
                InclusionStatus.FAIL,
                expected,
                f"Patient {value_name} of {value} exceeds protocol maximum (<= {req}).",
            )

        # 5. Strictly less than (<)
        m_lt = self._RE_LT.search(text)
        if m_lt:
            req = float(m_lt.group("val"))
            expected = f"< {req}"
            if value < req:
                return (
                    InclusionStatus.PASS,
                    expected,
                    f"Patient {value_name} of {value} satisfies protocol requirement (< {req}).",
                )
            return (
                InclusionStatus.FAIL,
                expected,
                f"Patient {value_name} of {value} is not less than protocol threshold (< {req}).",
            )

        # If no explicit comparison operator found, return UNKNOWN
        return (
            InclusionStatus.UNKNOWN,
            text,
            f"Could not deterministically extract numerical threshold from: '{text}'.",
        )

    # -------------------------------------------------------------------------
    # Evaluation Handlers
    # -------------------------------------------------------------------------

    def _evaluate_age(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        age = patient_profile.demographics.age if patient_profile.demographics else None
        if age is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented age",
                    rationale="Patient age is missing from medical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.age",
            )

        status, expected, rationale = self._compare_numerical(float(age), criterion_text, "age")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=age,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"demographics.age": age},
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        ecog = None
        if patient_profile.clinical_status:
            ecog = patient_profile.clinical_status.ecog_performance_status

        # Note: ecog == 0 is NOT missing!
        if ecog is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented ECOG performance status",
                    rationale="ECOG performance status is missing from patient clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.ecog_performance_status",
            )

        # Check for specific ECOG patterns like "0-1", "0, 1", "0 or 1", "<= 1", "<= 2"
        text_lower = criterion_text.lower()
        if any(p in text_lower for p in ["0-1", "0 to 1", "0 or 1", "0, 1", "0 - 1"]):
            expected = "0 - 1"
            if ecog in (0, 1):
                return (
                    InclusionCriterionAssessment(
                        criterion_id=criterion_id,
                        trial_id=trial_id,
                        status=InclusionStatus.PASS,
                        criterion_text=criterion_text,
                        patient_value=ecog,
                        expected_requirement=expected,
                        rationale=f"Patient ECOG score of {ecog} satisfies protocol requirement (0-1).",
                        evidence={"clinical_status.ecog_performance_status": ecog},
                        source_page=source_page,
                        source_document=source_document,
                        source_excerpt=source_excerpt,
                    ),
                    None,
                )
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.FAIL,
                    criterion_text=criterion_text,
                    patient_value=ecog,
                    expected_requirement=expected,
                    rationale=f"Patient ECOG score of {ecog} exceeds allowed range (0-1).",
                    evidence={"clinical_status.ecog_performance_status": ecog},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        # Numerical comparison fallback
        status, expected, rationale = self._compare_numerical(float(ecog), criterion_text, "ECOG")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=ecog,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"clinical_status.ecog_performance_status": ecog},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_egfr(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.egfr:
            val = patient_profile.labs.egfr.value

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented eGFR",
                    rationale="eGFR lab measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.egfr",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "eGFR")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.egfr": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.anc:
            val = patient_profile.labs.anc.value

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented ANC",
                    rationale="ANC (Absolute Neutrophil Count) is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.anc",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "ANC")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.anc": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.platelets:
            val = patient_profile.labs.platelets.value

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented Platelet count",
                    rationale="Platelet measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.platelets",
            )

        # Normalize threshold if text has "100,000" or "100k" and patient is stored as e.g. 150 (x10^9/L)
        clean_text = criterion_text.replace(",", "")
        p_val = float(val)
        # If text has 100000 and p_val is e.g. 150 (common unit: x10^9/L or 10^3/mcL), normalize
        if "100000" in clean_text and p_val < 1000:
            p_val = p_val * 1000.0

        status, expected, rationale = self._compare_numerical(p_val, clean_text, "platelet count")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.platelets": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.hemoglobin:
            val = patient_profile.labs.hemoglobin.value

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented Hemoglobin",
                    rationale="Hemoglobin measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.hemoglobin",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "hemoglobin")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.hemoglobin": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.bilirubin:
            val = patient_profile.labs.bilirubin.value

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented Bilirubin",
                    rationale="Bilirubin lab measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.bilirubin",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "bilirubin")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.bilirubin": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        text_lower = criterion_text.lower()
        # Evaluate AST or ALT as specified
        check_ast = "ast" in text_lower
        check_alt = "alt" in text_lower
        if not check_ast and not check_alt:
            check_ast = True
            check_alt = True

        val = None
        target_name = "AST/ALT"
        missing_name = "labs.ast_alt"
        if check_ast and patient_profile.labs and patient_profile.labs.ast:
            val = patient_profile.labs.ast.value
            target_name = "AST"
            missing_name = "labs.ast"
        elif check_alt and patient_profile.labs and patient_profile.labs.alt:
            val = patient_profile.labs.alt.value
            target_name = "ALT"
            missing_name = "labs.alt"

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement=f"Documented {target_name}",
                    rationale=f"{target_name} measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                missing_name,
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, target_name)
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={missing_name: val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_fev1_fvc(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.other_labs:
            for k in ["fev1_fvc", "fev1/fvc", "fev1_fvc_ratio"]:
                if k in patient_profile.labs.other_labs:
                    val = patient_profile.labs.other_labs[k].value
                    break

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="FEV1/FVC < 0.70",
                    rationale="FEV1/FVC post-bronchodilator ratio is missing from patient pulmonary records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.other_labs.fev1_fvc",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "FEV1/FVC")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.other_labs.fev1_fvc": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_fev1(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.other_labs:
            for k in ["fev1", "fev1_percent", "fev1_predicted"]:
                if k in patient_profile.labs.other_labs:
                    val = patient_profile.labs.other_labs[k].value
                    break

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented FEV1 (% predicted)",
                    rationale="FEV1 (% predicted) measurement is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.other_labs.fev1",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "FEV1")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.other_labs.fev1": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_cat_score(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.other_labs:
            for k in ["cat", "cat_score", "copd_assessment_test"]:
                if k in patient_profile.labs.other_labs:
                    val = patient_profile.labs.other_labs[k].value
                    break

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented CAT score",
                    rationale="CAT score is missing from patient clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.other_labs.cat_score",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "CAT score")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.other_labs.cat_score": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_pack_years(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.labs and patient_profile.labs.other_labs:
            for k in ["pack_years", "smoking_pack_years", "pack_year"]:
                if k in patient_profile.labs.other_labs:
                    val = patient_profile.labs.other_labs[k].value
                    break

        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented smoking pack-years",
                    rationale="Smoking pack-years history is missing from patient records.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "labs.other_labs.pack_years",
            )

        status, expected, rationale = self._compare_numerical(float(val), criterion_text, "smoking pack-years")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=val,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"labs.other_labs.pack_years": val},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.clinical_status:
            val = patient_profile.clinical_status.active_serious_infection

        # CRITICAL: False is NOT missing!
        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="active_serious_infection = false",
                    rationale="Active serious infection status is not documented in clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.active_serious_infection",
            )

        # Requirement is that active serious infection must be false/absent
        if val is False:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.PASS,
                    criterion_text=criterion_text,
                    patient_value=False,
                    expected_requirement="active_serious_infection = false",
                    rationale="Patient is documented to have no active serious infection (False).",
                    evidence={"clinical_status.active_serious_infection": False},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.FAIL,
                criterion_text=criterion_text,
                patient_value=True,
                expected_requirement="active_serious_infection = false",
                rationale="Patient has documented active serious infection (True).",
                evidence={"clinical_status.active_serious_infection": True},
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = None
        if patient_profile.clinical_status:
            val = patient_profile.clinical_status.uncontrolled_cardiac_disease

        # CRITICAL: False is NOT missing!
        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="uncontrolled_cardiac_disease = false",
                    rationale="Uncontrolled cardiac disease status is not documented in clinical record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "clinical_status.uncontrolled_cardiac_disease",
            )

        if val is False:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.PASS,
                    criterion_text=criterion_text,
                    patient_value=False,
                    expected_requirement="uncontrolled_cardiac_disease = false",
                    rationale="Patient is documented to have no uncontrolled cardiac disease (False).",
                    evidence={"clinical_status.uncontrolled_cardiac_disease": False},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.FAIL,
                criterion_text=criterion_text,
                patient_value=True,
                expected_requirement="uncontrolled_cardiac_disease = false",
                rationale="Patient has documented uncontrolled cardiac disease (True).",
                evidence={"clinical_status.uncontrolled_cardiac_disease": True},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_pregnancy_status(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = patient_profile.demographics.pregnancy_status if patient_profile.demographics else None
        if val is None or val == PregnancyStatus.UNKNOWN:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="pregnancy_status = not_pregnant",
                    rationale="Pregnancy status is not documented in patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.pregnancy_status",
            )

        if val == PregnancyStatus.NOT_PREGNANT:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.PASS,
                    criterion_text=criterion_text,
                    patient_value=val.value,
                    expected_requirement="not_pregnant",
                    rationale="Patient is confirmed not pregnant.",
                    evidence={"demographics.pregnancy_status": val.value},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.FAIL,
                criterion_text=criterion_text,
                patient_value=val.value,
                expected_requirement="not_pregnant",
                rationale="Patient has documented pregnancy (pregnant).",
                evidence={"demographics.pregnancy_status": val.value},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_breastfeeding_status(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        val = patient_profile.demographics.breastfeeding_status if patient_profile.demographics else None
        if val is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="breastfeeding_status = false",
                    rationale="Breastfeeding status is not documented in patient record.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "demographics.breastfeeding_status",
            )

        if val is False:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.PASS,
                    criterion_text=criterion_text,
                    patient_value=False,
                    expected_requirement="breastfeeding_status = false",
                    rationale="Patient is documented as not breastfeeding.",
                    evidence={"demographics.breastfeeding_status": False},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.FAIL,
                criterion_text=criterion_text,
                patient_value=True,
                expected_requirement="breastfeeding_status = false",
                rationale="Patient is actively breastfeeding.",
                evidence={"demographics.breastfeeding_status": True},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
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
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        bp = patient_profile.vital_signs.blood_pressure if patient_profile.vital_signs else None
        if bp is None or bp.systolic is None:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.UNKNOWN,
                    criterion_text=criterion_text,
                    patient_value=None,
                    expected_requirement="Documented Blood Pressure",
                    rationale="Blood pressure measurement is missing from vital signs.",
                    evidence=None,
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                "vital_signs.blood_pressure",
            )

        patient_bp_str = f"{bp.systolic}/{bp.diastolic} {bp.unit}" if bp.diastolic is not None else f"{bp.systolic} {bp.unit}"
        status, expected, rationale = self._compare_numerical(float(bp.systolic), criterion_text, "systolic BP")
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=status,
                criterion_text=criterion_text,
                patient_value=patient_bp_str,
                expected_requirement=expected,
                rationale=rationale,
                evidence={"vital_signs.blood_pressure": patient_bp_str},
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            None,
        )

    def _evaluate_condition_match(
        self,
        trial_id: str,
        criterion_id: str,
        criterion_text: str,
        source_page: int,
        source_document: str,
        source_excerpt: Optional[str],
        patient_profile: PatientProfile,
    ) -> Tuple[InclusionCriterionAssessment, Optional[str]]:
        """Evaluates documented medical conditions without inferring undocumented diagnoses."""
        text_lower = criterion_text.lower()
        patient_conditions = patient_profile.conditions or []

        # Target condition keywords
        target_condition = ""
        if "solid tumor" in text_lower or "advanced solid tumor" in text_lower:
            target_condition = "solid tumor"
        elif "copd" in text_lower or "chronic obstructive pulmonary" in text_lower:
            target_condition = "COPD"
        elif "asthma" in text_lower:
            target_condition = "asthma"
        elif "lung cancer" in text_lower or "nsclc" in text_lower:
            target_condition = "lung cancer"
        elif "breast cancer" in text_lower:
            target_condition = "breast cancer"
        else:
            target_condition = criterion_text

        # If conditions list is empty or target condition not found in documented conditions:
        # NO MEDICAL INFERENCE: Missing condition documentation means UNKNOWN!
        matching_condition = None
        for cond in patient_conditions:
            if not cond.documented:
                continue
            cond_lower = cond.name.lower()
            if target_condition.lower() in cond_lower or any(
                term in cond_lower for term in target_condition.lower().split() if len(term) > 3
            ):
                matching_condition = cond
                break

        if matching_condition:
            return (
                InclusionCriterionAssessment(
                    criterion_id=criterion_id,
                    trial_id=trial_id,
                    status=InclusionStatus.PASS,
                    criterion_text=criterion_text,
                    patient_value=f"{matching_condition.name} (status: {matching_condition.status})",
                    expected_requirement=f"Documented {target_condition}",
                    rationale=f"Patient has documented diagnosis of '{matching_condition.name}' matching protocol requirement.",
                    evidence={"conditions": matching_condition.name},
                    source_page=source_page,
                    source_document=source_document,
                    source_excerpt=source_excerpt,
                ),
                None,
            )

        # If not documented: UNKNOWN (do not assume absence means patient is free of condition or definitively fails)
        return (
            InclusionCriterionAssessment(
                criterion_id=criterion_id,
                trial_id=trial_id,
                status=InclusionStatus.UNKNOWN,
                criterion_text=criterion_text,
                patient_value=None,
                expected_requirement=f"Documented {target_condition}",
                rationale=f"Required diagnosis of '{target_condition}' is not documented in patient conditions record. Absence of documentation cannot be inferred as negative.",
                evidence=None,
                source_page=source_page,
                source_document=source_document,
                source_excerpt=source_excerpt,
            ),
            f"conditions.{target_condition}",
        )
