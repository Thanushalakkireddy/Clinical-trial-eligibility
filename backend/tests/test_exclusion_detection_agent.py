"""Comprehensive test suite for the Exclusion Detection Agent.

Tests cover all 22 required cases:
- Case 1: All exclusions CLEAR
- Case 2: Renal exclusion triggered (eGFR < 30, value = 20)
- Case 3: Renal exclusion clear (eGFR < 30, value = 68)
- Case 4: Missing eGFR yields UNKNOWN (never CLEAR)
- Case 5: Active infection True -> TRIGGERED
- Case 6: Active infection False -> CLEAR
- Case 7: Active infection None -> UNKNOWN
- Case 8: False preservation
- Case 9: Zero preservation (ECOG = 0)
- Case 10: Missing diagnosis -> UNKNOWN (not CLEAR)
- Case 11: Documented condition (Asthma) -> TRIGGERED
- Case 12: Cross-trial evidence rejection (TrialIsolationError)
- Case 13: Inclusion criterion supplied rejection (CriterionTypeError)
- Case 14: Multiple exclusions (One triggered + several clear -> TRIGGERED)
- Case 15: Multiple unknowns (No triggered + >=1 unknown -> UNKNOWN)
- Case 16: All clear -> CLEAR
- Case 17: Temporal exclusion triggered (within 12 months)
- Case 18: Temporal exclusion clear (outside 12 months)
- Case 19: Temporal date missing -> UNKNOWN
- Case 20: Boundary condition (< 30 with value 30 -> CLEAR)
- Case 21: Strict boundary (<= 30 with value 30 -> TRIGGERED)
- Case 22: Provenance preservation
- Additional API tests for POST /api/v1/exclusion/evaluate
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient

from app.agents.exclusion_detection_agent import (
    CriterionTypeError,
    ExclusionDetectionAgent,
    TrialIsolationError,
)
from app.main import app
from app.schemas.exclusion import (
    EvaluateExclusionRequest,
    ExclusionAssessment,
    ExclusionStatus,
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
    VitalSigns,
    BloodPressure,
)
from app.schemas.rag import RetrievedChunk


# =============================================================================
# Helper Fixtures
# =============================================================================

def build_clear_patient() -> PatientProfile:
    """Builds a patient that is CLEAR of standard oncology exclusion criteria."""
    return PatientProfile(
        patient_profile_id="PAT-CLEAR-001",
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
        ],
        treatment_history=TreatmentHistory(
            recent_systemic_anticancer_therapy=False,
            last_treatment_date="2025-01-10",
        ),
    )


def build_standard_exclusion_chunks() -> list[RetrievedChunk]:
    """Builds 3 standard protocol exclusion chunks for SYN-ONC-001."""
    return [
        RetrievedChunk(
            chunk_id="CHK-EXC-001",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-001",
            criterion_type="exclusion",
            text="eGFR < 30 mL/min/1.73m2",
            score=0.92,
            source_page=5,
            source_document="oncology_protocol.pdf",
            source_excerpt="eGFR < 30 mL/min/1.73m2",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-002",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-002",
            criterion_type="exclusion",
            text="Active serious infection",
            score=0.90,
            source_page=5,
            source_document="oncology_protocol.pdf",
            source_excerpt="Active serious infection",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-003",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-003",
            criterion_type="exclusion",
            text="Uncontrolled cardiac disease",
            score=0.88,
            source_page=5,
            source_document="oncology_protocol.pdf",
            source_excerpt="Uncontrolled cardiac disease",
        ),
    ]


# =============================================================================
# Test Cases 1 to 22
# =============================================================================

@pytest.mark.asyncio
async def test_case_1_all_exclusions_clear():
    """Case 1: All relevant exclusions are CLEAR -> Overall CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    evidence = build_standard_exclusion_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.trial_id == "SYN-ONC-001"
    assert result.patient_profile_id == "PAT-CLEAR-001"
    assert result.overall_status == ExclusionStatus.CLEAR
    assert len(result.criteria) == 3
    for c in result.criteria:
        assert c.status == ExclusionStatus.CLEAR


