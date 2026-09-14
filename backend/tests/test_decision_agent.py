"""Unit and integration test suite for the Decision / Reviewer Agent (Checkpoint 10).

Covers:
1. ELIGIBLE conditions (all inclusion PASS, exclusion CLEAR, no contradictions/silent exclusions)
2. NOT_ELIGIBLE conditions (inclusion FAIL, exclusion TRIGGERED, confirmed silent exclusion)
3. MORE_INFORMATION_REQUIRED conditions (UNKNOWN criteria, critical contradictions, ambiguous silent exclusions)
4. Deterministic priority resolution (NOT_ELIGIBLE > MORE_INFORMATION_REQUIRED > ELIGIBLE)
5. Decisive criteria extraction and explanation generation
6. Provenance citations preservation
7. Clinical disclaimer validation
8. requires_human_review flagging rules
9. Strict trial isolation enforcement
10. Direct API endpoint (POST /api/v1/decision/evaluate) testing
11. End-to-end LangGraph integration with decision node
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.decision_reviewer_agent import DecisionReviewerAgent, TrialIsolationError
from app.graph.workflow import run_workflow
from app.main import app
from app.schemas.contradiction import (
    ContradictionAssessment,
    ContradictionFinding,
    ContradictionSeverity,
    ContradictionType,
)
from app.schemas.decision import (
    DecisionAssessment,
    DecisionStatus,
    EvaluateDecisionRequest,
)
from app.schemas.exclusion import (
    ExclusionAssessment,
    ExclusionCriterionAssessment,
    ExclusionStatus,
)
from app.schemas.inclusion import (
    InclusionAssessment,
    InclusionCriterionAssessment,
    InclusionStatus,
)
from app.schemas.patient import (
    ClinicalStatus,
    ConditionItem,
    Demographics,
    LabValue,
    Labs,
    MedicationItem,
    PatientProfile,
    PregnancyStatus,
    Sex,
)
from app.schemas.rag import RetrievedChunk


# =============================================================================
# Helper Fixtures
# =============================================================================

def make_patient(profile_id: str = "PT-DEC-001") -> PatientProfile:
    return PatientProfile(
        patient_profile_id=profile_id,
        demographics=Demographics(age=45, sex=Sex.FEMALE, pregnancy_status=PregnancyStatus.NOT_PREGNANT),
        clinical_status=ClinicalStatus(ecog_performance_status=0),
        conditions=[
            ConditionItem(name="Non-Small Cell Lung Cancer", status="active")
        ],
        labs=Labs(
            anc=LabValue(value=2.5, unit="10^9/L"),
            egfr=LabValue(value=65.0, unit="mL/min/1.73m2"),
        ),
        medications=[
            MedicationItem(name="Acetaminophen", dose="500mg", status="active")
        ],
    )


def make_evidence_chunk(
    trial_id: str,
    criterion_id: str,
    criterion_type: str,
    text: str,
    page: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{trial_id}-CHK-{criterion_id}",
        trial_id=trial_id,
        criterion_id=criterion_id,
        criterion_type=criterion_type,
        text=text,
        score=0.95,
        source_page=page,
        source_document="protocol_master.pdf",
        source_excerpt=f"Protocol excerpt: {text}",
    )


def make_passing_inclusion(trial_id: str) -> InclusionAssessment:
    return InclusionAssessment(
        trial_id=trial_id,
        patient_profile_id="PT-DEC-001",
        overall_status=InclusionStatus.PASS,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-AGE",
                trial_id=trial_id,
                status=InclusionStatus.PASS,
                criterion_text="Age >= 18",
                patient_value=45,
                expected_requirement=">= 18",
                rationale="Patient age 45 satisfies >= 18",
                source_page=1,
                source_document="protocol_master.pdf",
                source_excerpt="Age >= 18",
            ),
            InclusionCriterionAssessment(
                criterion_id="INC-EGFR",
                trial_id=trial_id,
                status=InclusionStatus.PASS,
                criterion_text="eGFR >= 30",
                patient_value=65.0,
                expected_requirement=">= 30",
                rationale="eGFR 65 satisfies >= 30",
                source_page=2,
                source_document="protocol_master.pdf",
                source_excerpt="eGFR >= 30",
            ),
        ],
        missing_information=[],
        warnings=[],
    )


def make_clear_exclusion(trial_id: str) -> ExclusionAssessment:
    return ExclusionAssessment(
        trial_id=trial_id,
        patient_profile_id="PT-DEC-001",
        overall_status=ExclusionStatus.CLEAR,
        criteria=[
            ExclusionCriterionAssessment(
                criterion_id="EXC-PREG",
                trial_id=trial_id,
                status=ExclusionStatus.CLEAR,
                criterion_text="Known active pregnancy",
                patient_value="Not pregnant",
                exclusion_requirement="Active pregnancy is excluded",
                rationale="No active pregnancy reported",
                source_page=4,
                source_document="protocol_master.pdf",
                source_excerpt="Active pregnancy excluded",
            )
        ],
        missing_information=[],
        warnings=[],
    )


def make_clean_contradiction(trial_id: str) -> ContradictionAssessment:
    return ContradictionAssessment(
        trial_id=trial_id,
        patient_profile_id="PT-DEC-001",
        findings=[],
        checked_criteria=["INC-AGE", "INC-EGFR", "EXC-PREG"],
        warnings=[],
        has_critical_findings=False,
    )


# =============================================================================
# 1-4: Deterministic Eligibility & Ineligibility Tests
# =============================================================================

def test_1_eligible_when_all_inclusion_pass_and_exclusions_clear():
    """1. Returns ELIGIBLE when inclusion PASS, exclusion CLEAR, and no contradictions."""
    trial_id = "TRIAL-DEC-001"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    chunk = make_evidence_chunk(trial_id, "INC-AGE", "inclusion", "Age >= 18")

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
        protocol_evidence=[chunk],
    )

    assert decision.final_status == DecisionStatus.ELIGIBLE
    assert decision.requires_human_review is False
    assert len(decision.primary_reasons) > 0
    assert "met" in decision.primary_reasons[0].lower()


def test_2_not_eligible_when_inclusion_fails():
    """2. Returns NOT_ELIGIBLE when any inclusion criterion FAILS."""
    trial_id = "TRIAL-DEC-002"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.FAIL
    inc.criteria.append(
        InclusionCriterionAssessment(
            criterion_id="INC-PLT",
            trial_id=trial_id,
            status=InclusionStatus.FAIL,
            criterion_text="Platelets >= 100k",
            patient_value=50.0,
            expected_requirement=">= 100k",
            rationale="Platelet count 50k below 100k threshold",
            source_page=2,
            source_document="protocol_master.pdf",
        )
    )
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert any("INC-PLT" in r for r in decision.primary_reasons)


def test_3_not_eligible_when_exclusion_triggered():
    """3. Returns NOT_ELIGIBLE when any exclusion criterion is TRIGGERED."""
    trial_id = "TRIAL-DEC-003"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    exc.overall_status = ExclusionStatus.TRIGGERED
    exc.criteria.append(
        ExclusionCriterionAssessment(
            criterion_id="EXC-HEPB",
            trial_id=trial_id,
            status=ExclusionStatus.TRIGGERED,
            criterion_text="Active Hepatitis B infection",
            patient_value="Positive HBsAg",
            exclusion_requirement="Active HBV triggers trial exclusion",
            rationale="Active HBV triggers trial exclusion",
            source_page=5,
            source_document="protocol_master.pdf",
        )
    )
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert any("EXC-HEPB" in r for r in decision.primary_reasons)


def test_4_not_eligible_when_confirmed_silent_exclusion():
    """4. Returns NOT_ELIGIBLE when a silent exclusion is confirmed."""
    trial_id = "TRIAL-DEC-004"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    contra.findings.append(
        ContradictionFinding(
            finding_id="FIND-SILENT-001",
            trial_id=trial_id,
            contradiction_type=ContradictionType.SILENT_EXCLUSION,
            severity=ContradictionSeverity.CRITICAL,
            title="Confirmed Silent Exclusion: Warfarin",
            description="Warfarin listed in current active medications falls under prohibited anticoagulants",
            criterion_ids=["EXC-WARFARIN"],
            patient_fields=["medications"],
            evidence={"drug": "Warfarin", "confirmed": True},
            recommended_action="Exclude patient due to prohibited anticoagulant therapy",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert any("Warfarin" in r or "Silent exclusion" in r for r in decision.primary_reasons)


# =============================================================================
# 5-9: MORE_INFORMATION_REQUIRED Tests
# =============================================================================

def test_5_more_info_required_when_inclusion_unknown():
    """5. Returns MORE_INFORMATION_REQUIRED when inclusion has UNKNOWN criteria."""
    trial_id = "TRIAL-DEC-005"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.UNKNOWN
    inc.criteria.append(
        InclusionCriterionAssessment(
            criterion_id="INC-PDL1",
            trial_id=trial_id,
            status=InclusionStatus.UNKNOWN,
            criterion_text="PD-L1 expression >= 50%",
            patient_value=None,
            expected_requirement=">= 50%",
            rationale="PD-L1 IHC report missing from profile",
            source_page=3,
            source_document="protocol_master.pdf",
        )
    )
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED
    assert decision.requires_human_review is True
    assert any("INC-PDL1" in u for u in decision.unresolved_information)


def test_6_more_info_required_when_exclusion_unknown():
    """6. Returns MORE_INFORMATION_REQUIRED when exclusion has UNKNOWN criteria."""
    trial_id = "TRIAL-DEC-006"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    exc.overall_status = ExclusionStatus.UNKNOWN
    exc.criteria.append(
        ExclusionCriterionAssessment(
            criterion_id="EXC-HIV",
            trial_id=trial_id,
            status=ExclusionStatus.UNKNOWN,
            criterion_text="Known HIV infection",
            patient_value=None,
            exclusion_requirement="HIV excluded",
            rationale="HIV status not documented in chart",
            source_page=5,
            source_document="protocol_master.pdf",
        )
    )
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED
    assert decision.requires_human_review is True
    assert any("EXC-HIV" in u for u in decision.unresolved_information)


def test_7_more_info_required_when_critical_contradiction():
    """7. Returns MORE_INFORMATION_REQUIRED when critical contradiction is present."""
    trial_id = "TRIAL-DEC-007"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    contra.has_critical_findings = True
    contra.findings.append(
        ContradictionFinding(
            finding_id="CF-001",
            trial_id=trial_id,
            contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
            severity=ContradictionSeverity.CRITICAL,
            title="Smoking History Conflict",
            description="Active smoker indicated in social history but non-smoker in clinical note",
            criterion_ids=["INC-SMOKING"],
            patient_fields=["social_history"],
            recommended_action="Verify tobacco history with patient.",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED
    assert decision.requires_human_review is True
    assert len(decision.contradiction_findings) == 1


def test_8_more_info_required_when_ambiguous_silent_exclusion():
    """8. Returns MORE_INFORMATION_REQUIRED when unconfirmed silent exclusion exists."""
    trial_id = "TRIAL-DEC-008"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    contra.findings.append(
        ContradictionFinding(
            finding_id="FIND-SILENT-AMB",
            trial_id=trial_id,
            contradiction_type=ContradictionType.SILENT_EXCLUSION,
            severity=ContradictionSeverity.WARNING,
            title="Potential Silent Exclusion: Herbal Supplement",
            description="Patient reports taking St. John's Wort intermittently - potential unverified CYP3A4 inducer",
            criterion_ids=["EXC-CYP3A4"],
            patient_fields=["medications"],
            evidence={"drug": "St. John's Wort", "confirmed": False},
            recommended_action="Clarify herbal supplement frequency and dosage with patient",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED
    assert decision.requires_human_review is True


def test_9_more_info_required_when_missing_information_listed():
    """9. Returns MORE_INFORMATION_REQUIRED when missing_information is populated."""
    trial_id = "TRIAL-DEC-009"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    inc.missing_information = ["Platelet count required"]
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED
    assert any("Platelet count required" in u for u in decision.unresolved_information)


# =============================================================================
# 10-12: Deterministic Priority Rules
# =============================================================================

def test_10_deterministic_priority_not_eligible_over_more_info():
    """10. NOT_ELIGIBLE takes priority over MORE_INFORMATION_REQUIRED (FAIL + UNKNOWN)."""
    trial_id = "TRIAL-DEC-010"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    # Inclusion has 1 FAIL and 1 UNKNOWN
    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.FAIL
    inc.criteria = [
        InclusionCriterionAssessment(
            criterion_id="INC-MET",
            trial_id=trial_id,
            status=InclusionStatus.PASS,
            criterion_text="Age >= 18",
            patient_value=45,
            expected_requirement=">= 18",
            rationale="Pass",
            source_page=1,
            source_document="protocol.pdf",
        ),
        InclusionCriterionAssessment(
            criterion_id="INC-FAIL",
            trial_id=trial_id,
            status=InclusionStatus.FAIL,
            criterion_text="eGFR >= 60",
            patient_value=25.0,
            expected_requirement=">= 60",
            rationale="Fail",
            source_page=2,
            source_document="protocol.pdf",
        ),
        InclusionCriterionAssessment(
            criterion_id="INC-UNK",
            trial_id=trial_id,
            status=InclusionStatus.UNKNOWN,
            criterion_text="PD-L1 status",
            patient_value=None,
            expected_requirement="Known",
            rationale="Unknown",
            source_page=3,
            source_document="protocol.pdf",
        ),
    ]

    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert any("INC-FAIL" in r for r in decision.primary_reasons)


def test_11_deterministic_priority_not_eligible_over_critical_contradiction():
    """11. NOT_ELIGIBLE takes priority over critical contradictions."""
    trial_id = "TRIAL-DEC-011"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    exc.overall_status = ExclusionStatus.TRIGGERED
    exc.criteria.append(
        ExclusionCriterionAssessment(
            criterion_id="EXC-LIVER",
            trial_id=trial_id,
            status=ExclusionStatus.TRIGGERED,
            criterion_text="End-stage liver disease",
            patient_value="Child-Pugh C",
            exclusion_requirement="Liver disease excluded",
            rationale="Exclusion triggered",
            source_page=5,
            source_document="protocol.pdf",
        )
    )

    # Contradiction also has critical findings
    contra = make_clean_contradiction(trial_id)
    contra.has_critical_findings = True
    contra.findings.append(
        ContradictionFinding(
            finding_id="CF-CRIT",
            trial_id=trial_id,
            contradiction_type=ContradictionType.PATIENT_FACT_CONTRADICTION,
            severity=ContradictionSeverity.CRITICAL,
            title="Conflicting Pathology Notes",
            description="Conflicting pathology notes regarding histological subtype",
            criterion_ids=["INC-HISTOLOGY"],
            patient_fields=["pathology"],
            recommended_action="Review biopsy specimens with pathologist.",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    # Priority rule: NOT_ELIGIBLE must be the final verdict
    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert any("EXC-LIVER" in r for r in decision.primary_reasons)


def test_12_deterministic_priority_more_info_over_eligible():
    """12. MORE_INFORMATION_REQUIRED takes priority over ELIGIBLE when any unknown exists."""
    trial_id = "TRIAL-DEC-012"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    exc.overall_status = ExclusionStatus.UNKNOWN
    exc.criteria.append(
        ExclusionCriterionAssessment(
            criterion_id="EXC-ALLERGY",
            trial_id=trial_id,
            status=ExclusionStatus.UNKNOWN,
            criterion_text="Known drug allergy",
            patient_value=None,
            exclusion_requirement="Allergy excluded",
            rationale="Allergy unknown",
            source_page=6,
            source_document="protocol.pdf",
        )
    )
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.MORE_INFORMATION_REQUIRED


# =============================================================================
# 13-16: Decisive Criteria, Provenance & Clinical Disclaimer
# =============================================================================

def test_13_decisive_evidence_contains_failing_criteria():
    """13. Decision evidence contains criteria with status FAIL."""
    trial_id = "TRIAL-DEC-013"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.FAIL
    inc.criteria.append(
        InclusionCriterionAssessment(
            criterion_id="INC-ECOG",
            trial_id=trial_id,
            status=InclusionStatus.FAIL,
            criterion_text="ECOG performance status 0-1",
            patient_value=3,
            expected_requirement="0-1",
            rationale="ECOG 3 exceeds allowed threshold",
            source_page=1,
            source_document="protocol.pdf",
        )
    )
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    failing_items = [e for e in decision.decision_evidence if e.status == "FAIL"]
    assert len(failing_items) > 0
    assert failing_items[0].criterion_id == "INC-ECOG"


def test_14_decisive_evidence_contains_triggered_exclusion():
    """14. Decision evidence contains criteria with status TRIGGERED."""
    trial_id = "TRIAL-DEC-014"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    exc.overall_status = ExclusionStatus.TRIGGERED
    exc.criteria.append(
        ExclusionCriterionAssessment(
            criterion_id="EXC-CHEMO",
            trial_id=trial_id,
            status=ExclusionStatus.TRIGGERED,
            criterion_text="Prior chemotherapy within 14 days",
            patient_value="Chemotherapy 5 days ago",
            exclusion_requirement="14 days washout",
            rationale="Washout period not met",
            source_page=4,
            source_document="protocol.pdf",
        )
    )
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    triggered_items = [e for e in decision.decision_evidence if e.status == "TRIGGERED"]
    assert len(triggered_items) > 0
    assert triggered_items[0].criterion_id == "EXC-CHEMO"


def test_15_provenance_citations_preserved_in_evidence():
    """15. Evidence citations preserve source document, source page, and source excerpt."""
    trial_id = "TRIAL-DEC-015"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    chunk = make_evidence_chunk(
        trial_id=trial_id,
        criterion_id="INC-AGE",
        criterion_type="inclusion",
        text="Age >= 18 years old",
        page=3,
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
        protocol_evidence=[chunk],
    )

    assert len(decision.decision_evidence) > 0
    citation = decision.decision_evidence[0]
    assert citation.source_document == "protocol_master.pdf"
    assert citation.source_page >= 1


def test_16_clinical_disclaimer_is_always_present():
    """16. Output strictly includes the clinical disclaimer communicating decision support."""
    trial_id = "TRIAL-DEC-016"
    agent = DecisionReviewerAgent()
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert "not an independent medical" in decision.disclaimer.lower()


# =============================================================================
# 17-20: requires_human_review Flagging Rules
# =============================================================================

def test_17_human_review_required_on_more_info_required():
    """17. requires_human_review is True when status is MORE_INFORMATION_REQUIRED."""
    trial_id = "TRIAL-DEC-017"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.UNKNOWN
    inc.criteria.append(
        InclusionCriterionAssessment(
            criterion_id="INC-UNKNOWN-X",
            trial_id=trial_id,
            status=InclusionStatus.UNKNOWN,
            criterion_text="Special biomarker status",
            patient_value=None,
            expected_requirement="Positive",
            rationale="Missing",
            source_page=2,
            source_document="protocol.pdf",
        )
    )
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.requires_human_review is True


def test_18_human_review_required_on_critical_contradiction():
    """18. requires_human_review is True when any critical contradiction exists."""
    trial_id = "TRIAL-DEC-018"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    contra.has_critical_findings = True
    contra.findings.append(
        ContradictionFinding(
            finding_id="CF-002",
            trial_id=trial_id,
            contradiction_type=ContradictionType.PROTOCOL_CONTRADICTION,
            severity=ContradictionSeverity.CRITICAL,
            title="Cross-Criteria Conflict",
            description="Inclusion allows Stage III, exclusion bars all locally advanced.",
            criterion_ids=["INC-STAGE", "EXC-LOC-ADV"],
            patient_fields=["staging"],
            recommended_action="Seek clarification from trial sponsor.",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.requires_human_review is True


def test_19_human_review_required_on_warning_contradiction_with_ineligibility():
    """19. requires_human_review is True when ineligibility is accompanied by warnings or contradictions."""
    trial_id = "TRIAL-DEC-019"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    inc.overall_status = InclusionStatus.FAIL
    inc.criteria.append(
        InclusionCriterionAssessment(
            criterion_id="INC-BORDERLINE",
            trial_id=trial_id,
            status=InclusionStatus.FAIL,
            criterion_text="Platelets >= 100k",
            patient_value=99.0,
            expected_requirement=">= 100k",
            rationale="Borderline platelet count",
            source_page=2,
            source_document="protocol.pdf",
        )
    )
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    contra.findings.append(
        ContradictionFinding(
            finding_id="CF-WARN-01",
            trial_id=trial_id,
            contradiction_type=ContradictionType.ASSESSMENT_CONTRADICTION,
            severity=ContradictionSeverity.WARNING,
            title="Lab value fluctuation",
            description="Platelet values fluctuated across reports",
            criterion_ids=["INC-BORDERLINE"],
            patient_fields=["labs"],
            recommended_action="Repeat lab test.",
        )
    )

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.NOT_ELIGIBLE
    assert decision.requires_human_review is True


def test_20_human_review_not_required_on_clean_eligible():
    """20. requires_human_review is False on definitive clean ELIGIBLE."""
    trial_id = "TRIAL-DEC-020"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    decision = agent.evaluate(
        trial_id=trial_id,
        patient_profile=patient,
        inclusion_assessment=inc,
        exclusion_assessment=exc,
        contradiction_assessment=contra,
    )

    assert decision.final_status == DecisionStatus.ELIGIBLE
    assert decision.requires_human_review is False


# =============================================================================
# 21-24: Strict Trial Isolation Enforcement
# =============================================================================

def test_21_trial_isolation_rejects_mismatched_inclusion_trial_id():
    """21. Raises TrialIsolationError when inclusion_assessment has wrong trial_id."""
    trial_id = "TRIAL-DEC-021"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion("DIFFERENT-TRIAL-999")
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    with pytest.raises(TrialIsolationError) as exc_info:
        agent.evaluate(
            trial_id=trial_id,
            patient_profile=patient,
            inclusion_assessment=inc,
            exclusion_assessment=exc,
            contradiction_assessment=contra,
        )
    assert "DIFFERENT-TRIAL-999" in str(exc_info.value)


def test_22_trial_isolation_rejects_mismatched_exclusion_trial_id():
    """22. Raises TrialIsolationError when exclusion_assessment has wrong trial_id."""
    trial_id = "TRIAL-DEC-022"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion("DIFFERENT-TRIAL-888")
    contra = make_clean_contradiction(trial_id)

    with pytest.raises(TrialIsolationError) as exc_info:
        agent.evaluate(
            trial_id=trial_id,
            patient_profile=patient,
            inclusion_assessment=inc,
            exclusion_assessment=exc,
            contradiction_assessment=contra,
        )
    assert "DIFFERENT-TRIAL-888" in str(exc_info.value)


def test_23_trial_isolation_rejects_mismatched_contradiction_trial_id():
    """23. Raises TrialIsolationError when contradiction_assessment has wrong trial_id."""
    trial_id = "TRIAL-DEC-023"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction("DIFFERENT-TRIAL-777")

    with pytest.raises(TrialIsolationError) as exc_info:
        agent.evaluate(
            trial_id=trial_id,
            patient_profile=patient,
            inclusion_assessment=inc,
            exclusion_assessment=exc,
            contradiction_assessment=contra,
        )
    assert "DIFFERENT-TRIAL-777" in str(exc_info.value)


def test_24_trial_isolation_rejects_mismatched_chunk_evidence():
    """24. Raises TrialIsolationError when protocol_evidence contains foreign chunk."""
    trial_id = "TRIAL-DEC-024"
    agent = DecisionReviewerAgent()
    patient = make_patient()

    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)
    foreign_chunk = make_evidence_chunk("FOREIGN-TRIAL-001", "INC-1", "inclusion", "Foreign rule")

    with pytest.raises(TrialIsolationError) as exc_info:
        agent.evaluate(
            trial_id=trial_id,
            patient_profile=patient,
            inclusion_assessment=inc,
            exclusion_assessment=exc,
            contradiction_assessment=contra,
            protocol_evidence=[foreign_chunk],
        )
    assert "FOREIGN-TRIAL-001" in str(exc_info.value)


# =============================================================================
# 25-27: API Endpoint & LangGraph Workflow Integration
# =============================================================================

def test_25_api_evaluate_endpoint_returns_valid_assessment():
    """25. Direct API POST /api/v1/decision/evaluate returns valid DecisionAssessment."""
    client = TestClient(app)
    trial_id = "TRIAL-DEC-025"
    patient = make_patient()
    inc = make_passing_inclusion(trial_id)
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    payload = {
        "trial_id": trial_id,
        "patient_profile": patient.model_dump(),
        "inclusion_assessment": inc.model_dump(),
        "exclusion_assessment": exc.model_dump(),
        "contradiction_assessment": contra.model_dump(),
    }

    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["trial_id"] == trial_id
    assert data["patient_profile_id"] == patient.patient_profile_id
    assert data["final_status"] == "ELIGIBLE"
    assert "disclaimer" in data
    assert "requires_human_review" in data


def test_26_api_evaluate_endpoint_rejects_trial_mismatch():
    """26. Direct API POST /api/v1/decision/evaluate returns 400 on trial mismatch."""
    client = TestClient(app)
    trial_id = "TRIAL-DEC-026"
    patient = make_patient()
    inc = make_passing_inclusion("MISMATCHED-TRIAL-ID")
    exc = make_clear_exclusion(trial_id)
    contra = make_clean_contradiction(trial_id)

    payload = {
        "trial_id": trial_id,
        "patient_profile": patient.model_dump(),
        "inclusion_assessment": inc.model_dump(),
        "exclusion_assessment": exc.model_dump(),
        "contradiction_assessment": contra.model_dump(),
    }

    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 400
    assert "Trial isolation violation" in response.json()["detail"]


@pytest.mark.asyncio
async def test_27_workflow_integration_executes_decision_node_to_completion():
    """27. End-to-end LangGraph workflow executes all nodes including decision node."""
    trial_id = "TRIAL-DEC-027"
    patient = make_patient("PT-WF-DEC")
    chunk_inc = make_evidence_chunk(trial_id, "INC-AGE", "inclusion", "Age >= 18")
    chunk_exc = make_evidence_chunk(trial_id, "EXC-PREG", "exclusion", "No active pregnancy")

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=[chunk_inc, chunk_exc],
    )

    assert final_state["current_step"] == "decision"
    assert final_state["errors"] == []
    assert final_state["decision_assessment"] is not None

    decision = final_state["decision_assessment"]
    assert isinstance(decision, DecisionAssessment)
    assert decision.trial_id == trial_id
    assert decision.final_status in (
        DecisionStatus.ELIGIBLE,
        DecisionStatus.NOT_ELIGIBLE,
        DecisionStatus.MORE_INFORMATION_REQUIRED,
    )
    assert "not an independent medical" in decision.disclaimer.lower()
