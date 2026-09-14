"""Comprehensive tests for the Inclusion Matching Agent.

Tests cover:
- Case 1: Complete PASS
- Case 2: Inclusion FAIL
- Case 3: Missing information (UNKNOWN)
- Case 4: False preservation (False != missing)
- Case 5: Zero preservation (0 != missing)
- Case 6: Trial isolation (SYN-ONC-001 vs SYN-PULM-002)
- Case 7: Cross-trial evidence rejection (TrialIsolationError)
- Case 8: Exclusion criterion rejection (CriterionTypeError)
- Numerical operators: >=, >, <=, <, inclusive ranges, exact values
- Clinical domains: age, eGFR, ECOG, FEV1, FEV1/FVC, CAT score, pack-years, ANC, Platelets, BP
- No medical inference on undocumented diagnoses
- Full traceability on every criterion assessment
- FastAPI router endpoint POST /api/v1/inclusion/evaluate
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.inclusion_matching_agent import (
    CriterionTypeError,
    InclusionMatchingAgent,
    TrialIsolationError,
)
from app.main import app
from app.schemas.inclusion import (
    EvaluateInclusionRequest,
    InclusionAssessment,
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
    VitalSigns,
    BloodPressure,
)
from app.schemas.rag import RetrievedChunk


# =============================================================================
# Helper Fixtures
# =============================================================================

def build_oncology_patient() -> PatientProfile:
    """Builds synthetic patient for oncology trial evaluation."""
    return PatientProfile(
        patient_profile_id="PAT-ONC-001",
        demographics=Demographics(
            age=52,
            pregnancy_status=PregnancyStatus.NOT_PREGNANT,
            breastfeeding_status=False,
        ),
        clinical_status=ClinicalStatus(
            ecog_performance_status=1,
            active_serious_infection=False,
            uncontrolled_cardiac_disease=False,
        ),
        labs=Labs(
            egfr=LabValue(value=68.0, unit="mL/min/1.73m2"),
            anc=LabValue(value=2.4, unit="x10^9/L"),
            platelets=LabValue(value=180.0, unit="x10^9/L"),
            hemoglobin=LabValue(value=11.2, unit="g/dL"),
            bilirubin=LabValue(value=0.8, unit="mg/dL"),
            ast=LabValue(value=22.0, unit="U/L"),
            alt=LabValue(value=24.0, unit="U/L"),
        ),
        conditions=[
            ConditionItem(name="Advanced Solid Tumor (NSCLC)", status="active", documented=True),
            ConditionItem(name="Hypertension", status="active", documented=True),
        ],
    )


def build_oncology_chunks() -> list[RetrievedChunk]:
    """Builds inclusion criteria chunks for SYN-ONC-001."""
    return [
        RetrievedChunk(
            chunk_id="CHK-ONC-001",
            trial_id="SYN-ONC-001",
            criterion_id="INC-001",
            criterion_type="inclusion",
            text="Age >= 18 years at the time of signing informed consent.",
            score=0.92,
            source_page=3,
            source_document="oncology_protocol.pdf",
            source_excerpt="Age >= 18 years",
        ),
        RetrievedChunk(
            chunk_id="CHK-ONC-002",
            trial_id="SYN-ONC-001",
            criterion_id="INC-002",
            criterion_type="inclusion",
            text="Histologically or cytologically confirmed advanced solid tumor.",
            score=0.90,
            source_page=3,
            source_document="oncology_protocol.pdf",
            source_excerpt="confirmed advanced solid tumor",
        ),
        RetrievedChunk(
            chunk_id="CHK-ONC-003",
            trial_id="SYN-ONC-001",
            criterion_id="INC-003",
            criterion_type="inclusion",
            text="ECOG performance status 0-1.",
            score=0.88,
            source_page=4,
            source_document="oncology_protocol.pdf",
            source_excerpt="ECOG performance status 0-1",
        ),
        RetrievedChunk(
            chunk_id="CHK-ONC-004",
            trial_id="SYN-ONC-001",
            criterion_id="INC-004",
            criterion_type="inclusion",
            text="Adequate renal function: eGFR >= 30 mL/min/1.73m2.",
            score=0.85,
            source_page=4,
            source_document="oncology_protocol.pdf",
            source_excerpt="eGFR >= 30 mL/min/1.73m2",
        ),
    ]


def build_pulmonary_chunks() -> list[RetrievedChunk]:
    """Builds inclusion criteria chunks for SYN-PULM-002."""
    return [
        RetrievedChunk(
            chunk_id="CHK-PULM-001",
            trial_id="SYN-PULM-002",
            criterion_id="INC-P01",
            criterion_type="inclusion",
            text="Age between 40 and 80 years inclusive.",
            score=0.91,
            source_page=5,
            source_document="pulmonary_protocol.pdf",
            source_excerpt="Age between 40 and 80",
        ),
        RetrievedChunk(
            chunk_id="CHK-PULM-002",
            trial_id="SYN-PULM-002",
            criterion_id="INC-P02",
            criterion_type="inclusion",
            text="Documented diagnosis of COPD according to GOLD criteria.",
            score=0.89,
            source_page=5,
            source_document="pulmonary_protocol.pdf",
            source_excerpt="diagnosis of COPD",
        ),
        RetrievedChunk(
            chunk_id="CHK-PULM-003",
            trial_id="SYN-PULM-002",
            criterion_id="INC-P03",
            criterion_type="inclusion",
            text="Post-bronchodilator FEV1/FVC < 0.70.",
            score=0.87,
            source_page=5,
            source_document="pulmonary_protocol.pdf",
            source_excerpt="FEV1/FVC < 0.70",
        ),
        RetrievedChunk(
            chunk_id="CHK-PULM-004",
            trial_id="SYN-PULM-002",
            criterion_id="INC-P04",
            criterion_type="inclusion",
            text="Post-bronchodilator FEV1 30-80% predicted.",
            score=0.84,
            source_page=6,
            source_document="pulmonary_protocol.pdf",
            source_excerpt="FEV1 30-80% predicted",
        ),
    ]


# =============================================================================
# Core Specification Tests (Cases 1 to 8)
# =============================================================================

@pytest.mark.asyncio
async def test_case_1_complete_pass():
    """Case 1: Complete PASS when all inclusion criteria are satisfied."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    evidence = build_oncology_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.trial_id == "SYN-ONC-001"
    assert result.patient_profile_id == "PAT-ONC-001"
    assert result.overall_status == InclusionStatus.PASS
    assert len(result.criteria) == 4
    for c in result.criteria:
        assert c.status == InclusionStatus.PASS
    assert len(result.missing_information) == 0


