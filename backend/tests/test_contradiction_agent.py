"""Comprehensive test suite for the Contradiction & Silent Exclusion Agent.

Tests cover all 25+ mandatory cases:
1. Age >=18 inclusion + age <18 exclusion -> NO contradiction
2. Age >=18 + age <=12 mandatory requirements -> PROTOCOL_CONTRADICTION
3. ECOG 0-1 + ECOG >=3 -> PROTOCOL_CONTRADICTION
4. COPD required + COPD forbidden -> PROTOCOL_CONTRADICTION
5. eGFR 20 + inclusion >=30 + assessment PASS -> ASSESSMENT_CONTRADICTION
6. eGFR 20 + exclusion <30 + assessment CLEAR -> ASSESSMENT_CONTRADICTION
7. Two contemporaneous conflicting eGFR values -> PATIENT_FACT_CONTRADICTION
8. Same field with different dates -> no false contradiction
9. Recent stroke protocol exclusion + recent stroke patient + missing exclusion assessment -> SILENT_EXCLUSION
10. Stroke exclusion + missing stroke information -> NOT silent exclusion
11. Unknown patient information -> no unsupported silent exclusion
12. Cross-trial protocol evidence -> reject (TrialIsolationError)
13. Cross-trial inclusion assessment -> reject (TrialIsolationError)
14. Cross-trial exclusion assessment -> reject (TrialIsolationError)
15. Provenance preserved
16. Active infection true + false contemporaneously -> PATIENT_FACT_CONTRADICTION
17. Pregnancy true + false contemporaneously -> PATIENT_FACT_CONTRADICTION
18. Protocol boolean contradiction
19. Boundary conditions
20. Normal inclusion/exclusion boundary -> no contradiction
21. Completely consistent protocol/patient/assessments -> zero findings
22. Multiple independent findings returned
23. Matching assessment -> no assessment contradiction
24. Missing assessment criterion + triggered exclusion -> silent exclusion
25. No hallucinated protocol exclusion
26. API endpoint POST /api/v1/contradiction/analyze tests
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.contradiction_agent import ContradictionAgent, TrialIsolationError
from app.main import app
from app.schemas.contradiction import (
    AnalyzeContradictionRequest,
    ContradictionAssessment,
    ContradictionSeverity,
    ContradictionType,
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
    PatientProfile,
    PregnancyStatus,
    TreatmentHistory,
)
from app.schemas.rag import RetrievedChunk


# =============================================================================
# Helper Fixtures
# =============================================================================

def build_consistent_patient() -> PatientProfile:
    """Builds a consistent, eligible baseline patient."""
    return PatientProfile(
        patient_profile_id="PAT-CONSISTENT-001",
        demographics=Demographics(
            age=55,
            pregnancy_status=PregnancyStatus.NOT_PREGNANT,
            breastfeeding_status=False,
        ),
        clinical_status=ClinicalStatus(
            ecog_performance_status=1,
            active_serious_infection=False,
            uncontrolled_cardiac_disease=False,
        ),
        labs=Labs(
            egfr=LabValue(value=65.0, unit="mL/min/1.73m2"),
            anc=LabValue(value=2.5, unit="x10^9/L"),
            platelets=LabValue(value=180.0, unit="x10^9/L"),
            hemoglobin=LabValue(value=12.0, unit="g/dL"),
            bilirubin=LabValue(value=0.8, unit="mg/dL"),
            ast=LabValue(value=24.0, unit="U/L"),
            alt=LabValue(value=22.0, unit="U/L"),
        ),
        conditions=[
            ConditionItem(name="Non-Small Cell Lung Cancer", status="active", documented=True),
        ],
        treatment_history=TreatmentHistory(
            recent_systemic_anticancer_therapy=False,
            last_treatment_date="2025-01-01",
        ),
    )


# =============================================================================
# Test Cases 1 to 26
# =============================================================================

@pytest.mark.asyncio
async def test_case_1_complementary_age_boundary_not_contradiction():
    """Case 1: Age >= 18 (inclusion) + Age < 18 (exclusion) is NOT a contradiction."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-AGE",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE",
            criterion_type="inclusion",
            text="Age >= 18 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-AGE",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-AGE",
            criterion_type="exclusion",
            text="Age < 18 years",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 0