@pytest.mark.asyncio
async def test_case_2_renal_exclusion_triggered():
    """Case 2: eGFR < 30 with patient eGFR = 20 -> TRIGGERED."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr.value = 20.0
    evidence = build_standard_exclusion_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == ExclusionStatus.TRIGGERED
    egfr_crit = next(c for c in result.criteria if c.criterion_id == "EXC-001")
    assert egfr_crit.status == ExclusionStatus.TRIGGERED
    assert egfr_crit.patient_value == 20.0
    assert "< 30" in egfr_crit.exclusion_requirement


@pytest.mark.asyncio
async def test_case_3_renal_exclusion_clear():
    """Case 3: eGFR < 30 with patient eGFR = 68 -> CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr.value = 68.0
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",
        text="eGFR < 30 mL/min/1.73m2",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert result.criteria[0].patient_value == 68.0


@pytest.mark.asyncio
async def test_case_4_missing_egfr():
    """Case 4: Patient eGFR is missing -> UNKNOWN (never CLEAR)."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr = None
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",
        text="eGFR < 30 mL/min/1.73m2",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.UNKNOWN
    assert result.criteria[0].status == ExclusionStatus.UNKNOWN
    assert result.criteria[0].patient_value is None
    assert "labs.egfr" in result.missing_information


@pytest.mark.asyncio
async def test_case_5_active_infection_true():
    """Case 5: active_serious_infection = True -> TRIGGERED."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = True
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-002",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-002",
        criterion_type="exclusion",
        text="Active serious infection",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].patient_value is True


@pytest.mark.asyncio
async def test_case_6_active_infection_false():
    """Case 6: active_serious_infection = False -> CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = False
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-002",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-002",
        criterion_type="exclusion",
        text="Active serious infection",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert result.criteria[0].patient_value is False


@pytest.mark.asyncio
async def test_case_7_active_infection_missing():
    """Case 7: active_serious_infection = None -> UNKNOWN."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = None
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-002",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-002",
        criterion_type="exclusion",
        text="Active serious infection",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.UNKNOWN
    assert result.criteria[0].status == ExclusionStatus.UNKNOWN
    assert "clinical_status.active_serious_infection" in result.missing_information


@pytest.mark.asyncio
async def test_case_8_false_preservation():
    """Case 8: Explicit False boolean remains valid and produces CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.demographics.breastfeeding_status = False
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-BF",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-BF",
        criterion_type="exclusion",
        text="Breastfeeding patients are excluded.",
        score=0.9,
        source_page=6,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert result.criteria[0].patient_value is False


@pytest.mark.asyncio
async def test_case_9_zero_preservation():
    """Case 9: Explicit numeric 0 is not treated as missing."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.ecog_performance_status = 0
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-ECOG",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-ECOG",
        criterion_type="exclusion",
        text="ECOG performance status >= 2.",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert result.criteria[0].patient_value == 0


@pytest.mark.asyncio
async def test_case_10_missing_diagnosis_yields_unknown():
    """Case 10: Exclusion 'Asthma' when patient has no documented asthma status -> UNKNOWN, not CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.conditions = []  # No conditions documented
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-ASTHMA",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-ASTHMA",
        criterion_type="exclusion",
        text="History of asthma or active asthma",
        score=0.9,
        source_page=7,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.UNKNOWN
    assert result.criteria[0].status == ExclusionStatus.UNKNOWN
    assert "conditions.asthma" in result.missing_information


@pytest.mark.asyncio
async def test_case_11_documented_asthma():
    """Case 11: Documented asthma -> TRIGGERED."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.conditions.append(
        ConditionItem(name="Moderate Persistent Asthma", status="active", documented=True)
    )
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-ASTHMA",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-ASTHMA",
        criterion_type="exclusion",
        text="History of asthma",
        score=0.9,
        source_page=7,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].status == ExclusionStatus.TRIGGERED
    assert "Moderate Persistent Asthma" in str(result.criteria[0].patient_value)