@pytest.mark.asyncio
async def test_case_2_inclusion_fail():
    """Case 2: Inclusion FAIL when ECOG exceeds threshold (ECOG=2 vs required 0-1)."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    patient.clinical_status.ecog_performance_status = 2
    evidence = build_oncology_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == InclusionStatus.FAIL
    ecog_crit = next(c for c in result.criteria if c.criterion_id == "INC-003")
    assert ecog_crit.status == InclusionStatus.FAIL
    assert ecog_crit.patient_value == 2
    assert "exceeds" in ecog_crit.rationale.lower()


@pytest.mark.asyncio
async def test_case_3_missing_information_yields_unknown():
    """Case 3: Missing required lab information (eGFR missing) yields UNKNOWN, never PASS or FAIL."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    patient.labs.egfr = None  # Missing eGFR
    evidence = build_oncology_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == InclusionStatus.UNKNOWN
    egfr_crit = next(c for c in result.criteria if c.criterion_id == "INC-004")
    assert egfr_crit.status == InclusionStatus.UNKNOWN
    assert egfr_crit.patient_value is None
    assert "labs.egfr" in result.missing_information


@pytest.mark.asyncio
async def test_case_4_false_preservation():
    """Case 4: Explicit False boolean is NOT treated as missing."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    patient.clinical_status.active_serious_infection = False

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INF-01",
            trial_id="SYN-ONC-001",
            criterion_id="INC-INF",
            criterion_type="inclusion",
            text="Patient must have no active serious infection (active serious infection = false).",
            score=0.9,
            source_page=4,
            source_document="protocol.pdf",
        )
    ]

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == InclusionStatus.PASS
    assert len(result.criteria) == 1
    assert result.criteria[0].status == InclusionStatus.PASS
    assert result.criteria[0].patient_value is False
    assert "clinical_status.active_serious_infection" not in result.missing_information


@pytest.mark.asyncio
async def test_case_5_zero_preservation():
    """Case 5: Explicit numeric 0 is NOT treated as missing."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    patient.clinical_status.ecog_performance_status = 0

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-ECOG-0",
            trial_id="SYN-ONC-001",
            criterion_id="INC-ECOG",
            criterion_type="inclusion",
            text="ECOG performance status 0-1.",
            score=0.95,
            source_page=4,
            source_document="protocol.pdf",
        )
    ]

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == InclusionStatus.PASS
    assert result.criteria[0].status == InclusionStatus.PASS
    assert result.criteria[0].patient_value == 0
    assert "clinical_status.ecog_performance_status" not in result.missing_information