@pytest.mark.asyncio
async def test_case_2_mutually_exclusive_age_inclusions():
    """Case 2: Age >= 18 and Age <= 12 mandatory requirements -> PROTOCOL_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-1",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE-1",
            criterion_type="inclusion",
            text="Age >= 18 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-INC-2",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE-2",
            criterion_type="inclusion",
            text="Age <= 12 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 1
    assert "INC-AGE-1" in proto_findings[0].criterion_ids
    assert "INC-AGE-2" in proto_findings[0].criterion_ids
    assert proto_findings[0].severity == ContradictionSeverity.CRITICAL


@pytest.mark.asyncio
async def test_case_3_ecog_disjoint_inclusions():
    """Case 3: ECOG 0-1 and ECOG >= 3 -> PROTOCOL_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-ECOG-1",
            trial_id="SYN-ONC-001",
            criterion_id="INC-ECOG-1",
            criterion_type="inclusion",
            text="ECOG performance status 0-1",
            score=0.9,
            source_page=3,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-ECOG-2",
            trial_id="SYN-ONC-001",
            criterion_id="INC-ECOG-2",
            criterion_type="inclusion",
            text="ECOG performance status >= 3",
            score=0.9,
            source_page=3,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 1
    assert "ECOG" in proto_findings[0].title


@pytest.mark.asyncio
async def test_case_4_condition_required_and_forbidden():
    """Case 4: COPD required (inclusion) + COPD forbidden (exclusion) -> PROTOCOL_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-COPD-INC",
            trial_id="SYN-PULM-001",
            criterion_id="INC-COPD",
            criterion_type="inclusion",
            text="Documented diagnosis of COPD",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-COPD-EXC",
            trial_id="SYN-PULM-001",
            criterion_id="EXC-COPD",
            criterion_type="exclusion",
            text="History of COPD or severe pulmonary disease",
            score=0.9,
            source_page=4,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-PULM-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 1
    assert "COPD" in proto_findings[0].title
    assert proto_findings[0].severity == ContradictionSeverity.CRITICAL


@pytest.mark.asyncio
async def test_case_5_egfr_inclusion_assessment_contradiction():
    """Case 5: eGFR = 20, Inclusion requirement >= 30, but assessment reported PASS -> ASSESSMENT_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr.value = 20.0  # Actually fails >= 30

    inclusion_assessment = InclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id="PAT-CONSISTENT-001",
        overall_status=InclusionStatus.PASS,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-RENAL",
                trial_id="SYN-ONC-001",
                status=InclusionStatus.PASS,  # Contradictory!
                criterion_text="eGFR >= 30 mL/min/1.73m2",
                patient_value=20.0,
                expected_requirement=">= 30",
                rationale="Erroneously marked pass",
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=[],
        inclusion_assessment=inclusion_assessment,
    )

    assess_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.ASSESSMENT_CONTRADICTION]
    assert len(assess_findings) == 1
    assert "INC-RENAL" in assess_findings[0].criterion_ids
    assert assess_findings[0].severity == ContradictionSeverity.CRITICAL


@pytest.mark.asyncio
async def test_case_6_egfr_exclusion_assessment_contradiction():
    """Case 6: eGFR = 20, Exclusion requirement < 30, but assessment reported CLEAR -> ASSESSMENT_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr.value = 20.0  # Satisfies < 30 -> TRIGGERED

    exclusion_assessment = ExclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id="PAT-CONSISTENT-001",
        overall_status=ExclusionStatus.CLEAR,
        criteria=[
            ExclusionCriterionAssessment(
                criterion_id="EXC-RENAL",
                trial_id="SYN-ONC-001",
                status=ExclusionStatus.CLEAR,  # Contradictory!
                criterion_text="eGFR < 30 mL/min/1.73m2",
                patient_value=20.0,
                exclusion_requirement="< 30",
                rationale="Erroneously marked clear",
                source_page=4,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=[],
        exclusion_assessment=exclusion_assessment,
    )

    assess_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.ASSESSMENT_CONTRADICTION]
    assert len(assess_findings) == 1
    assert "EXC-RENAL" in assess_findings[0].criterion_ids
    assert assess_findings[0].severity == ContradictionSeverity.CRITICAL


@pytest.mark.asyncio
async def test_case_7_contemporaneous_conflicting_egfr_labs():
    """Case 7: Two contemporaneous conflicting eGFR values -> PATIENT_FACT_CONTRADICTION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr.value = 20.0
    patient.labs.other_labs["duplicate_egfr_conflict"] = LabValue(value=68.0, unit="mL/min/1.73m2")

    result = await agent.analyze("SYN-ONC-001", patient, [])

    patient_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PATIENT_FACT_CONTRADICTION]
    assert len(patient_findings) == 1
    assert "eGFR" in patient_findings[0].description