@pytest.mark.asyncio
async def test_case_12_cross_trial_evidence_rejected():
    """Case 12: Evidence belonging to mismatched trial raises TrialIsolationError."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EXC-MISMATCH",
            trial_id="SYN-PULM-002",  # Mismatched from SYN-ONC-001
            criterion_id="EXC-001",
            criterion_type="exclusion",
            text="Active hemoptysis",
            score=0.9,
            source_page=5,
            source_document="doc.pdf",
        )
    ]

    with pytest.raises(TrialIsolationError) as exc_info:
        await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert "Trial isolation violation" in str(exc_info.value)
    assert "SYN-PULM-002" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_13_inclusion_criterion_supplied_rejected():
    """Case 13: Inclusion criterion passed to exclusion agent raises CriterionTypeError."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-001",
            trial_id="SYN-ONC-001",
            criterion_id="INC-001",
            criterion_type="inclusion",  # Invalid type!
            text="Age >= 18",
            score=0.9,
            source_page=3,
            source_document="doc.pdf",
        )
    ]

    with pytest.raises(CriterionTypeError) as exc_info:
        await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert "Criterion type validation error" in str(exc_info.value)
    assert "inclusion" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_14_multiple_exclusions_one_triggered():
    """Case 14: One triggered + several clear -> Overall TRIGGERED."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    # Infection is True -> Triggered
    patient.clinical_status.active_serious_infection = True
    evidence = build_standard_exclusion_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == ExclusionStatus.TRIGGERED
    statuses = [c.status for c in result.criteria]
    assert ExclusionStatus.TRIGGERED in statuses
    assert ExclusionStatus.CLEAR in statuses


@pytest.mark.asyncio
async def test_case_15_multiple_unknowns():
    """Case 15: No triggered criteria + at least one unknown -> Overall UNKNOWN."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr = None  # UNKNOWN
    patient.clinical_status.active_serious_infection = False  # CLEAR
    patient.clinical_status.uncontrolled_cardiac_disease = False  # CLEAR
    evidence = build_standard_exclusion_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == ExclusionStatus.UNKNOWN
    statuses = [c.status for c in result.criteria]
    assert ExclusionStatus.TRIGGERED not in statuses
    assert ExclusionStatus.UNKNOWN in statuses


@pytest.mark.asyncio
async def test_case_16_all_clear():
    """Case 16: All clear -> Overall CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    evidence = build_standard_exclusion_chunks()

    result = await agent.evaluate("SYN-ONC-001", patient, evidence)

    assert result.overall_status == ExclusionStatus.CLEAR
    for c in result.criteria:
        assert c.status == ExclusionStatus.CLEAR


@pytest.mark.asyncio
async def test_case_17_temporal_exclusion_triggered():
    """Case 17: Stroke within 12 months. Event date is ~6 months prior -> TRIGGERED."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.conditions.append(
        ConditionItem(
            name="Ischemic Stroke",
            status="active",
            documented=True,
            source_provenance="Diagnosis date: 2026-03-01",
        )
    )
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-STROKE",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-STROKE",
        criterion_type="exclusion",
        text="History of stroke or TIA within 12 months.",
        score=0.9,
        source_page=6,
        source_document="doc.pdf",
    )

    result = await agent.evaluate(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=[chunk],
        reference_date="2026-09-14",
    )

    assert result.overall_status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].status == ExclusionStatus.TRIGGERED
    assert "within the" in result.criteria[0].rationale