@pytest.mark.asyncio
async def test_case_6_trial_isolation_selected_trial_controls():
    """Case 6: Same patient evaluated against oncology vs pulmonary receives trial-specific evaluation."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    onc_evidence = build_oncology_chunks()
    pulm_evidence = build_pulmonary_chunks()

    # Oncology evaluation
    onc_result = await agent.evaluate("SYN-ONC-001", patient, onc_evidence)
    assert onc_result.trial_id == "SYN-ONC-001"
    assert {c.criterion_id for c in onc_result.criteria} == {"INC-001", "INC-002", "INC-003", "INC-004"}
    assert onc_result.overall_status == InclusionStatus.PASS

    # Pulmonary evaluation for same patient (patient does NOT have documented COPD or spirometry)
    pulm_result = await agent.evaluate("SYN-PULM-002", patient, pulm_evidence)
    assert pulm_result.trial_id == "SYN-PULM-002"
    assert {c.criterion_id for c in pulm_result.criteria} == {"INC-P01", "INC-P02", "INC-P03", "INC-P04"}
    # Missing COPD diagnosis and missing FEV1 spirometry yields UNKNOWN
    assert pulm_result.overall_status == InclusionStatus.UNKNOWN


@pytest.mark.asyncio
async def test_case_7_cross_trial_evidence_rejection():
    """Case 7: Agent rejects evidence containing mismatched trial_id (TrialIsolationError)."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    evidence = build_oncology_chunks()

    # Inject a pulmonary chunk into an oncology evaluation
    evidence.append(
        RetrievedChunk(
            chunk_id="CHK-MISMATCH",
            trial_id="SYN-PULM-002",  # Mismatched!
            criterion_id="INC-P99",
            criterion_type="inclusion",
            text="FEV1/FVC < 0.70",
            score=0.8,
            source_page=5,
            source_document="pulm.pdf",
        )
    )

    with pytest.raises(TrialIsolationError) as exc_info:
        await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert "Trial isolation violation" in str(exc_info.value)
    assert "SYN-PULM-002" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_8_exclusion_criterion_rejection():
    """Case 8: Agent rejects exclusion criteria (CriterionTypeError)."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()

    exclusion_chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",  # Invalid for inclusion agent!
        text="Prior chemotherapy within 14 days.",
        score=0.85,
        source_page=7,
        source_document="oncology_protocol.pdf",
    )

    with pytest.raises(CriterionTypeError) as exc_info:
        await agent.evaluate("SYN-ONC-001", patient, [exclusion_chunk])

    assert "Criterion type validation error" in str(exc_info.value)
    assert "exclusion" in str(exc_info.value)


# =============================================================================
# Numerical Operator Tests
# =============================================================================

@pytest.mark.asyncio
async def test_numerical_gte_operator():
    """Test >= operator (18 passes, 17 fails)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-AGE",
        trial_id="T1",
        criterion_id="INC-AGE",
        criterion_type="inclusion",
        text="Age >= 18",
        score=1.0,
        source_page=1,
        source_document="p.pdf",
    )

    # 18 -> PASS
    p1 = PatientProfile(patient_profile_id="P1", demographics=Demographics(age=18))
    res1 = await agent.evaluate("T1", p1, [chunk])
    assert res1.overall_status == InclusionStatus.PASS

    # 17 -> FAIL
    p2 = PatientProfile(patient_profile_id="P2", demographics=Demographics(age=17))
    res2 = await agent.evaluate("T1", p2, [chunk])
    assert res2.overall_status == InclusionStatus.FAIL