@pytest.mark.asyncio
async def test_case_8_different_dates_no_false_contradiction():
    """Case 8: Same field with different dates (longitudinal) -> No false contradiction."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    # Prior treatment was in 2025, current status is different -> Valid history
    patient.treatment_history.last_treatment_date = "2024-01-01"
    patient.treatment_history.recent_systemic_anticancer_therapy = False

    result = await agent.analyze("SYN-ONC-001", patient, [])

    patient_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PATIENT_FACT_CONTRADICTION]
    assert len(patient_findings) == 0


@pytest.mark.asyncio
async def test_case_9_silent_exclusion_detected():
    """Case 9: Protocol exclusion triggered by patient facts but omitted from ExclusionAssessment -> SILENT_EXCLUSION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.conditions.append(
        ConditionItem(
            name="Ischemic Stroke",
            status="active",
            documented=True,
            source_provenance="Date: 2026-03-01",  # ~6 months ago <= 12 months
        )
    )

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-007",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-007",
            criterion_type="exclusion",
            text="History of stroke or TIA within 12 months",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        )
    ]

    # Upstream exclusion assessment did NOT assess EXC-007!
    exclusion_assessment = ExclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=ExclusionStatus.CLEAR,
        criteria=[
            ExclusionCriterionAssessment(
                criterion_id="EXC-001",
                trial_id="SYN-ONC-001",
                status=ExclusionStatus.CLEAR,
                criterion_text="Active serious infection",
                patient_value=False,
                exclusion_requirement="No infection",
                rationale="Clear",
                source_page=5,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=evidence,
        exclusion_assessment=exclusion_assessment,
        reference_date="2026-09-14",
    )

    silent_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.SILENT_EXCLUSION]
    assert len(silent_findings) == 1
    assert "EXC-007" in silent_findings[0].criterion_ids
    assert silent_findings[0].severity == ContradictionSeverity.CRITICAL


@pytest.mark.asyncio
async def test_case_10_stroke_missing_info_not_silent_exclusion():
    """Case 10: Stroke exclusion when patient stroke info is missing -> NOT silent exclusion."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    # Patient has NO stroke info documented (patient.conditions has only lung cancer)

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-007",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-007",
            criterion_type="exclusion",
            text="History of stroke or TIA within 12 months",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        )
    ]

    exclusion_assessment = ExclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=ExclusionStatus.CLEAR,
        criteria=[],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=evidence,
        exclusion_assessment=exclusion_assessment,
        reference_date="2026-09-14",
    )

    # Missing info yields UNKNOWN in evaluation, which must NEVER be marked as silent exclusion!
    silent_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.SILENT_EXCLUSION]
    assert len(silent_findings) == 0


@pytest.mark.asyncio
async def test_case_11_unknown_patient_info_no_unsupported_silent_exclusion():
    """Case 11: Missing lab eGFR -> Do NOT report silent exclusion."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr = None  # Missing!

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-RENAL",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-RENAL",
            criterion_type="exclusion",
            text="eGFR < 30 mL/min/1.73m2",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        )
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    silent_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.SILENT_EXCLUSION]
    assert len(silent_findings) == 0