@pytest.mark.asyncio
async def test_case_18_temporal_exclusion_clear():
    """Case 18: Stroke outside required window (event date 2024-01-15 vs 12 month window) -> CLEAR."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.conditions.append(
        ConditionItem(
            name="Ischemic Stroke",
            status="historical",
            documented=True,
            source_provenance="Diagnosis date: 2024-01-15",
        )
    )
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-STROKE",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-STROKE",
        criterion_type="exclusion",
        text="History of stroke or TIA within 12 months.",
        score=0.9,
        source_page=6,
        source_document="doc.pdf",
    )

    result = await agent.evaluate(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=[chunk],
        reference_date="2026-09-14",
    )

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert "safely outside" in result.criteria[0].rationale


@pytest.mark.asyncio
async def test_case_19_temporal_date_missing():
    """Case 19: Stroke documented, but date is missing -> UNKNOWN."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.conditions.append(
        ConditionItem(
            name="Ischemic Stroke",
            status="active",
            documented=True,
            source_provenance=None,  # No date
        )
    )
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-STROKE",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-STROKE",
        criterion_type="exclusion",
        text="History of stroke or TIA within 12 months.",
        score=0.9,
        source_page=6,
        source_document="doc.pdf",
    )

    result = await agent.evaluate(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=[chunk],
        reference_date="2026-09-14",
    )

    assert result.overall_status == ExclusionStatus.UNKNOWN
    assert result.criteria[0].status == ExclusionStatus.UNKNOWN
    assert "event date is missing" in result.criteria[0].rationale.lower()


@pytest.mark.asyncio
async def test_case_20_boundary_condition_strict_lt():
    """Case 20: Exclusion eGFR < 30. Patient eGFR = 30 -> CLEAR (30 is not < 30)."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr.value = 30.0
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",
        text="eGFR < 30 mL/min/1.73m2",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.CLEAR
    assert result.criteria[0].status == ExclusionStatus.CLEAR
    assert result.criteria[0].patient_value == 30.0


@pytest.mark.asyncio
async def test_case_21_boundary_condition_lte():
    """Case 21: Exclusion eGFR <= 30. Patient eGFR = 30 -> TRIGGERED (30 <= 30)."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.labs.egfr.value = 30.0
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",
        text="eGFR <= 30 mL/min/1.73m2",
        score=0.9,
        source_page=5,
        source_document="doc.pdf",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    assert result.overall_status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].status == ExclusionStatus.TRIGGERED
    assert result.criteria[0].patient_value == 30.0