@pytest.mark.asyncio
async def test_numerical_gt_operator():
    """Test > operator (18 fails, 19 passes)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-AGE",
        trial_id="T1",
        criterion_id="INC-AGE",
        criterion_type="inclusion",
        text="Age > 18 years",
        score=1.0,
        source_page=1,
        source_document="p.pdf",
    )

    p1 = PatientProfile(patient_profile_id="P1", demographics=Demographics(age=18))
    res1 = await agent.evaluate("T1", p1, [chunk])
    assert res1.overall_status == InclusionStatus.FAIL

    p2 = PatientProfile(patient_profile_id="P2", demographics=Demographics(age=19))
    res2 = await agent.evaluate("T1", p2, [chunk])
    assert res2.overall_status == InclusionStatus.PASS


@pytest.mark.asyncio
async def test_numerical_lte_operator():
    """Test <= operator (80 passes, 81 fails)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-AGE",
        trial_id="T1",
        criterion_id="INC-AGE",
        criterion_type="inclusion",
        text="Age <= 80 years",
        score=1.0,
        source_page=1,
        source_document="p.pdf",
    )

    p1 = PatientProfile(patient_profile_id="P1", demographics=Demographics(age=80))
    res1 = await agent.evaluate("T1", p1, [chunk])
    assert res1.overall_status == InclusionStatus.PASS

    p2 = PatientProfile(patient_profile_id="P2", demographics=Demographics(age=81))
    res2 = await agent.evaluate("T1", p2, [chunk])
    assert res2.overall_status == InclusionStatus.FAIL


@pytest.mark.asyncio
async def test_numerical_lt_operator():
    """Test < operator (FEV1/FVC < 0.70: 0.65 passes, 0.70 fails)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-PULM",
        trial_id="T1",
        criterion_id="INC-RATIO",
        criterion_type="inclusion",
        text="FEV1/FVC < 0.70",
        score=1.0,
        source_page=1,
        source_document="p.pdf",
    )

    p1 = PatientProfile(
        patient_profile_id="P1",
        labs=Labs(other_labs={"fev1_fvc": LabValue(value=0.65)}),
    )
    res1 = await agent.evaluate("T1", p1, [chunk])
    assert res1.overall_status == InclusionStatus.PASS

    p2 = PatientProfile(
        patient_profile_id="P2",
        labs=Labs(other_labs={"fev1_fvc": LabValue(value=0.70)}),
    )
    res2 = await agent.evaluate("T1", p2, [chunk])
    assert res2.overall_status == InclusionStatus.FAIL


@pytest.mark.asyncio
async def test_numerical_inclusive_range():
    """Test inclusive range 40-80 (35 fails, 40 passes, 65 passes, 80 passes, 85 fails)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-RANGE",
        trial_id="T1",
        criterion_id="INC-RANGE",
        criterion_type="inclusion",
        text="Age 40-80 years",
        score=1.0,
        source_page=1,
        source_document="p.pdf",
    )

    for age, expected in [(35, InclusionStatus.FAIL), (40, InclusionStatus.PASS), (65, InclusionStatus.PASS), (80, InclusionStatus.PASS), (85, InclusionStatus.FAIL)]:
        p = PatientProfile(patient_profile_id=f"P-{age}", demographics=Demographics(age=age))
        res = await agent.evaluate("T1", p, [chunk])
        assert res.overall_status == expected, f"Failed for age={age}"


# =============================================================================
# Specific Clinical Domains & Evidence Traceability
# =============================================================================

@pytest.mark.asyncio
async def test_hematology_thresholds_anc_and_platelets():
    """Test ANC and platelet criteria."""
    agent = InclusionMatchingAgent()
    chunks = [
        RetrievedChunk(
            chunk_id="CHK-ANC",
            trial_id="T1",
            criterion_id="INC-ANC",
            criterion_type="inclusion",
            text="ANC >= 1.5 x 10^9/L",
            score=0.9,
            source_page=2,
            source_document="doc.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-PLT",
            trial_id="T1",
            criterion_id="INC-PLT",
            criterion_type="inclusion",
            text="Platelets >= 100,000 /mcL",
            score=0.9,
            source_page=2,
            source_document="doc.pdf",
        ),
    ]

    # Passing patient (ANC 1.8, Plt 150)
    p_pass = PatientProfile(
        patient_profile_id="P-HEM-1",
        labs=Labs(
            anc=LabValue(value=1.8),
            platelets=LabValue(value=150.0),
        ),
    )
    res_pass = await agent.evaluate("T1", p_pass, chunks)
    assert res_pass.overall_status == InclusionStatus.PASS

    # Failing patient (ANC 1.1)
    p_fail = PatientProfile(
        patient_profile_id="P-HEM-2",
        labs=Labs(
            anc=LabValue(value=1.1),
            platelets=LabValue(value=150.0),
        ),
    )
    res_fail = await agent.evaluate("T1", p_fail, chunks)
    assert res_fail.overall_status == InclusionStatus.FAIL