@pytest.mark.asyncio
async def test_case_12_cross_trial_protocol_evidence_rejected():
    """Case 12: Protocol evidence belonging to mismatched trial raises TrialIsolationError."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-1",
            trial_id="SYN-MISMATCH-999",  # Cross trial!
            criterion_id="INC-1",
            criterion_type="inclusion",
            text="Age >= 18",
            score=0.9,
            source_page=1,
            source_document="protocol.pdf",
        )
    ]

    with pytest.raises(TrialIsolationError) as exc_info:
        await agent.analyze("SYN-ONC-001", patient, evidence)

    assert "Trial isolation violation" in str(exc_info.value)
    assert "SYN-MISMATCH-999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_13_cross_trial_inclusion_assessment_rejected():
    """Case 13: Inclusion assessment with mismatched trial raises TrialIsolationError."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    inc = InclusionAssessment(
        trial_id="SYN-WRONG-TRIAL",  # Mismatch!
        patient_profile_id=patient.patient_profile_id,
        overall_status=InclusionStatus.PASS,
        criteria=[],
    )

    with pytest.raises(TrialIsolationError) as exc_info:
        await agent.analyze("SYN-ONC-001", patient, [], inclusion_assessment=inc)

    assert "Trial isolation violation" in str(exc_info.value)
    assert "SYN-WRONG-TRIAL" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_14_cross_trial_exclusion_assessment_rejected():
    """Case 14: Exclusion assessment with mismatched trial raises TrialIsolationError."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    exc = ExclusionAssessment(
        trial_id="SYN-WRONG-TRIAL-2",  # Mismatch!
        patient_profile_id=patient.patient_profile_id,
        overall_status=ExclusionStatus.CLEAR,
        criteria=[],
    )

    with pytest.raises(TrialIsolationError) as exc_info:
        await agent.analyze("SYN-ONC-001", patient, [], exclusion_assessment=exc)

    assert "Trial isolation violation" in str(exc_info.value)
    assert "SYN-WRONG-TRIAL-2" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_15_provenance_preserved():
    """Case 15: Findings preserve criterion IDs, patient fields, and evidence."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr.value = 15.0

    inclusion_assessment = InclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=InclusionStatus.PASS,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-RENAL-PROV",
                trial_id="SYN-ONC-001",
                status=InclusionStatus.PASS,
                criterion_text="eGFR >= 30 mL/min/1.73m2",
                patient_value=15.0,
                expected_requirement=">= 30",
                rationale="Pass",
                source_page=7,
                source_document="protocol_prov.pdf",
                source_excerpt="eGFR >= 30 required",
            )
        ],
    )

    result = await agent.analyze("SYN-ONC-001", patient, [], inclusion_assessment=inclusion_assessment)

    assert len(result.findings) >= 1
    finding = result.findings[0]
    assert "INC-RENAL-PROV" in finding.criterion_ids
    assert finding.trial_id == "SYN-ONC-001"
    assert finding.finding_id.startswith("FINDING-")
    assert finding.recommended_action != ""


@pytest.mark.asyncio
async def test_case_16_active_infection_true_and_false_contemporaneously():
    """Case 16: clinical_status active_serious_infection=False while active infection condition exists."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.clinical_status.active_serious_infection = False
    patient.conditions.append(
        ConditionItem(name="Active Serious Bacterial Infection", status="active", documented=True)
    )

    result = await agent.analyze("SYN-ONC-001", patient, [])

    patient_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PATIENT_FACT_CONTRADICTION]
    assert len(patient_findings) == 1
    assert "infection" in patient_findings[0].title.lower()


@pytest.mark.asyncio
async def test_case_17_pregnancy_true_and_false_contemporaneously():
    """Case 17: Demographics not_pregnant while active pregnancy condition exists."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.demographics.pregnancy_status = PregnancyStatus.NOT_PREGNANT
    patient.conditions.append(
        ConditionItem(name="Active Intrauterine Pregnancy", status="active", documented=True)
    )

    result = await agent.analyze("SYN-ONC-001", patient, [])

    patient_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PATIENT_FACT_CONTRADICTION]
    assert len(patient_findings) == 1
    assert "pregnancy" in patient_findings[0].title.lower()