@pytest.mark.asyncio
async def test_case_22_provenance_preservation():
    """Case 22: Provenance fields (source_page, source_document, source_excerpt) survive pipeline."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-001",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-001",
        criterion_type="exclusion",
        text="eGFR < 30 mL/min/1.73m2",
        score=0.92,
        source_page=9,
        source_document="protocol_rev4.pdf",
        source_excerpt="Exclusion criterion: eGFR < 30",
    )

    result = await agent.evaluate("SYN-ONC-001", patient, [chunk])

    crit = result.criteria[0]
    assert crit.criterion_id == "EXC-001"
    assert crit.source_page == 9
    assert crit.source_document == "protocol_rev4.pdf"
    assert crit.source_excerpt == "Exclusion criterion: eGFR < 30"
    assert crit.trial_id == "SYN-ONC-001"


# =============================================================================
# Additional Clinical Operator & API Tests
# =============================================================================

@pytest.mark.asyncio
async def test_systemic_anticancer_therapy_temporal_exclusion():
    """Test anticancer therapy within 4 weeks (28 days)."""
    agent = ExclusionDetectionAgent()
    chunk = RetrievedChunk(
        chunk_id="CHK-EXC-CHEMO",
        trial_id="SYN-ONC-001",
        criterion_id="EXC-CHEMO",
        criterion_type="exclusion",
        text="Systemic anticancer therapy within 4 weeks",
        score=0.9,
        source_page=6,
        source_document="doc.pdf",
    )

    # 1. Patient treated 10 days ago -> TRIGGERED
    p1 = build_clear_patient()
    p1.treatment_history = TreatmentHistory(
        recent_systemic_anticancer_therapy=True,
        last_treatment_date="2026-09-04",
    )
    res1 = await agent.evaluate("SYN-ONC-001", p1, [chunk], reference_date="2026-09-14")
    assert res1.overall_status == ExclusionStatus.TRIGGERED

    # 2. Patient treated 45 days ago -> CLEAR
    p2 = build_clear_patient()
    p2.treatment_history = TreatmentHistory(
        recent_systemic_anticancer_therapy=True,
        last_treatment_date="2026-07-31",
    )
    res2 = await agent.evaluate("SYN-ONC-001", p2, [chunk], reference_date="2026-09-14")
    assert res2.overall_status == ExclusionStatus.CLEAR


def test_api_evaluate_exclusion_success():
    """Test FastAPI POST /api/v1/exclusion/evaluate endpoint."""
    client = TestClient(app)
    patient = build_clear_patient()
    evidence = build_standard_exclusion_chunks()

    req = EvaluateExclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/exclusion/evaluate", json=req.model_dump())
    assert response.status_code == 200

    data = response.json()
    assert data["trial_id"] == "SYN-ONC-001"
    assert data["patient_profile_id"] == "PAT-CLEAR-001"
    assert data["overall_status"] == "CLEAR"
    assert len(data["criteria"]) == 3


def test_api_evaluate_exclusion_mismatched_trial_returns_400():
    """Test API endpoint returns 400 when cross-trial evidence is passed."""
    client = TestClient(app)
    patient = build_clear_patient()
    evidence = build_standard_exclusion_chunks()
    evidence[0].trial_id = "WRONG-TRIAL"

    req = EvaluateExclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/exclusion/evaluate", json=req.model_dump())
    assert response.status_code == 400
    assert "Trial isolation violation" in response.json()["detail"]


def test_api_evaluate_exclusion_inclusion_criterion_returns_400():
    """Test API endpoint returns 400 when an inclusion criterion is passed to exclusion endpoint."""
    client = TestClient(app)
    patient = build_clear_patient()
    evidence = [
        RetrievedChunk(
            chunk_id="CHK-INC-01",
            trial_id="SYN-ONC-001",
            criterion_id="INC-001",
            criterion_type="inclusion",
            text="Age >= 18",
            score=0.9,
            source_page=3,
            source_document="doc.pdf",
        )
    ]

    req = EvaluateExclusionRequest(
        trial_id="SYN-ONC-001",
        patient_profile=patient,
        retrieved_evidence=evidence,
    )

    response = client.post("/api/v1/exclusion/evaluate", json=req.model_dump())
    assert response.status_code == 400
    assert "Criterion type validation error" in response.json()["detail"]


# =============================================================================
# Checkpoint 2A Regression Tests – EXC-002 / EXC-003 dispatch reorder
#
# These use the full SYN-ONC-001 protocol text which includes temporal phrases
# ("within 14 days", "within 6 months") that previously hijacked the routing
# before the clinical-status handler could be reached.
# =============================================================================

def _exc_realistic_chunks() -> list[RetrievedChunk]:
    """SYN-ONC-001 exclusion chunks with protocol-realistic text (includes temporal phrases)."""
    return [
        RetrievedChunk(
            chunk_id="CHK-EXC-002",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-002",
            criterion_type="exclusion",
            text=(
                "Patients with active serious infection requiring systemic antimicrobial "
                "therapy within 14 days prior to administration of study treatment will be excluded."
            ),
            score=0.90,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 2. Active serious infection",
        ),
        RetrievedChunk(
            chunk_id="CHK-EXC-003",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-003",
            criterion_type="exclusion",
            text=(
                "Patients with uncontrolled cardiac disease, including unstable angina, "
                "myocardial infarction, or clinically significant arrhythmia within "
                "6 months prior to enrollment, will be excluded."
            ),
            score=0.90,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 3. Uncontrolled cardiac disease",
        ),
    ]


# --- A. active_serious_infection = True  →  EXC-002 TRIGGERED ---

@pytest.mark.asyncio
async def test_exc002_infection_true_triggered():
    """EXC-002 (realistic text): infection=True -> TRIGGERED, NOT the temporal/anticancer handler."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = True

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc002 = next(c for c in result.criteria if c.criterion_id == "EXC-002")
    assert exc002.status == ExclusionStatus.TRIGGERED
    assert exc002.patient_value is True
    assert "active serious infection" in exc002.rationale.lower()
    assert "anticancer" not in exc002.rationale.lower()
    assert "conditions.temporal_event" not in result.missing_information


