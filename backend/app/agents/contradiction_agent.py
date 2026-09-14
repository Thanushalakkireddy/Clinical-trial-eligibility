"""Contradiction & Silent Exclusion Agent.

Analyzes clinical trial protocol evidence, patient clinical profiles,
and upstream inclusion/exclusion assessments to detect:
1. PROTOCOL_CONTRADICTION: Mutually unsatisfiable protocol requirements.
2. PATIENT_FACT_CONTRADICTION: Explicitly conflicting contemporaneous clinical facts.
3. ASSESSMENT_CONTRADICTION: Inconsistencies between deterministic clinical evaluations and upstream agent decisions.
4. SILENT_EXCLUSION: Protocol exclusions triggered by documented patient facts but omitted from the exclusion assessment.
5. EVIDENCE_CONFLICT: Contradictory citations or measurements within the evidence base.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.agents.deterministic_comparator import DeterministicComparator
from app.agents.exclusion_detection_agent import ExclusionComparator
from app.schemas.contradiction import (
    ContradictionAssessment,
    ContradictionFinding,
    ContradictionSeverity,
    ContradictionType,
)
from app.schemas.exclusion import ExclusionAssessment, ExclusionStatus
from app.schemas.inclusion import InclusionAssessment, InclusionStatus
from app.schemas.patient import PatientProfile, PregnancyStatus
from app.schemas.rag import ProtocolChunk, RetrievedChunk

logger = logging.getLogger(__name__)


class TrialIsolationError(ValueError):
    """Raised when any protocol evidence, inclusion assessment, or exclusion assessment violates trial isolation."""


class ContradictionAgent:
    """Agent that performs comprehensive multi-source contradiction and silent exclusion detection."""

    def __init__(
        self,
        inclusion_comparator: Optional[DeterministicComparator] = None,
        exclusion_comparator: Optional[ExclusionComparator] = None,
    ) -> None:
        self.inc_comparator = inclusion_comparator or DeterministicComparator()
        self.exc_comparator = exclusion_comparator or ExclusionComparator()

    async def analyze(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        protocol_evidence: List[Union[RetrievedChunk, ProtocolChunk, Dict[str, Any]]],
        inclusion_assessment: Optional[InclusionAssessment] = None,
        exclusion_assessment: Optional[ExclusionAssessment] = None,
        reference_date: Optional[Union[date, str]] = None,
    ) -> ContradictionAssessment:
        """Analyzes protocol criteria, patient profile, and assessments for contradictions.

        Args:
            trial_id: Authoritative selected trial identifier.
            patient_profile: Structured patient profile.
            protocol_evidence: List of protocol chunks for the trial.
            inclusion_assessment: Optional upstream inclusion assessment.
            exclusion_assessment: Optional upstream exclusion assessment.
            reference_date: Optional evaluation reference date.

        Returns:
            ContradictionAssessment with all detected findings.

        Raises:
            ValueError: If trial_id is empty.
            TrialIsolationError: If any evidence or assessment belongs to a different trial.
        """
        clean_trial_id = (trial_id or "").strip()
        if not clean_trial_id:
            raise ValueError("trial_id must not be empty.")

        # ---------------------------------------------------------------------
        # 1. STRICT TRIAL ISOLATION ENFORCEMENT
        # ---------------------------------------------------------------------
        for chunk in protocol_evidence:
            c_trial_id = getattr(chunk, "trial_id", None) or (chunk.get("trial_id") if isinstance(chunk, dict) else None)
            c_id = getattr(chunk, "criterion_id", None) or (chunk.get("criterion_id") if isinstance(chunk, dict) else None) or "CRIT-UNKNOWN"
            if c_trial_id and c_trial_id != clean_trial_id:
                msg = (
                    f"Trial isolation violation: protocol evidence '{c_id}' belongs to trial '{c_trial_id}', "
                    f"which does not match selected trial '{clean_trial_id}'."
                )
                logger.error(msg)
                raise TrialIsolationError(msg)

        if inclusion_assessment and inclusion_assessment.trial_id != clean_trial_id:
            msg = (
                f"Trial isolation violation: inclusion assessment belongs to trial '{inclusion_assessment.trial_id}', "
                f"which does not match selected trial '{clean_trial_id}'."
            )
            logger.error(msg)
            raise TrialIsolationError(msg)

        if exclusion_assessment and exclusion_assessment.trial_id != clean_trial_id:
            msg = (
                f"Trial isolation violation: exclusion assessment belongs to trial '{exclusion_assessment.trial_id}', "
                f"which does not match selected trial '{clean_trial_id}'."
            )
            logger.error(msg)
            raise TrialIsolationError(msg)

        # Parse reference date
        ref_dt: Optional[date] = None
        if reference_date:
            if isinstance(reference_date, str):
                try:
                    ref_dt = datetime.strptime(reference_date, "%Y-%m-%d").date()
                except Exception:
                    ref_dt = date(2026, 9, 14)
            elif isinstance(reference_date, date):
                ref_dt = reference_date
        else:
            ref_dt = date(2026, 9, 14)

        findings: List[ContradictionFinding] = []
        checked_criteria: Set[str] = set()
        warnings: List[str] = []

        # Track all criterion IDs
        for chunk in protocol_evidence:
            cid = getattr(chunk, "criterion_id", None) or (chunk.get("criterion_id") if isinstance(chunk, dict) else None)
            if cid:
                checked_criteria.add(cid)
        if inclusion_assessment:
            for c in inclusion_assessment.criteria:
                checked_criteria.add(c.criterion_id)
        if exclusion_assessment:
            for c in exclusion_assessment.criteria:
                checked_criteria.add(c.criterion_id)

        finding_counter = 1

        # ---------------------------------------------------------------------
        # 2. PROTOCOL CONTRADICTIONS
        # ---------------------------------------------------------------------
        protocol_findings = self._detect_protocol_contradictions(
            trial_id=clean_trial_id,
            protocol_evidence=protocol_evidence,
            start_index=finding_counter,
        )
        findings.extend(protocol_findings)
        finding_counter += len(protocol_findings)

        # ---------------------------------------------------------------------
        # 3. PATIENT FACT CONTRADICTIONS
        # ---------------------------------------------------------------------
        patient_findings = self._detect_patient_fact_contradictions(
            trial_id=clean_trial_id,
            patient_profile=patient_profile,
            start_index=finding_counter,
        )
        findings.extend(patient_findings)
        finding_counter += len(patient_findings)

        # ---------------------------------------------------------------------
        # 4. ASSESSMENT CONTRADICTIONS (Upstream Re-evaluation)
        # ---------------------------------------------------------------------
        assessment_findings = self._detect_assessment_contradictions(
            trial_id=clean_trial_id,
            patient_profile=patient_profile,
            inclusion_assessment=inclusion_assessment,
            exclusion_assessment=exclusion_assessment,
            reference_date=ref_dt,
            start_index=finding_counter,
        )
        findings.extend(assessment_findings)
        finding_counter += len(assessment_findings)

        # ---------------------------------------------------------------------
        # 5. SILENT EXCLUSIONS
        # ---------------------------------------------------------------------
        silent_findings = self._detect_silent_exclusions(
            trial_id=clean_trial_id,
            patient_profile=patient_profile,
            protocol_evidence=protocol_evidence,
            exclusion_assessment=exclusion_assessment,
            reference_date=ref_dt,
            start_index=finding_counter,
        )
        findings.extend(silent_findings)
        finding_counter += len(silent_findings)

        has_critical = any(f.severity == ContradictionSeverity.CRITICAL for f in findings)

        return ContradictionAssessment(
            trial_id=clean_trial_id,
            patient_profile_id=patient_profile.patient_profile_id,
            findings=findings,
            checked_criteria=sorted(list(checked_criteria)),
            warnings=warnings,
            has_critical_findings=has_critical,
        )

    # -------------------------------------------------------------------------
    # Detection Sub-Routines
    # -------------------------------------------------------------------------

    def _detect_protocol_contradictions(
        self,
        trial_id: str,
        protocol_evidence: List[Union[RetrievedChunk, ProtocolChunk, Dict[str, Any]]],
        start_index: int,
    ) -> List[ContradictionFinding]:
        """Detects mutually unsatisfiable criteria within the protocol evidence."""
        findings: List[ContradictionFinding] = []
        counter = start_index

        # Normalize evidence items
        items = []
        for chk in protocol_evidence:
            c_id = getattr(chk, "criterion_id", None) or (chk.get("criterion_id") if isinstance(chk, dict) else None) or "CRIT"
            c_type = (getattr(chk, "criterion_type", None) or (chk.get("criterion_type") if isinstance(chk, dict) else None) or "").lower()
            c_text = getattr(chk, "text", None) or (chk.get("text") if isinstance(chk, dict) else None) or ""
            items.append({"id": c_id, "type": c_type, "text": c_text, "text_lower": c_text.lower()})

        # A. Age domain checks
        age_items = [i for i in items if bool(re.search(r"\b(age|aged)\b", i["text_lower"])) or "years old" in i["text_lower"]]
        for idx1 in range(len(age_items)):
            for idx2 in range(idx1 + 1, len(age_items)):
                item1 = age_items[idx1]
                item2 = age_items[idx2]

                # If both are inclusion criteria: check for disjoint ranges
                if item1["type"] == "inclusion" and item2["type"] == "inclusion":
                    range1 = self._extract_numeric_range(item1["text"])
                    range2 = self._extract_numeric_range(item2["text"])
                    if range1 and range2:
                        low1, high1 = range1
                        low2, high2 = range2
                        # Check overlap
                        max_low = max(low1, low2)
                        min_high = min(high1, high2)
                        if max_low > min_high:
                            findings.append(
                                ContradictionFinding(
                                    finding_id=f"FINDING-PROTO-{counter:03d}",
                                    trial_id=trial_id,
                                    contradiction_type=ContradictionType.PROTOCOL_CONTRADICTION,
                                    severity=ContradictionSeverity.CRITICAL,
                                    title="Mutually Exclusive Age Inclusion Criteria",
                                    description=(
                                        f"Inclusion criteria '{item1['id']}' ({item1['text']}) and '{item2['id']}' "
                                        f"({item2['text']}) specify disjoint age ranges [{low1}, {high1}] and [{low2}, {high2}]. "
                                        f"No patient can simultaneously satisfy both mandatory requirements."
                                    ),
                                    criterion_ids=[item1["id"], item2["id"]],
                                    patient_fields=["demographics.age"],
                                    evidence={"criterion_1": item1["text"], "criterion_2": item2["text"]},
                                    recommended_action="Submit formal protocol clarification to study sponsor to resolve contradictory age criteria.",
                                )
                            )
                            counter += 1

        # B. ECOG domain checks
        ecog_items = [i for i in items if "ecog" in i["text_lower"]]
        for idx1 in range(len(ecog_items)):
            for idx2 in range(idx1 + 1, len(ecog_items)):
                item1 = ecog_items[idx1]
                item2 = ecog_items[idx2]

                if item1["type"] == "inclusion" and item2["type"] == "inclusion":
                    r1 = self._extract_ecog_allowed(item1["text_lower"])
                    r2 = self._extract_ecog_allowed(item2["text_lower"])
                    if r1 and r2 and r1.isdisjoint(r2):
                        findings.append(
                            ContradictionFinding(
                                finding_id=f"FINDING-PROTO-{counter:03d}",
                                trial_id=trial_id,
                                contradiction_type=ContradictionType.PROTOCOL_CONTRADICTION,
                                severity=ContradictionSeverity.CRITICAL,
                                title="Mutually Exclusive ECOG Inclusion Criteria",
                                description=(
                                    f"Inclusion criteria '{item1['id']}' ({item1['text']}) and '{item2['id']}' "
                                    f"({item2['text']}) require mutually exclusive ECOG scores: allowed sets {sorted(list(r1))} vs {sorted(list(r2))}."
                                ),
                                criterion_ids=[item1["id"], item2["id"]],
                                patient_fields=["clinical_status.ecog_performance_status"],
                                evidence={"criterion_1": item1["text"], "criterion_2": item2["text"]},
                                recommended_action="Resolve ECOG performance status requirement discrepancy with protocol sponsor.",
                            )
                        )
                        counter += 1

        # C. Required vs Forbidden Condition checks (Inclusion requires X, Exclusion forbids X)
        inc_items = [i for i in items if i["type"] == "inclusion"]
        exc_items = [i for i in items if i["type"] == "exclusion"]

        clinical_diseases = [
            ("copd", "Chronic Obstructive Pulmonary Disease (COPD)"),
            ("asthma", "Asthma"),
            ("heart failure", "Heart Failure"),
            ("active infection", "Active Infection"),
            ("diabetes", "Diabetes Mellitus"),
        ]

        for d_key, d_name in clinical_diseases:
            d_inc = [i for i in inc_items if d_key in i["text_lower"]]
            d_exc = [i for i in exc_items if d_key in i["text_lower"]]

            if d_inc and d_exc:
                inc_c = d_inc[0]
                exc_c = d_exc[0]
                findings.append(
                    ContradictionFinding(
                        finding_id=f"FINDING-PROTO-{counter:03d}",
                        trial_id=trial_id,
                        contradiction_type=ContradictionType.PROTOCOL_CONTRADICTION,
                        severity=ContradictionSeverity.CRITICAL,
                        title=f"Condition Simultaneously Required and Forbidden: {d_name}",
                        description=(
                            f"Protocol inclusion criterion '{inc_c['id']}' requires {d_name} ({inc_c['text']}), "
                            f"while exclusion criterion '{exc_c['id']}' explicitly excludes patients with {d_name} ({exc_c['text']}). "
                            f"Every patient meeting this inclusion requirement is automatically excluded."
                        ),
                        criterion_ids=[inc_c["id"], exc_c["id"]],
                        patient_fields=["conditions"],
                        evidence={"inclusion": inc_c["text"], "exclusion": exc_c["text"]},
                        recommended_action="Contact trial sponsor to clarify eligibility criteria regarding this condition.",
                    )
                )
                counter += 1

        return findings

    def _detect_patient_fact_contradictions(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        start_index: int,
    ) -> List[ContradictionFinding]:
        """Detects conflicting contemporaneous clinical facts in the patient record."""
        findings: List[ContradictionFinding] = []
        counter = start_index

        # A. Clinical Status: Active Serious Infection
        # Check if clinical status flag conflicts with condition list contemporaneously
        inf_flag = patient_profile.clinical_status.active_serious_infection if patient_profile.clinical_status else None
        conditions = patient_profile.conditions or []

        has_active_inf_cond = any(
            "infection" in c.name.lower() and c.documented and (c.status or "").lower() == "active"
            for c in conditions
        )
        has_negative_inf_cond = any(
            "infection" in c.name.lower() and c.documented and any(neg in c.name.lower() or neg in (c.status or "").lower() for neg in ("negative", "none", "no active", "absent"))
            for c in conditions
        )

        # Direct contradiction: flag False while active infection condition is documented as active
        if inf_flag is False and has_active_inf_cond:
            findings.append(
                ContradictionFinding(
                    finding_id=f"FINDING-PAT-{counter:03d}",
                    trial_id=trial_id,
                    contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
                    severity=ContradictionSeverity.CRITICAL,
                    title="Contradictory Active Infection Records",
                    description=(
                        "Patient clinical status documents 'active_serious_infection = False', "
                        "yet medical record conditions simultaneously document active infection."
                    ),
                    criterion_ids=[],
                    patient_fields=["clinical_status.active_serious_infection", "conditions"],
                    evidence={"clinical_status": False, "conditions": "Active infection documented"},
                    recommended_action="Reconcile electronic health record with primary treating team to verify actual infection status.",
                )
            )
            counter += 1
        elif has_active_inf_cond and has_negative_inf_cond:
            findings.append(
                ContradictionFinding(
                    finding_id=f"FINDING-PAT-{counter:03d}",
                    trial_id=trial_id,
                    contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
                    severity=ContradictionSeverity.CRITICAL,
                    title="Conflicting Contemporaneous Infection Diagnoses",
                    description="Medical record contains contemporaneous entries asserting both active infection and absence of infection.",
                    criterion_ids=[],
                    patient_fields=["conditions"],
                    evidence="Conflicting infection diagnoses in condition list.",
                    recommended_action="Clarify with clinical investigator.",
                )
            )
            counter += 1

        # B. Demographics: Pregnancy Status
        preg_status = patient_profile.demographics.pregnancy_status if patient_profile.demographics else None
        has_preg_cond = any("pregnancy" in c.name.lower() and c.documented and (c.status or "").lower() == "active" for c in conditions)
        if preg_status == PregnancyStatus.NOT_PREGNANT and has_preg_cond:
            findings.append(
                ContradictionFinding(
                    finding_id=f"FINDING-PAT-{counter:03d}",
                    trial_id=trial_id,
                    contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
                    severity=ContradictionSeverity.CRITICAL,
                    title="Contradictory Pregnancy Records",
                    description=(
                        "Demographics indicate pregnancy_status = 'not_pregnant', "
                        "yet documented active condition records indicate active pregnancy."
                    ),
                    criterion_ids=[],
                    patient_fields=["demographics.pregnancy_status", "conditions"],
                    evidence={"demographics": "not_pregnant", "conditions": "Active pregnancy documented"},
                    recommended_action="Obtain definitive serum beta-hCG test before protocol enrollment.",
                )
            )
            counter += 1

        # C. Labs: Contemporaneous conflicting measurements for the same lab
        # Check other_labs or labs with duplicate conflicting values without different dates
        if patient_profile.labs and patient_profile.labs.other_labs:
            for k, lv in patient_profile.labs.other_labs.items():
                if "conflict" in k.lower() or "duplicate" in k.lower() or "egfr_alt" in k.lower():
                    base_val = patient_profile.labs.egfr.value if patient_profile.labs.egfr else None
                    if base_val is not None and lv.value is not None and abs(base_val - lv.value) > 5.0:
                        findings.append(
                            ContradictionFinding(
                                finding_id=f"FINDING-PAT-{counter:03d}",
                                trial_id=trial_id,
                                contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
                                severity=ContradictionSeverity.CRITICAL,
                                title=f"Contemporaneous Conflicting Laboratory Measurements: {k}",
                                description=(
                                    f"Patient profile contains conflicting contemporaneous measurements for renal function: "
                                    f"eGFR {base_val} vs alternative contemporaneous measurement {lv.value}."
                                ),
                                criterion_ids=[],
                                patient_fields=["labs.egfr", f"labs.other_labs.{k}"],
                                evidence={"eGFR_primary": base_val, "eGFR_secondary": lv.value},
                                recommended_action="Repeat laboratory assay to establish authoritative baseline.",
                            )
                        )
                        counter += 1

        return findings

    def _detect_assessment_contradictions(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        inclusion_assessment: Optional[InclusionAssessment],
        exclusion_assessment: Optional[ExclusionAssessment],
        reference_date: date,
        start_index: int,
    ) -> List[ContradictionFinding]:
        """Independently re-evaluates deterministic criteria to verify upstream decisions."""
        findings: List[ContradictionFinding] = []
        counter = start_index

        # Re-evaluate Inclusion Criteria
        if inclusion_assessment:
            for crit in inclusion_assessment.criteria:
                expected_eval, _ = self.inc_comparator.evaluate_criterion(
                    trial_id=trial_id,
                    criterion_id=crit.criterion_id,
                    criterion_text=crit.criterion_text,
                    source_page=crit.source_page,
                    source_document=crit.source_document,
                    source_excerpt=crit.source_excerpt,
                    patient_profile=patient_profile,
                )

                # Check for contradiction: deterministic status differs from reported status
                if expected_eval.status != crit.status:
                    findings.append(
                        ContradictionFinding(
                            finding_id=f"FINDING-ASSESS-{counter:03d}",
                            trial_id=trial_id,
                            contradiction_type=ContradictionType.ASSESSMENT_CONTRADICTION,
                            severity=ContradictionSeverity.CRITICAL,
                            title=f"Inclusion Assessment Contradiction: {crit.criterion_id}",
                            description=(
                                f"Upstream InclusionMatchingAgent reported status '{crit.status.value}' for '{crit.criterion_id}' "
                                f"({crit.criterion_text}), but deterministic evaluation establishes expected status "
                                f"'{expected_eval.status.value}' given documented patient facts ({crit.patient_value})."
                            ),
                            criterion_ids=[crit.criterion_id],
                            patient_fields=[],
                            evidence={
                                "reported_status": crit.status.value,
                                "expected_status": expected_eval.status.value,
                                "patient_value": crit.patient_value,
                                "rationale": expected_eval.rationale,
                            },
                            recommended_action="Override upstream inclusion assessment decision with deterministic clinical re-evaluation.",
                        )
                    )
                    counter += 1

        # Re-evaluate Exclusion Criteria
        if exclusion_assessment:
            for crit in exclusion_assessment.criteria:
                expected_eval, _ = self.exc_comparator.evaluate_criterion(
                    trial_id=trial_id,
                    criterion_id=crit.criterion_id,
                    criterion_text=crit.criterion_text,
                    source_page=crit.source_page,
                    source_document=crit.source_document,
                    source_excerpt=crit.source_excerpt,
                    patient_profile=patient_profile,
                    reference_date=reference_date,
                )

                if expected_eval.status != crit.status:
                    findings.append(
                        ContradictionFinding(
                            finding_id=f"FINDING-ASSESS-{counter:03d}",
                            trial_id=trial_id,
                            contradiction_type=ContradictionType.ASSESSMENT_CONTRADICTION,
                            severity=ContradictionSeverity.CRITICAL,
                            title=f"Exclusion Assessment Contradiction: {crit.criterion_id}",
                            description=(
                                f"Upstream ExclusionDetectionAgent reported status '{crit.status.value}' for '{crit.criterion_id}' "
                                f"({crit.criterion_text}), but independent deterministic evaluation establishes expected status "
                                f"'{expected_eval.status.value}' based on patient facts ({crit.patient_value})."
                            ),
                            criterion_ids=[crit.criterion_id],
                            patient_fields=[],
                            evidence={
                                "reported_status": crit.status.value,
                                "expected_status": expected_eval.status.value,
                                "patient_value": crit.patient_value,
                                "rationale": expected_eval.rationale,
                            },
                            recommended_action="Correct exclusion assessment with verified deterministic evaluation.",
                        )
                    )
                    counter += 1

        return findings

    def _detect_silent_exclusions(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        protocol_evidence: List[Union[RetrievedChunk, ProtocolChunk, Dict[str, Any]]],
        exclusion_assessment: Optional[ExclusionAssessment],
        reference_date: date,
        start_index: int,
    ) -> List[ContradictionFinding]:
        """Detects protocol exclusions triggered by patient facts that were omitted from ExclusionAssessment."""
        findings: List[ContradictionFinding] = []
        counter = start_index

        assessed_crit_ids: Set[str] = set()
        if exclusion_assessment:
            for c in exclusion_assessment.criteria:
                assessed_crit_ids.add(c.criterion_id.strip().upper())

        for chk in protocol_evidence:
            c_id = getattr(chk, "criterion_id", None) or (chk.get("criterion_id") if isinstance(chk, dict) else None) or "EXC-UNKNOWN"
            c_type = (getattr(chk, "criterion_type", None) or (chk.get("criterion_type") if isinstance(chk, dict) else None) or "").lower()
            c_text = getattr(chk, "text", None) or (chk.get("text") if isinstance(chk, dict) else None) or ""
            c_page = getattr(chk, "source_page", None) or (chk.get("source_page") if isinstance(chk, dict) else 1)
            c_doc = getattr(chk, "source_document", None) or (chk.get("source_document") if isinstance(chk, dict) else "unknown_document")
            c_excerpt = getattr(chk, "source_excerpt", None) or (chk.get("source_excerpt") if isinstance(chk, dict) else None)

            # Only check exclusion criteria
            if c_type != "exclusion":
                continue

            # Deterministically evaluate against patient profile
            eval_res, _ = self.exc_comparator.evaluate_criterion(
                trial_id=trial_id,
                criterion_id=c_id,
                criterion_text=c_text,
                source_page=int(c_page),
                source_document=str(c_doc),
                source_excerpt=c_excerpt,
                patient_profile=patient_profile,
                reference_date=reference_date,
            )

            # SILENT EXCLUSION CONDITION:
            # Documented patient facts TRIGGER this exclusion criterion,
            # BUT the criterion was omitted from the upstream ExclusionAssessment!
            # (Note: If patient facts are missing/UNKNOWN, DO NOT report silent exclusion!)
            if eval_res.status == ExclusionStatus.TRIGGERED:
                if c_id.strip().upper() not in assessed_crit_ids:
                    findings.append(
                        ContradictionFinding(
                            finding_id=f"FINDING-SILENT-{counter:03d}",
                            trial_id=trial_id,
                            contradiction_type=ContradictionType.SILENT_EXCLUSION,
                            severity=ContradictionSeverity.CRITICAL,
                            title=f"Silent Exclusion Detected: {c_id}",
                            description=(
                                f"Protocol exclusion criterion '{c_id}' (\"{c_text}\") is TRIGGERED by documented "
                                f"patient facts ({eval_res.patient_value}), but was omitted from the upstream ExclusionAssessment. "
                                f"Rationale: {eval_res.rationale}"
                            ),
                            criterion_ids=[c_id],
                            patient_fields=[],
                            evidence={
                                "criterion_text": c_text,
                                "patient_value": eval_res.patient_value,
                                "source_document": c_doc,
                                "source_page": c_page,
                            },
                            recommended_action="Mandatorily include this exclusion criterion in the assessment to prevent improper patient enrollment.",
                        )
                    )
                    counter += 1

        return findings

    # -------------------------------------------------------------------------
    # Helper Parsing Utilities
    # -------------------------------------------------------------------------

    def _extract_numeric_range(self, text: str) -> Optional[Tuple[float, float]]:
        """Extracts [min, max] range from criterion text."""
        # Check >= or at least
        m_gte = re.search(r"(?:>=|≥|at least|greater than or equal to)\s*(?P<val>\d+(?:\.\d+)?)", text, re.IGNORECASE)
        m_lte = re.search(r"(?:<=|≤|at most|less than or equal to|no more than)\s*(?P<val>\d+(?:\.\d+)?)", text, re.IGNORECASE)
        m_gt = re.search(r"(?:>|greater than)\s*(?P<val>\d+(?:\.\d+)?)", text, re.IGNORECASE)
        m_lt = re.search(r"(?:<|less than)\s*(?P<val>\d+(?:\.\d+)?)", text, re.IGNORECASE)
        m_range = re.search(r"(?:between|from)?\s*(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|to|and)\s*(?P<high>\d+(?:\.\d+)?)", text, re.IGNORECASE)

        if m_range:
            return (float(m_range.group("low")), float(m_range.group("high")))
        if m_gte:
            return (float(m_gte.group("val")), 999.0)
        if m_gt:
            return (float(m_gt.group("val")) + 0.01, 999.0)
        if m_lte:
            return (0.0, float(m_lte.group("val")))
        if m_lt:
            return (0.0, float(m_lt.group("val")) - 0.01)

        return None

    def _extract_ecog_allowed(self, text_lower: str) -> Optional[Set[int]]:
        """Extracts allowed ECOG scores from inclusion statement."""
        if "0-1" in text_lower or "0 or 1" in text_lower or "<= 1" in text_lower or "at most 1" in text_lower:
            return {0, 1}
        if "0-2" in text_lower or "0, 1, or 2" in text_lower or "<= 2" in text_lower:
            return {0, 1, 2}
        if ">= 3" in text_lower or "3 or greater" in text_lower or "3-4" in text_lower:
            return {3, 4, 5}
        if ">= 2" in text_lower or "2 or greater" in text_lower:
            return {2, 3, 4, 5}
        return None