@pytest.mark.asyncio
async def test_case_18_protocol_boolean_contradiction():
    """Case 18: Protocol criterion A requires active infection, criterion B excludes active infection."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INF-REQ",
            trial_id="SYN-INF-001",
            criterion_id="INC-INF",
            criterion_type="inclusion",
            text="Documented active infection requiring IV antibiotics",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-INF-EXC",
            trial_id="SYN-INF-001",
            criterion_id="EXC-INF",
            criterion_type="exclusion",
            text="Active infection is excluded",
            score=0.9,
            source_page=4,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-INF-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 1
    assert "Active Infection" in proto_findings[0].title


@pytest.mark.asyncio
async def test_case_19_boundary_conditions_numeric_operators():
    """Case 19: Boundary condition: Age in [18, 65] vs Age in [65, 80] shares boundary 65 -> Overlap exists!"""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-1",
            trial_id="SYN-ONC-001",
            criterion_id="INC-1",
            criterion_type="inclusion",
            text="Age between 18 and 65 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-2",
            trial_id="SYN-ONC-001",
            criterion_id="INC-2",
            criterion_type="inclusion",
            text="Age between 65 and 80 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    # Point 65 is shared: they intersect at 65, so not strictly disjoint
    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 0


@pytest.mark.asyncio
async def test_case_20_normal_inclusion_exclusion_boundary():
    """Case 20: Inclusion eGFR >= 30 and Exclusion eGFR < 30 -> No contradiction."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-EGFR",
            trial_id="SYN-ONC-001",
            criterion_id="INC-EGFR",
            criterion_type="inclusion",
            text="eGFR >= 30 mL/min/1.73m2",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-EGFR",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-EGFR",
            criterion_type="exclusion",
            text="eGFR < 30 mL/min/1.73m2",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        ),
    ]

    result = await agent.analyze("SYN-ONC-001", patient, evidence)

    proto_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.PROTOCOL_CONTRADICTION]
    assert len(proto_findings) == 0


@pytest.mark.asyncio
async def test_case_21_completely_consistent_zero_findings():
    """Case 21: Completely consistent protocol, patient, and assessments -> zero findings."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-AGE",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE",
            criterion_type="inclusion",
            text="Age >= 18 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-INF",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-INF",
            criterion_type="exclusion",
            text="Active serious infection",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        ),
    ]

    inc_assess = InclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=InclusionStatus.PASS,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-AGE",
                trial_id="SYN-ONC-001",
                status=InclusionStatus.PASS,
                criterion_text="Age >= 18 years",
                patient_value=55,
                expected_requirement=">= 18",
                rationale="55 >= 18",
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    exc_assess = ExclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=ExclusionStatus.CLEAR,
        criteria=[
            ExclusionCriterionAssessment(
                criterion_id="EXC-INF",
                trial_id="SYN-ONC-001",
                status=ExclusionStatus.CLEAR,
                criterion_text="Active serious infection",
                patient_value=False,
                exclusion_requirement="No infection",
                rationale="Clear",
                source_page=5,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=evidence,
        inclusion_assessment=inc_assess,
        exclusion_assessment=exc_assess,
    )

    assert len(result.findings) == 0
    assert result.has_critical_findings is False


@pytest.mark.asyncio
async def test_case_22_multiple_independent_findings_returned():
    """Case 22: Protocol contradiction + patient contradiction + assessment contradiction simultaneously."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    # 1. Patient contradiction: infection False + active infection in conditions
    patient.clinical_status.active_serious_infection = False
    patient.conditions.append(ConditionItem(name="Active Serious Infection", status="active", documented=True))

    # 2. Protocol contradiction: Age >= 18 and Age <= 12
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-1",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE-1",
            criterion_type="inclusion",
            text="Age >= 18 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-2",
            trial_id="SYN-ONC-001",
            criterion_id="INC-AGE-2",
            criterion_type="inclusion",
            text="Age <= 12 years",
            score=0.9,
            source_page=2,
            source_document="protocol.pdf",
        ),
    ]

    # 3. Assessment contradiction: eGFR = 65, but inclusion assessment claimed FAIL
    inc_assess = InclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=InclusionStatus.FAIL,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-EGFR",
                trial_id="SYN-ONC-001",
                status=InclusionStatus.FAIL,  # Contradicts true eGFR 65 >= 30
                criterion_text="eGFR >= 30 mL/min/1.73m2",
                patient_value=65.0,
                expected_requirement=">= 30",
                rationale="Fails",
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=evidence,
        inclusion_assessment=inc_assess,
    )

    types = {f.contradiction_type for f in result.findings}
    assert ContradictionType.PROTOCOL_CONTRADICTION in types
    assert ContradictionType.PATIENT_FACT_CONTRADICTION in types
    assert ContradictionType.ASSESSMENT_CONTRADICTION in types
    assert len(result.findings) >= 3
    assert result.has_critical_findings is True


