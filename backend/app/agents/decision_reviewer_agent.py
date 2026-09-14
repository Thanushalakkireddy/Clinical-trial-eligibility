"""Deterministic Decision / Reviewer Agent for Clinical Trial Eligibility.

This agent evaluates upstream clinical assessments (Inclusion, Exclusion, Contradiction,
and Protocol Evidence) to produce the final authoritative trial eligibility classification:
- ELIGIBLE
- NOT_ELIGIBLE
- MORE_INFORMATION_REQUIRED

CRITICAL SAFETY & DETERMINISM DIRECTIVES:
1. The final classification is computed STRICTLY by deterministic Python decision rules.
   Gemini/LLMs MUST NOT determine or override the final eligibility classification.
2. Trial isolation is authoritative. Cross-trial assessments are rejected immediately.
3. Priority order is mathematically enforced:
   NOT_ELIGIBLE > MORE_INFORMATION_REQUIRED > ELIGIBLE
4. Clinical Decision Support Disclaimer:
   This output provides clinical trial matching support and is not an independent medical
   diagnosis, prescription, or clinical management decision.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas.contradiction import (
    ContradictionAssessment,
    ContradictionFinding,
    ContradictionSeverity,
    ContradictionType,
)
from app.schemas.decision import (
    DecisionAssessment,
    DecisionEvidence,
    DecisionStatus,
)
from app.schemas.exclusion import ExclusionAssessment, ExclusionStatus
from app.schemas.inclusion import InclusionAssessment, InclusionStatus
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk

logger = logging.getLogger(__name__)


class TrialIsolationError(ValueError):
    """Raised when an assessment or evidence belongs to a different trial."""
    pass


class DecisionReviewerAgent:
    """Conservative, deterministic decision and reviewer agent."""

    CLINICAL_DISCLAIMER = (
        "Clinical decision support output for trial matching only. "
        "Not an independent medical diagnosis, treatment recommendation, or clinical management decision."
    )

    def evaluate(
        self,
        trial_id: str,
        patient_profile: PatientProfile,
        inclusion_assessment: InclusionAssessment,
        exclusion_assessment: ExclusionAssessment,
        contradiction_assessment: Optional[ContradictionAssessment] = None,
        protocol_evidence: Optional[List[RetrievedChunk]] = None,
    ) -> DecisionAssessment:
        """Executes deterministic eligibility decision logic with full evidence traceability.

        Args:
            trial_id: The authoritative selected clinical trial ID.
            patient_profile: Patient clinical data.
            inclusion_assessment: Upstream assessment from InclusionMatchingAgent.
            exclusion_assessment: Upstream assessment from ExclusionDetectionAgent.
            contradiction_assessment: Optional upstream assessment from ContradictionAgent.
            protocol_evidence: Optional protocol evidence chunks for provenance enrichment.

        Returns:
            Authoritative DecisionAssessment.
        """
        # 1. Authoritative Trial Isolation Validation
        self._validate_trial_isolation(
            trial_id=trial_id,
            inclusion_assessment=inclusion_assessment,
            exclusion_assessment=exclusion_assessment,
            contradiction_assessment=contradiction_assessment,
            protocol_evidence=protocol_evidence,
        )

        patient_id = patient_profile.patient_profile_id

        # 2. Extract key signals from upstream assessments
        failed_inclusions = [
            c for c in inclusion_assessment.criteria if c.status == InclusionStatus.FAIL
        ]
        unknown_inclusions = [
            c for c in inclusion_assessment.criteria if c.status == InclusionStatus.UNKNOWN
        ]
        passed_inclusions = [
            c for c in inclusion_assessment.criteria if c.status == InclusionStatus.PASS
        ]

        triggered_exclusions = [
            c for c in exclusion_assessment.criteria if c.status == ExclusionStatus.TRIGGERED
        ]
        unknown_exclusions = [
            c for c in exclusion_assessment.criteria if c.status == ExclusionStatus.UNKNOWN
        ]
        clear_exclusions = [
            c for c in exclusion_assessment.criteria if c.status == ExclusionStatus.CLEAR
        ]

        # 3. Analyze Contradictions & Silent Exclusions
        findings: List[ContradictionFinding] = []
        if contradiction_assessment and contradiction_assessment.findings:
            findings = contradiction_assessment.findings

        critical_contradictions: List[ContradictionFinding] = []
        warning_contradictions: List[ContradictionFinding] = []
        confirmed_silent_exclusions: List[ContradictionFinding] = []
        ambiguous_silent_exclusions: List[ContradictionFinding] = []

        for f in findings:
            is_silent = f.contradiction_type == ContradictionType.SILENT_EXCLUSION
            if is_silent:
                if self._is_confirmed_silent_exclusion(f):
                    confirmed_silent_exclusions.append(f)
                else:
                    ambiguous_silent_exclusions.append(f)
            elif f.severity == ContradictionSeverity.CRITICAL:
                critical_contradictions.append(f)
            elif f.severity == ContradictionSeverity.WARNING:
                # Warnings affecting criteria or eligibility
                warning_contradictions.append(f)

        # 4. Collect Unresolved Information & Missing Data
        unresolved_info: List[str] = []
        for missing in inclusion_assessment.missing_information:
            if missing not in unresolved_info:
                unresolved_info.append(f"Inclusion data missing: {missing}")
        for missing in exclusion_assessment.missing_information:
            if missing not in unresolved_info:
                unresolved_info.append(f"Exclusion data missing: {missing}")
        for c in unknown_inclusions:
            msg = f"Unknown inclusion criterion: {c.criterion_id} - {c.criterion_text}"
            if msg not in unresolved_info:
                unresolved_info.append(msg)
        for c in unknown_exclusions:
            msg = f"Unknown exclusion criterion: {c.criterion_id} - {c.criterion_text}"
            if msg not in unresolved_info:
                unresolved_info.append(msg)
        for amb in ambiguous_silent_exclusions:
            unresolved_info.append(f"Ambiguous silent exclusion: {amb.title}")
        for cc in critical_contradictions:
            unresolved_info.append(f"Critical contradiction: {cc.title} - {cc.description}")
        for wc in warning_contradictions:
            unresolved_info.append(f"Warning contradiction: {wc.title} - {wc.description}")

        # 5. Deterministic Classification & Priority Evaluation
        primary_reasons: List[str] = []
        decision_evidence: List[DecisionEvidence] = []
        final_status: DecisionStatus
        requires_human_review = False

        # Check total criteria evaluated
        total_criteria_evaluated = (
            len(passed_inclusions)
            + len(failed_inclusions)
            + len(unknown_inclusions)
            + len(clear_exclusions)
            + len(triggered_exclusions)
            + len(unknown_exclusions)
        )

        is_not_eligible = (
            len(failed_inclusions) > 0
            or len(triggered_exclusions) > 0
            or len(confirmed_silent_exclusions) > 0
        )

        # PRIORITY 0: ZERO CRITERIA (Protocol validation failure)
        if total_criteria_evaluated == 0:
            final_status = DecisionStatus.MORE_INFORMATION_REQUIRED
            requires_human_review = True
            primary_reasons.append(
                "Protocol validation failure: Zero eligibility criteria were evaluated. "
                "An eligibility assessment cannot declare a patient ELIGIBLE without verified protocol criteria."
            )
            decision_evidence.append(
                DecisionEvidence(
                    criterion_id="PROTOCOL-VALIDATION-ERROR",
                    criterion_text="Protocol Source of Truth & Criteria Verification",
                    patient_value=None,
                    status="VALIDATION_FAILED",
                    source_page=1,
                    source_document="protocol.pdf",
                    source_excerpt="No clinical trial inclusion or exclusion criteria identified in document.",
                    originating_agent="DecisionReviewerAgent",
                )
            )

        # PRIORITY 1: NOT_ELIGIBLE (Confirmed FAIL, TRIGGERED, or confirmed SILENT_EXCLUSION)
        elif is_not_eligible:
            final_status = DecisionStatus.NOT_ELIGIBLE

            for c in failed_inclusions:
                reason = f"Inclusion criterion {c.criterion_id} failed: {c.criterion_text}"
                primary_reasons.append(reason)
                decision_evidence.append(
                    DecisionEvidence(
                        criterion_id=c.criterion_id,
                        criterion_text=c.criterion_text,
                        patient_value=c.patient_value,
                        status="FAIL",
                        source_page=c.source_page,
                        source_document=c.source_document,
                        source_excerpt=c.source_excerpt,
                        originating_agent="InclusionMatchingAgent",
                    )
                )

            for c in triggered_exclusions:
                reason = f"Exclusion criterion {c.criterion_id} triggered: {c.criterion_text}"
                primary_reasons.append(reason)
                decision_evidence.append(
                    DecisionEvidence(
                        criterion_id=c.criterion_id,
                        criterion_text=c.criterion_text,
                        patient_value=c.patient_value,
                        status="TRIGGERED",
                        source_page=c.source_page,
                        source_document=c.source_document,
                        source_excerpt=c.source_excerpt,
                        originating_agent="ExclusionDetectionAgent",
                    )
                )

            for f in confirmed_silent_exclusions:
                reason = f"Confirmed silent exclusion: {f.title} ({f.description})"
                primary_reasons.append(reason)
                crit_id = f.criterion_ids[0] if f.criterion_ids else "SILENT-EXC"
                # Locate chunk provenance if available
                chunk_prov = self._find_chunk_provenance(crit_id, protocol_evidence)
                decision_evidence.append(
                    DecisionEvidence(
                        criterion_id=crit_id,
                        criterion_text=f.title,
                        patient_value=str(f.evidence) if f.evidence else None,
                        status="SILENT_EXCLUSION",
                        source_page=chunk_prov.get("source_page", 1),
                        source_document=chunk_prov.get("source_document", "protocol.pdf"),
                        source_excerpt=chunk_prov.get("source_excerpt", f.description),
                        originating_agent="ContradictionAgent",
                    )
                )

            # Human review on NOT_ELIGIBLE: Set true if there are contradictions or unresolved ambiguities
            if critical_contradictions or ambiguous_silent_exclusions or warning_contradictions:
                requires_human_review = True
            else:
                requires_human_review = False

        # PRIORITY 2: MORE_INFORMATION_REQUIRED
        elif (
            len(unknown_inclusions) > 0
            or len(unknown_exclusions) > 0
            or len(critical_contradictions) > 0
            or len(warning_contradictions) > 0
            or len(ambiguous_silent_exclusions) > 0
            or len(unresolved_info) > 0
        ):
            final_status = DecisionStatus.MORE_INFORMATION_REQUIRED
            requires_human_review = True

            if critical_contradictions:
                for cc in critical_contradictions:
                    primary_reasons.append(f"Critical contradiction: {cc.title} - {cc.description}")
                    crit_id = cc.criterion_ids[0] if cc.criterion_ids else "CONTRADICTION"
                    chunk_prov = self._find_chunk_provenance(crit_id, protocol_evidence)
                    decision_evidence.append(
                        DecisionEvidence(
                            criterion_id=crit_id,
                            criterion_text=cc.title,
                            patient_value=str(cc.evidence) if cc.evidence else None,
                            status="CRITICAL_CONTRADICTION",
                            source_page=chunk_prov.get("source_page", 1),
                            source_document=chunk_prov.get("source_document", "protocol.pdf"),
                            source_excerpt=chunk_prov.get("source_excerpt", cc.description),
                            originating_agent="ContradictionAgent",
                        )
                    )

            if warning_contradictions:
                for wc in warning_contradictions:
                    primary_reasons.append(f"Contradiction warning affecting eligibility: {wc.title}")
                    crit_id = wc.criterion_ids[0] if wc.criterion_ids else "WARNING"
                    chunk_prov = self._find_chunk_provenance(crit_id, protocol_evidence)
                    decision_evidence.append(
                        DecisionEvidence(
                            criterion_id=crit_id,
                            criterion_text=wc.title,
                            patient_value=str(wc.evidence) if wc.evidence else None,
                            status="WARNING_CONTRADICTION",
                            source_page=chunk_prov.get("source_page", 1),
                            source_document=chunk_prov.get("source_document", "protocol.pdf"),
                            source_excerpt=chunk_prov.get("source_excerpt", wc.description),
                            originating_agent="ContradictionAgent",
                        )
                    )

            if ambiguous_silent_exclusions:
                for amb in ambiguous_silent_exclusions:
                    primary_reasons.append(f"Unresolved potential silent exclusion: {amb.title}")
                    crit_id = amb.criterion_ids[0] if amb.criterion_ids else "AMBIGUOUS-EXC"
                    chunk_prov = self._find_chunk_provenance(crit_id, protocol_evidence)
                    decision_evidence.append(
                        DecisionEvidence(
                            criterion_id=crit_id,
                            criterion_text=amb.title,
                            patient_value=str(amb.evidence) if amb.evidence else None,
                            status="AMBIGUOUS_SILENT_EXCLUSION",
                            source_page=chunk_prov.get("source_page", 1),
                            source_document=chunk_prov.get("source_document", "protocol.pdf"),
                            source_excerpt=chunk_prov.get("source_excerpt", amb.description),
                            originating_agent="ContradictionAgent",
                        )
                    )

            if unknown_inclusions:
                for c in unknown_inclusions:
                    primary_reasons.append(f"Inclusion requirement unknown due to missing data: {c.criterion_id}")
                    decision_evidence.append(
                        DecisionEvidence(
                            criterion_id=c.criterion_id,
                            criterion_text=c.criterion_text,
                            patient_value=c.patient_value,
                            status="UNKNOWN",
                            source_page=c.source_page,
                            source_document=c.source_document,
                            source_excerpt=c.source_excerpt,
                            originating_agent="InclusionMatchingAgent",
                        )
                    )

            if unknown_exclusions:
                for c in unknown_exclusions:
                    primary_reasons.append(f"Exclusion criterion status unknown: {c.criterion_id}")
                    decision_evidence.append(
                        DecisionEvidence(
                            criterion_id=c.criterion_id,
                            criterion_text=c.criterion_text,
                            patient_value=c.patient_value,
                            status="UNKNOWN",
                            source_page=c.source_page,
                            source_document=c.source_document,
                            source_excerpt=c.source_excerpt,
                            originating_agent="ExclusionDetectionAgent",
                        )
                    )

        # PRIORITY 3: ELIGIBLE (Requires at least 1 verified passed inclusion)
        elif len(passed_inclusions) > 0:
            final_status = DecisionStatus.ELIGIBLE
            requires_human_review = False
            primary_reasons.append(
                f"All evaluated inclusion criteria ({len(passed_inclusions)}) met with no exclusions triggered ({len(clear_exclusions)} clear) and no critical contradictions."
            )
            # Include representative passed/clear evidence
            for c in passed_inclusions:
                decision_evidence.append(
                    DecisionEvidence(
                        criterion_id=c.criterion_id,
                        criterion_text=c.criterion_text,
                        patient_value=c.patient_value,
                        status="PASS",
                        source_page=c.source_page,
                        source_document=c.source_document,
                        source_excerpt=c.source_excerpt,
                        originating_agent="InclusionMatchingAgent",
                    )
                )
            for c in clear_exclusions:
                decision_evidence.append(
                    DecisionEvidence(
                        criterion_id=c.criterion_id,
                        criterion_text=c.criterion_text,
                        patient_value=c.patient_value,
                        status="CLEAR",
                        source_page=c.source_page,
                        source_document=c.source_document,
                        source_excerpt=c.source_excerpt,
                        originating_agent="ExclusionDetectionAgent",
                    )
                )

        else:
            final_status = DecisionStatus.MORE_INFORMATION_REQUIRED
            requires_human_review = True
            primary_reasons.append(
                "No protocol inclusion criteria were verified as satisfied from the patient record."
            )

        # Collect warnings
        warnings = list(inclusion_assessment.warnings) + list(exclusion_assessment.warnings)
        if contradiction_assessment and contradiction_assessment.findings:
            info_findings = [
                f for f in contradiction_assessment.findings if f.severity == ContradictionSeverity.INFO
            ]
            for inf in info_findings:
                warnings.append(f"Info note: {inf.title} - {inf.description}")

        return DecisionAssessment(
            trial_id=trial_id,
            patient_profile_id=patient_id,
            final_status=final_status,
            requires_human_review=requires_human_review,
            primary_reasons=primary_reasons,
            decision_evidence=decision_evidence,
            unresolved_information=unresolved_info,
            contradiction_findings=findings,
            warnings=warnings,
            disclaimer=self.CLINICAL_DISCLAIMER,
        )

    def _is_confirmed_silent_exclusion(self, finding: ContradictionFinding) -> bool:
        """Determines if a silent exclusion is confirmed or ambiguous."""
        title_lower = finding.title.lower()
        desc_lower = finding.description.lower()
        evidence_str = str(finding.evidence).lower() if finding.evidence else ""

        # Check for explicit confirmation flag or wording
        if isinstance(finding.evidence, dict):
            if finding.evidence.get("confirmed") is True or finding.evidence.get("is_confirmed") is True:
                return True
            if finding.evidence.get("confirmed") is False:
                return False

        if "confirmed" in title_lower or "confirmed" in desc_lower or "confirmed" in evidence_str:
            return True

        # Check for ambiguity indicators
        ambiguity_terms = ["ambiguous", "potential", "suspected", "possible", "unconfirmed", "unresolved"]
        if any(term in title_lower or term in desc_lower for term in ambiguity_terms):
            return False

        # If severity is CRITICAL without ambiguity terms, treat as confirmed
        return finding.severity == ContradictionSeverity.CRITICAL

    def _find_chunk_provenance(
        self,
        criterion_id: str,
        protocol_evidence: Optional[List[RetrievedChunk]],
    ) -> Dict[str, Any]:
        """Locates protocol document and page provenance for a given criterion ID."""
        if not protocol_evidence:
            return {"source_page": 1, "source_document": "protocol.pdf", "source_excerpt": None}
        for chunk in protocol_evidence:
            if chunk.criterion_id == criterion_id or chunk.chunk_id == criterion_id:
                return {
                    "source_page": chunk.source_page,
                    "source_document": chunk.source_document,
                    "source_excerpt": chunk.source_excerpt or chunk.text,
                }
        # Default to first chunk if available
        first = protocol_evidence[0]
        return {
            "source_page": first.source_page,
            "source_document": first.source_document,
            "source_excerpt": first.source_excerpt or first.text,
        }

    def _validate_trial_isolation(
        self,
        trial_id: str,
        inclusion_assessment: InclusionAssessment,
        exclusion_assessment: ExclusionAssessment,
        contradiction_assessment: Optional[ContradictionAssessment] = None,
        protocol_evidence: Optional[List[RetrievedChunk]] = None,
    ) -> None:
        """Validates that all inputs strictly belong to the authoritative trial_id."""
        if not trial_id or not trial_id.strip():
            raise ValueError("trial_id is required and cannot be empty")

        if inclusion_assessment.trial_id != trial_id:
            raise TrialIsolationError(
                f"Trial isolation violation: inclusion_assessment trial_id '{inclusion_assessment.trial_id}' "
                f"does not match selected trial '{trial_id}'"
            )

        if exclusion_assessment.trial_id != trial_id:
            raise TrialIsolationError(
                f"Trial isolation violation: exclusion_assessment trial_id '{exclusion_assessment.trial_id}' "
                f"does not match selected trial '{trial_id}'"
            )

        if contradiction_assessment and contradiction_assessment.trial_id != trial_id:
            raise TrialIsolationError(
                f"Trial isolation violation: contradiction_assessment trial_id '{contradiction_assessment.trial_id}' "
                f"does not match selected trial '{trial_id}'"
            )

        if protocol_evidence:
            for chunk in protocol_evidence:
                if chunk.trial_id != trial_id:
                    raise TrialIsolationError(
                        f"Trial isolation violation: protocol chunk '{chunk.chunk_id}' belongs to "
                        f"'{chunk.trial_id}', not selected trial '{trial_id}'"
                    )