@pytest.mark.asyncio
async def test_pulmonary_cat_score_and_pack_years():
    """Test CAT score and smoking pack-years."""
    agent = InclusionMatchingAgent()
    chunks = [
        RetrievedChunk(
            chunk_id="CHK-CAT",
            trial_id="PULM-1",
            criterion_id="INC-CAT",
            criterion_type="inclusion",
            text="CAT score >= 10",
            score=0.9,
            source_page=3,
            source_document="pulm.pdf",
        ),
        RetrievedChunk(
            chunk_id="CHK-PACK",
            trial_id="PULM-1",
            criterion_id="INC-PACK",
            criterion_type="inclusion",
            text="Smoking history >= 10 pack-years",
            score=0.9,
            source_page=3,
            source_document="pulm.pdf",
        ),
    ]

    p = PatientProfile(
        patient_profile_id="P-PULM",
        labs=Labs(
            other_labs={
                "cat_score": LabValue(value=14.0),
                "pack_years": LabValue(value=25.0),
            }
        ),
    )
    res = await agent.evaluate("PULM-1", p, chunks)
    assert res.overall_status == InclusionStatus.PASS


@pytest.mark.asyncio
async def test_cardiac_and_infection_boolean_criteria():
    """Test boolean cardiac status and infection requirements."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-CARD",
        trial_id="T1",
        criterion_id="INC-CARD",
        criterion_type="inclusion",
        text="No uncontrolled cardiac disease",
        score=0.9,
        source_page=4,
        source_document="doc.pdf",
    )

    # Patient with uncontrolled cardiac disease (True) fails
    p_fail = PatientProfile(
        patient_profile_id="P-CARD-1",
        clinical_status=ClinicalStatus(uncontrolled_cardiac_disease=True),
    )
    res_fail = await agent.evaluate("T1", p_fail, [chunk])
    assert res_fail.overall_status == InclusionStatus.FAIL

    # Patient with no uncontrolled cardiac disease (False) passes
    p_pass = PatientProfile(
        patient_profile_id="P-CARD-2",
        clinical_status=ClinicalStatus(uncontrolled_cardiac_disease=False),
    )
    res_pass = await agent.evaluate("T1", p_pass, [chunk])
    assert res_pass.overall_status == InclusionStatus.PASS


@pytest.mark.asyncio
async def test_vital_signs_blood_pressure():
    """Test blood pressure evaluation (systolic <= 140 mmHg)."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-BP",
        trial_id="T1",
        criterion_id="INC-BP",
        criterion_type="inclusion",
        text="Blood pressure systolic <= 140 mmHg",
        score=0.9,
        source_page=2,
        source_document="doc.pdf",
    )

    p_pass = PatientProfile(
        patient_profile_id="P-BP-1",
        vital_signs=VitalSigns(blood_pressure=BloodPressure(systolic=120, diastolic=80)),
    )
    res_pass = await agent.evaluate("T1", p_pass, [chunk])
    assert res_pass.overall_status == InclusionStatus.PASS

    p_fail = PatientProfile(
        patient_profile_id="P-BP-2",
        vital_signs=VitalSigns(blood_pressure=BloodPressure(systolic=150, diastolic=95)),
    )
    res_fail = await agent.evaluate("T1", p_fail, [chunk])
    assert res_fail.overall_status == InclusionStatus.FAIL