@pytest.mark.asyncio
async def test_case_23_matching_assessment_no_assessment_contradiction():
    """Case 23: Assessment matching deterministic ground truth produces no assessment contradiction."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.labs.egfr.value = 65.0

    inc_assess = InclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=InclusionStatus.PASS,
        criteria=[
            InclusionCriterionAssessment(
                criterion_id="INC-EGFR",
                trial_id="SYN-ONC-001",
                status=InclusionStatus.PASS,  # Correct!
                criterion_text="eGFR >= 30 mL/min/1.73m2",
                patient_value=65.0,
                expected_requirement=">= 30",
                rationale="Pass",
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    result = await agent.analyze("SYN-ONC-001", patient, [], inclusion_assessment=inc_assess)

    assess_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.ASSESSMENT_CONTRADICTION]
    assert len(assess_findings) == 0


@pytest.mark.asyncio
async def test_case_24_missing_assessment_criterion_plus_triggered_exclusion():
    """Case 24: Missing assessment criterion + triggered exclusion -> SILENT_EXCLUSION."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.clinical_status.active_serious_infection = True  # Patient triggers infection exclusion

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-INF",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-INF",
            criterion_type="exclusion",
            text="Active serious infection",
            score=0.9,
            source_page=5,
            source_document="protocol.pdf",
        )
    ]

    # Exclusion assessment completely omitted EXC-INF
    exclusion_assessment = ExclusionAssessment(
        trial_id="SYN-ONC-001",
        patient_profile_id=patient.patient_profile_id,
        overall_status=ExclusionStatus.CLEAR,
        criteria=[],
    )

    result = await agent.analyze(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=evidence,
        exclusion_assessment=exclusion_assessment,
    )

    silent_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.SILENT_EXCLUSION]
    assert len(silent_findings) == 1
    assert "EXC-INF" in silent_findings[0].criterion_ids


@pytest.mark.asyncio
async def test_case_25_no_hallucinated_protocol_exclusion():
    """Case 25: Do not report silent exclusion for criteria not present in protocol evidence."""
    agent = ContradictionAgent()
    patient = build_consistent_patient()
    patient.clinical_status.active_serious_infection = True

    # Empty protocol evidence -> No criteria exist -> Never invent one
    result = await agent.analyze("SYN-ONC-001", patient, protocol_evidence=[])

    silent_findings = [f for f in result.findings if f.contradiction_type == ContradictionType.SILENT_EXCLUSION]
    assert len(silent_findings) == 0


def test_case_26_api_analyze_contradictions_success():
    """Case 26: Test FastAPI POST /api/v1/contradiction/analyze endpoint."""
    client = TestClient(app)
    patient = build_consistent_patient()

    req = AnalyzeContradictionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=[
            RetrievedChunk(
                chunk_id="CHK-INC-AGE",
                trial_id="SYN-ONC-001",
                criterion_id="INC-AGE",
                criterion_type="inclusion",
                text="Age >= 18 years",
                score=0.9,
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    response = client.post("/api/v1/contradiction/analyze", json=req.model_dump())
    assert response.status_code == 200

    data = response.json()
    assert data["trial_id"] == "SYN-ONC-001"
    assert data["patient_profile_id"] == patient.patient_profile_id
    assert "findings" in data
    assert "checked_criteria" in data


def test_case_27_api_mismatched_trial_returns_400():
    """Case 27: Test API endpoint returns 400 when trial isolation is violated."""
    client = TestClient(app)
    patient = build_consistent_patient()

    req = AnalyzeContradictionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=[
            RetrievedChunk(
                chunk_id="CHK-MISMATCH",
                trial_id="WRONG-TRIAL-ID",
                criterion_id="INC-AGE",
                criterion_type="inclusion",
                text="Age >= 18 years",
                score=0.9,
                source_page=2,
                source_document="protocol.pdf",
            )
        ],
    )

    response = client.post("/api/v1/contradiction/analyze", json=req.model_dump())
    assert response.status_code == 400
    assert "Trial isolation violation" in response.json()["detail"]