# --- B. active_serious_infection = False  →  EXC-002 CLEAR ---

@pytest.mark.asyncio
async def test_exc002_infection_false_clear():
    """EXC-002 (realistic text): infection=False -> CLEAR, NOT routed to anticancer therapy handler."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = False

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc002 = next(c for c in result.criteria if c.criterion_id == "EXC-002")
    assert exc002.status == ExclusionStatus.CLEAR
    assert exc002.patient_value is False
    assert "no active serious infection" in exc002.rationale.lower()
    assert "recent systemic anticancer" not in exc002.rationale.lower()


# --- C. active_serious_infection = None  →  EXC-002 UNKNOWN ---

@pytest.mark.asyncio
async def test_exc002_infection_missing_unknown():
    """EXC-002 (realistic text): infection=None -> UNKNOWN with correct missing field."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.active_serious_infection = None

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc002 = next(c for c in result.criteria if c.criterion_id == "EXC-002")
    assert exc002.status == ExclusionStatus.UNKNOWN
    assert exc002.patient_value is None
    assert "clinical_status.active_serious_infection" in result.missing_information


# --- D. uncontrolled_cardiac_disease = True  →  EXC-003 TRIGGERED ---

@pytest.mark.asyncio
async def test_exc003_cardiac_true_triggered():
    """EXC-003 (realistic text): cardiac=True -> TRIGGERED, NOT routed to temporal/stroke handler."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.uncontrolled_cardiac_disease = True

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc003 = next(c for c in result.criteria if c.criterion_id == "EXC-003")
    assert exc003.status == ExclusionStatus.TRIGGERED
    assert exc003.patient_value is True
    assert "uncontrolled cardiac disease" in exc003.rationale.lower()
    assert "conditions.temporal_event" not in result.missing_information


# --- E. uncontrolled_cardiac_disease = False  →  EXC-003 CLEAR ---

@pytest.mark.asyncio
async def test_exc003_cardiac_false_clear():
    """EXC-003 (realistic text): cardiac=False -> CLEAR, NOT routed to temporal/stroke handler."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.uncontrolled_cardiac_disease = False

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc003 = next(c for c in result.criteria if c.criterion_id == "EXC-003")
    assert exc003.status == ExclusionStatus.CLEAR
    assert exc003.patient_value is False
    assert "no uncontrolled cardiac disease" in exc003.rationale.lower()


# --- F. uncontrolled_cardiac_disease = None  →  EXC-003 UNKNOWN ---

@pytest.mark.asyncio
async def test_exc003_cardiac_missing_unknown():
    """EXC-003 (realistic text): cardiac=None -> UNKNOWN with correct missing field."""
    agent = ExclusionDetectionAgent()
    patient = build_clear_patient()
    patient.clinical_status.uncontrolled_cardiac_disease = None

    result = await agent.evaluate("SYN-ONC-001", patient, _exc_realistic_chunks())

    exc003 = next(c for c in result.criteria if c.criterion_id == "EXC-003")
    assert exc003.status == ExclusionStatus.UNKNOWN
    assert exc003.patient_value is None
    assert "clinical_status.uncontrolled_cardiac_disease" in result.missing_information