@pytest.mark.asyncio
async def test_no_medical_inference_for_undocumented_diagnoses():
    """Verify that absent condition documentation produces UNKNOWN, not FAIL, and no inference from spirometry."""
    agent = InclusionMatchingAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-COPD",
        trial_id="T-PULM",
        criterion_id="INC-COPD",
        criterion_type="inclusion",
        text="Must have documented diagnosis of COPD",
        score=0.9,
        source_page=1,
        source_document="doc.pdf",
    )

    # Patient has low FEV1/FVC (< 0.70) but NO documented condition of COPD
    patient = PatientProfile(
        patient_profile_id="P-NO-COPD",
        conditions=[],  # Empty conditions
        labs=Labs(other_labs={"fev1_fvc": LabValue(value=0.58)}),
    )

    result = await agent.evaluate("T-PULM", patient, [chunk])
    assert result.overall_status == InclusionStatus.UNKNOWN
    assert result.criteria[0].status == InclusionStatus.UNKNOWN
    assert "conditions.COPD" in result.missing_information


@pytest.mark.asyncio
async def test_traceability_fields_fully_populated():
    """Verify all 6 traceability items are populated on each assessment."""
    agent = InclusionMatchingAgent()
    patient = build_oncology_patient()
    chunk = RetrievedChunk(
        chunk_id="CHK-TRACE",
        trial_id="SYN-ONC-001",
        criterion_id="INC-TRACE",
        criterion_type="inclusion",
        text="eGFR >= 30 mL/min/1.73m2",
        score=0.95,
        source_page=4,
        source_document="oncology_protocol.pdf",
        source_excerpt="eGFR >= 30 mL/min/1.73m2",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])
    crit = result.criteria[0]

    assert crit.criterion_id == "INC-TRACE"
    assert crit.trial_id == "SYN-ONC-001"
    assert crit.criterion_text == "eGFR >= 30 mL/min/1.73m2"
    assert crit.patient_value == 68.0
    assert crit.expected_requirement == ">= 30.0"
    assert crit.status == InclusionStatus.PASS
    assert "satisfies" in crit.rationale.lower()
    assert crit.source_page == 4
    assert crit.source_document == "oncology_protocol.pdf"
    assert crit.source_excerpt == "eGFR >= 30 mL/min/1.73m2"


# =============================================================================
# FastAPI Endpoint Integration Tests (POST /api/v1/inclusion/evaluate)
# =============================================================================

def test_api_evaluate_inclusion_success():
    """Test API endpoint POST /api/v1/inclusion/evaluate with valid request."""
    client = TestClient(app)
    patient = build_oncology_patient()
    evidence = build_oncology_chunks()

    req = EvaluateInclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/inclusion/evaluate", json=req.model_dump())
    assert response.status_code == 200

    data = response.json()
    assert data["trial_id"] == "SYN-ONC-001"
    assert data["patient_profile_id"] == "PAT-ONC-001"
    assert data["overall_status"] == "PASS"
    assert len(data["criteria"]) == 4


def test_api_evaluate_inclusion_cross_trial_returns_400():
    """Test API endpoint returns 400 Bad Request when cross-trial evidence is sent."""
    client = TestClient(app)
    patient = build_oncology_patient()
    evidence = build_oncology_chunks()
    # Mismatch trial ID on one chunk
    evidence[0].trial_id = "WRONG-TRIAL-999"

    req = EvaluateInclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/inclusion/evaluate", json=req.model_dump())
    assert response.status_code == 400
    assert "Trial isolation violation" in response.json()["detail"]


def test_api_evaluate_inclusion_exclusion_criterion_returns_400():
    """Test API endpoint returns 400 when an exclusion criterion is passed."""
    client = TestClient(app)
    patient = build_oncology_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-01",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-001",
            criterion_type="exclusion",
            text="Active CNS metastasis",
            score=0.8,
            source_page=5,
            source_document="p.pdf",
        )
    ]

    req = EvaluateInclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/inclusion/evaluate", json=req.model_dump())
    assert response.status_code == 400
    assert "Criterion type validation error" in response.json()["detail"]


def test_api_evaluate_inclusion_empty_trial_id_returns_422():
    """Test API endpoint returns 422 for empty trial_id via Pydantic validation."""
    client = TestClient(app)
    patient = build_oncology_patient()
    evidence = build_oncology_chunks()

    payload = {
        "trial_id": "",
        "patient_profile": patient.model_dump(),
        "retrieved_evidence": [e.model_dump() for e in evidence],
    }

    response = client.post("/api/v1/inclusion/evaluate", json=payload)
    assert response.status_code in (400, 422)
