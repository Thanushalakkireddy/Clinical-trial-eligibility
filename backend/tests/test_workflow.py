"""Test suite for Checkpoint 9: Real LangGraph Multi-Agent Orchestration.

Tests verify:
1. Graph builds successfully.
2. Graph contains expected nodes.
3. Simple complete patient/protocol workflow executes (real state transitions).
4. trial_id remains unchanged through every node.
5. RAG retrieval uses selected trial.
6. Inclusion node receives only inclusion evidence.
7. Exclusion node receives only exclusion evidence.
8. Contradiction node receives upstream assessments.
9. Provenance survives workflow execution.
10. Patient profile survives workflow execution.
11. Inclusion assessment survives workflow execution.
12. Exclusion assessment survives workflow execution.
13. Contradiction assessment survives workflow execution.
14. Missing patient information propagates as UNKNOWN.
15. Exclusion trigger propagates correctly.
16. Cross-trial evidence causes workflow failure.
17. Invalid trial_id is rejected.
18. Invalid patient profile is rejected.
19. Node failure creates structured workflow error.
20. API endpoint executes actual workflow.
21. API endpoint validates empty trial.
22. API endpoint handles cross-trial evidence safely.
23. Dependency injection allows custom services.
24. Legacy run endpoint maintains compatibility.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.agents.contradiction_agent import ContradictionAgent
from app.agents.exclusion_detection_agent import ExclusionDetectionAgent
from app.agents.inclusion_matching_agent import InclusionMatchingAgent
from app.graph.state import WorkflowState, create_initial_state
from app.graph.workflow import build_workflow, run_workflow
from app.main import app
from app.rag.service import RAGService
from app.schemas.exclusion import ExclusionStatus
from app.schemas.inclusion import InclusionCriterionAssessment, InclusionStatus
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
from app.schemas.rag import RetrievalResult, RetrievedChunk
from app.schemas.workflow import WorkflowEvaluateRequest


# =============================================================================
# Helper Fixtures
# =============================================================================

def make_test_patient(
    age: int = 45,
    ecog: int = 1,
    egfr_val: float = 65.0,
    has_infection: bool = False,
) -> PatientProfile:
    """Creates a deterministic test patient profile."""
    return PatientProfile(
        patient_profile_id="PAT-LG-001",
        demographics=Demographics(
            age=age,
            pregnancy_status=PregnancyStatus.NOT_PREGNANT,
            breastfeeding_status=False,
        ),
        clinical_status=ClinicalStatus(
            ecog_performance_status=ecog,
            active_serious_infection=has_infection,
            uncontrolled_cardiac_disease=False,
        ),
        labs=Labs(
            egfr=LabValue(value=egfr_val, unit="mL/min/1.73m2"),
            anc=LabValue(value=2.5, unit="x10^9/L"),
            platelets=LabValue(value=200.0, unit="x10^9/L"),
            hemoglobin=LabValue(value=13.0, unit="g/dL"),
            bilirubin=LabValue(value=0.8, unit="mg/dL"),
            ast=LabValue(value=22.0, unit="U/L"),
            alt=LabValue(value=20.0, unit="U/L"),
        ),
        conditions=[
            ConditionItem(name="Non-Small Cell Lung Cancer", status="active", documented=True),
        ],
        treatment_history=TreatmentHistory(
            recent_systemic_anticancer_therapy=False,
            last_treatment_date="2025-01-01",
        ),
    )


def make_test_evidence(trial_id: str = "TRIAL-LG-001") -> list[RetrievedChunk]:
    """Creates protocol criteria with full provenance."""
    return [
        RetrievedChunk(
            chunk_id=f"{trial_id}-CHK-INC-AGE",
            trial_id=trial_id,
            criterion_id="INC-AGE",
            criterion_type="inclusion",
            text="Age >= 18 years",
            score=0.95,
            source_page=2,
            source_document="protocol_v1.pdf",
            source_excerpt="Patient must be at least 18 years of age",
        ),
        RetrievedChunk(
            chunk_id=f"{trial_id}-CHK-INC-EGFR",
            trial_id=trial_id,
            criterion_id="INC-EGFR",
            criterion_type="inclusion",
            text="eGFR >= 30 mL/min/1.73m2",
            score=0.92,
            source_page=2,
            source_document="protocol_v1.pdf",
            source_excerpt="Adequate renal function defined as eGFR >= 30",
        ),
        RetrievedChunk(
            chunk_id=f"{trial_id}-CHK-EXC-INF",
            trial_id=trial_id,
            criterion_id="EXC-INF",
            criterion_type="exclusion",
            text="Active serious infection",
            score=0.91,
            source_page=4,
            source_document="protocol_v1.pdf",
            source_excerpt="Patients with active serious infection are excluded",
        ),
    ]


# =============================================================================
# Mandatory Workflow Tests (1 to 20+)
# =============================================================================

def test_1_graph_builds_successfully():
    """1. Graph builds successfully."""
    compiled_graph = build_workflow()
    assert compiled_graph is not None
    # Verify compiled graph has runnable interface
    assert hasattr(compiled_graph, "ainvoke")
    assert hasattr(compiled_graph, "invoke")


def test_2_graph_contains_expected_nodes():
    """2. Graph contains expected nodes."""
    compiled_graph = build_workflow()
    # Check nodes in compiled graph
    node_keys = compiled_graph.get_graph().nodes.keys()
    expected_nodes = [
        "validate_input",
        "retrieve_protocol",
        "inclusion",
        "exclusion",
        "contradiction",
        "decision",
    ]
    for expected in expected_nodes:
        assert expected in node_keys, f"Expected node '{expected}' not found in graph nodes: {node_keys}"


@pytest.mark.asyncio
async def test_3_simple_complete_workflow_executes_state_transitions():
    """3. Simple complete patient/protocol workflow executes and proves real state transitions."""
    trial_id = "TRIAL-LG-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    # Execute workflow using real compiled LangGraph
    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    assert final_state is not None
    assert final_state["trial_id"] == trial_id
    assert final_state["patient_profile_id"] == patient.patient_profile_id
    assert final_state["current_step"] == "decision"
    assert len(final_state["errors"]) == 0

    # Verify each sequential stage executed
    assert final_state["inclusion_assessment"] is not None
    assert final_state["inclusion_assessment"].overall_status == InclusionStatus.PASS

    assert final_state["exclusion_assessment"] is not None
    assert final_state["exclusion_assessment"].overall_status == ExclusionStatus.CLEAR

    assert final_state["contradiction_assessment"] is not None
    assert final_state["contradiction_assessment"].has_critical_findings is False

    assert final_state["decision_assessment"] is not None
    assert final_state["decision_assessment"].final_status.value == "ELIGIBLE"

    assert final_state["exclusion_assessment"] is not None
    assert final_state["exclusion_assessment"].overall_status == ExclusionStatus.CLEAR

    assert final_state["contradiction_assessment"] is not None
    assert final_state["contradiction_assessment"].has_critical_findings is False


@pytest.mark.asyncio
async def test_4_trial_id_remains_unchanged_through_every_node():
    """4. trial_id remains unchanged through every node."""
    trial_id = "TRIAL-ISOLATE-777"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    assert final_state["trial_id"] == trial_id
    assert final_state["inclusion_assessment"].trial_id == trial_id
    assert final_state["exclusion_assessment"].trial_id == trial_id
    assert final_state["contradiction_assessment"].trial_id == trial_id


@pytest.mark.asyncio
async def test_5_rag_retrieval_uses_selected_trial():
    """5. RAG retrieval uses selected trial."""
    mock_rag = MagicMock(spec=RAGService)
    mock_rag.has_trial_index.return_value = True
    trial_id = "TRIAL-RAG-SPECIFIC"

    mock_rag.retrieve.return_value = RetrievalResult(
        trial_id=trial_id,
        query="test",
        results=make_test_evidence(trial_id),
        total_results=3,
        retrieval_time_ms=5.0,
    )

    patient = make_test_patient()
    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        rag_service=mock_rag,
    )

    # Assert RAG service was called with the authoritative trial_id
    mock_rag.retrieve.assert_called_once()
    call_kwargs = mock_rag.retrieve.call_args[1]
    assert call_kwargs["trial_id"] == trial_id
    assert len(final_state["protocol_evidence"]) == 3


@pytest.mark.asyncio
async def test_6_inclusion_node_receives_only_inclusion_evidence():
    """6. Inclusion node receives only inclusion evidence."""
    mock_inc_agent = MagicMock(spec=InclusionMatchingAgent)
    mock_inc_agent.evaluate = AsyncMock()

    # Create dummy return for inclusion
    from app.schemas.inclusion import InclusionAssessment
    mock_inc_agent.evaluate.return_value = InclusionAssessment(
        trial_id="TRIAL-001",
        patient_profile_id="PAT-001",
        overall_status=InclusionStatus.PASS,
        criteria=[],
        missing_information=[],
        warnings=[],
    )

    trial_id = "TRIAL-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)  # 2 inclusion, 1 exclusion

    await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
        inclusion_agent=mock_inc_agent,
    )

    mock_inc_agent.evaluate.assert_called_once()
    passed_evidence = mock_inc_agent.evaluate.call_args[1]["retrieved_evidence"]
    assert len(passed_evidence) == 2
    for chunk in passed_evidence:
        assert chunk.criterion_type == "inclusion"


@pytest.mark.asyncio
async def test_7_exclusion_node_receives_only_exclusion_evidence():
    """7. Exclusion node receives only exclusion evidence."""
    mock_exc_agent = MagicMock(spec=ExclusionDetectionAgent)
    mock_exc_agent.evaluate = AsyncMock()

    from app.schemas.exclusion import ExclusionAssessment
    mock_exc_agent.evaluate.return_value = ExclusionAssessment(
        trial_id="TRIAL-001",
        patient_profile_id="PAT-001",
        overall_status=ExclusionStatus.CLEAR,
        criteria=[],
        missing_information=[],
        warnings=[],
    )

    trial_id = "TRIAL-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)  # 2 inclusion, 1 exclusion

    await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
        exclusion_agent=mock_exc_agent,
    )

    mock_exc_agent.evaluate.assert_called_once()
    passed_evidence = mock_exc_agent.evaluate.call_args[1]["retrieved_evidence"]
    assert len(passed_evidence) == 1
    assert passed_evidence[0].criterion_type == "exclusion"


@pytest.mark.asyncio
async def test_8_contradiction_node_receives_upstream_assessments():
    """8. Contradiction node receives upstream assessments."""
    mock_contra_agent = MagicMock(spec=ContradictionAgent)
    mock_contra_agent.analyze = AsyncMock()

    from app.schemas.contradiction import ContradictionAssessment
    mock_contra_agent.analyze.return_value = ContradictionAssessment(
        trial_id="TRIAL-001",
        patient_profile_id="PAT-001",
        findings=[],
        checked_criteria=[],
        has_critical_findings=False,
        summary="No contradictions",
    )

    trial_id = "TRIAL-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
        contradiction_agent=mock_contra_agent,
    )

    mock_contra_agent.analyze.assert_called_once()
    kwargs = mock_contra_agent.analyze.call_args[1]
    assert kwargs["inclusion_assessment"] is not None
    assert kwargs["inclusion_assessment"].overall_status == InclusionStatus.PASS
    assert kwargs["exclusion_assessment"] is not None
    assert kwargs["exclusion_assessment"].overall_status == ExclusionStatus.CLEAR


@pytest.mark.asyncio
async def test_9_provenance_survives_workflow_execution():
    """9. Provenance survives workflow execution."""
    trial_id = "TRIAL-PROV-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    retrieved = final_state["protocol_evidence"]
    assert len(retrieved) == 3
    for chunk in retrieved:
        assert chunk.source_page == 2 or chunk.source_page == 4
        assert chunk.source_document == "protocol_v1.pdf"
        assert chunk.source_excerpt is not None
        assert chunk.score > 0.8


@pytest.mark.asyncio
async def test_10_patient_profile_survives_workflow_execution():
    """10. Patient profile survives workflow execution."""
    trial_id = "TRIAL-PAT-001"
    patient = make_test_patient(age=52, ecog=0, egfr_val=75.0)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=make_test_evidence(trial_id),
    )

    surviving_patient = final_state["patient_profile"]
    assert surviving_patient.demographics.age == 52
    assert surviving_patient.clinical_status.ecog_performance_status == 0
    assert surviving_patient.labs.egfr.value == 75.0
    assert final_state["patient_profile_id"] == patient.patient_profile_id


@pytest.mark.asyncio
async def test_11_inclusion_assessment_survives_workflow_execution():
    """11. Inclusion assessment survives workflow execution."""
    trial_id = "TRIAL-INC-SURVIVE"
    patient = make_test_patient(age=45, egfr_val=60.0)
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    inc = final_state["inclusion_assessment"]
    assert inc is not None
    assert inc.trial_id == trial_id
    assert inc.overall_status == InclusionStatus.PASS
    assert len(inc.criteria) == 2


@pytest.mark.asyncio
async def test_12_exclusion_assessment_survives_workflow_execution():
    """12. Exclusion assessment survives workflow execution."""
    trial_id = "TRIAL-EXC-SURVIVE"
    patient = make_test_patient(has_infection=False)
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    exc = final_state["exclusion_assessment"]
    assert exc is not None
    assert exc.trial_id == trial_id
    assert exc.overall_status == ExclusionStatus.CLEAR
    assert len(exc.criteria) == 1


@pytest.mark.asyncio
async def test_13_contradiction_assessment_survives_workflow_execution():
    """13. Contradiction assessment survives workflow execution."""
    trial_id = "TRIAL-CONTRA-SURVIVE"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    contra = final_state["contradiction_assessment"]
    assert contra is not None
    assert contra.trial_id == trial_id
    assert isinstance(contra.findings, list)
    assert isinstance(contra.checked_criteria, list)


@pytest.mark.asyncio
async def test_14_missing_patient_information_propagates_as_unknown():
    """14. Missing patient information propagates as UNKNOWN."""
    trial_id = "TRIAL-UNKNOWN-PROP"
    patient = make_test_patient()
    patient.labs.egfr = None  # eGFR missing

    evidence = [
        RetrievedChunk(
            chunk_id="CHK-EGFR",
            trial_id=trial_id,
            criterion_id="INC-EGFR",
            criterion_type="inclusion",
            text="eGFR >= 30 mL/min/1.73m2",
            score=0.9,
            source_page=1,
            source_document="protocol.pdf",
        )
    ]

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    inc = final_state["inclusion_assessment"]
    assert inc.overall_status == InclusionStatus.UNKNOWN
    assert inc.criteria[0].status == InclusionStatus.UNKNOWN
    assert len(inc.missing_information) > 0


@pytest.mark.asyncio
async def test_15_exclusion_trigger_propagates_correctly():
    """15. Exclusion trigger propagates correctly."""
    trial_id = "TRIAL-TRIGGER-PROP"
    patient = make_test_patient(has_infection=True)  # Active infection
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
    )

    exc = final_state["exclusion_assessment"]
    assert exc.overall_status == ExclusionStatus.TRIGGERED
    assert any(c.status == ExclusionStatus.TRIGGERED for c in exc.criteria)


@pytest.mark.asyncio
async def test_16_cross_trial_evidence_causes_workflow_failure():
    """16. Cross-trial evidence causes workflow failure."""
    trial_id = "TRIAL-PRIMARY"
    patient = make_test_patient()

    # Pass evidence belonging to a foreign trial
    foreign_evidence = [
        RetrievedChunk(
            chunk_id="CHK-FOREIGN",
            trial_id="TRIAL-FOREIGN-999",
            criterion_id="INC-1",
            criterion_type="inclusion",
            text="Age >= 18",
            score=0.9,
            source_page=1,
            source_document="protocol.pdf",
        )
    ]

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=foreign_evidence,
    )

    # Workflow must record structured error and halt
    assert len(final_state["errors"]) > 0
    assert any("Trial isolation violation" in err for err in final_state["errors"])
    # Downstream agents should NOT have executed
    assert final_state.get("inclusion_assessment") is None
    assert final_state.get("exclusion_assessment") is None


@pytest.mark.asyncio
async def test_17_invalid_trial_id_is_rejected():
    """17. Invalid trial_id is rejected."""
    patient = make_test_patient()

    final_state = await run_workflow(
        state_or_trial_id="",
        patient_profile=patient,
    )

    assert len(final_state["errors"]) > 0
    assert any("trial_id is required" in err for err in final_state["errors"])
    assert final_state["current_step"] == "validate_input"


@pytest.mark.asyncio
async def test_18_invalid_patient_profile_is_rejected():
    """18. Invalid patient profile is rejected."""
    # Test passing None or empty dictionary
    init_state = create_initial_state(
        trial_id="TRIAL-001",
        patient_profile=None,  # type: ignore
    )

    final_state = await run_workflow(init_state)
    assert len(final_state["errors"]) > 0
    assert any("patient_profile is required" in err for err in final_state["errors"])
    assert final_state["current_step"] == "validate_input"


@pytest.mark.asyncio
async def test_19_node_failure_creates_structured_workflow_error():
    """19. Node failure creates structured workflow error."""
    mock_inc_agent = MagicMock(spec=InclusionMatchingAgent)
    mock_inc_agent.evaluate = AsyncMock(side_effect=RuntimeError("Simulated LLM service timeout"))

    trial_id = "TRIAL-FAIL-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    final_state = await run_workflow(
        state_or_trial_id=trial_id,
        patient_profile=patient,
        protocol_evidence=evidence,
        inclusion_agent=mock_inc_agent,
    )

    assert len(final_state["errors"]) > 0
    assert any("Inclusion matching failure" in err for err in final_state["errors"])
    # Did NOT invent fake clinical status
    assert final_state.get("inclusion_assessment") is None
    # Conditional edge stopped execution before contradiction
    assert final_state.get("contradiction_assessment") is None


def test_20_api_endpoint_executes_actual_workflow():
    """20. API endpoint executes actual workflow."""
    client = TestClient(app)
    trial_id = "TRIAL-API-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    payload = {
        "trial_id": trial_id,
        "patient_profile": patient.model_dump(),
        "protocol_evidence": [c.model_dump() for c in evidence],
        "reference_date": "2025-06-01",
    }

    response = client.post("/api/v1/workflow/evaluate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["trial_id"] == trial_id
    assert data["patient_profile_id"] == patient.patient_profile_id
    assert data["inclusion_assessment"]["overall_status"] == "PASS"
    assert data["exclusion_assessment"]["overall_status"] == "CLEAR"
    assert data["contradiction_assessment"]["has_critical_findings"] is False
    assert data["errors"] == []
    assert data["current_step"] == "decision"
    assert data["decision_assessment"] is not None
    assert data["decision_assessment"]["final_status"] == "ELIGIBLE"


def test_21_api_endpoint_validates_empty_trial():
    """21. API endpoint validates empty trial."""
    client = TestClient(app)
    patient = make_test_patient()

    payload = {
        "trial_id": "",
        "patient_profile": patient.model_dump(),
    }

    response = client.post("/api/v1/workflow/evaluate", json=payload)
    assert response.status_code in (400, 422)


def test_22_api_endpoint_handles_cross_trial_evidence_safely():
    """22. API endpoint handles cross-trial evidence safely."""
    client = TestClient(app)
    trial_id = "TRIAL-PRIMARY"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)
    evidence[0].trial_id = "FOREIGN-TRIAL"

    payload = {
        "trial_id": trial_id,
        "patient_profile": patient.model_dump(),
        "protocol_evidence": [c.model_dump() for c in evidence],
    }

    response = client.post("/api/v1/workflow/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["errors"]) > 0
    assert any("Trial isolation violation" in err for err in data["errors"])


def test_23_dependency_injection_allows_custom_services():
    """23. Dependency injection allows custom services."""
    mock_inc = MagicMock()
    mock_exc = MagicMock()
    mock_contra = MagicMock()
    mock_rag = MagicMock()

    custom_graph = build_workflow(
        rag_service=mock_rag,
        inclusion_agent=mock_inc,
        exclusion_agent=mock_exc,
        contradiction_agent=mock_contra,
    )
    assert custom_graph is not None


def test_24_legacy_run_endpoint():
    """24. Legacy run endpoint maintains compatibility."""
    client = TestClient(app)
    trial_id = "TRIAL-LEGACY-001"
    patient = make_test_patient()
    evidence = make_test_evidence(trial_id)

    payload = {
        "trial_id": trial_id,
        "patient_profile": patient.model_dump(),
        "protocol_evidence": [c.model_dump() for c in evidence],
    }

    response = client.post("/api/v1/workflow/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["trial_id"] == trial_id
    assert data["status"] == "COMPLETED"
    assert "summary" in data


# =============================================================================
# Checkpoint 2A Regression Tests – Workflow-level EXC-002 / EXC-003 mapping
#
# Uses the full SYN-ONC-001 protocol evidence and a complete eligible oncology
# patient. These verify the final decision flips correctly based solely on the
# documented clinical-status booleans (no temporal-handler misrouting).
# =============================================================================

def build_synonc001_evidence() -> list[RetrievedChunk]:
    """Full SYN-ONC-001 protocol evidence (4 inclusion + 5 exclusion chunks)."""
    return [
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0001",
            trial_id="SYN-ONC-001",
            criterion_id="INC-001",
            criterion_type="inclusion",
            text="Patients must be at least 18 years of age at the time of informed consent. No upper age limit applies for this study.",
            score=1.0,
            source_page=1,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Inclusion Criteria — 1. Age >= 18 years",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0002",
            trial_id="SYN-ONC-001",
            criterion_id="INC-002",
            criterion_type="inclusion",
            text="Patients must have a histologically or cytologically confirmed advanced solid tumor that is metastatic or unresectable, for which no standard therapy is available or the patient is not a candidate for standard therapy.",
            score=1.0,
            source_page=1,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Inclusion Criteria — 2. Advanced solid tumor (metastatic or unresectable)",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0003",
            trial_id="SYN-ONC-001",
            criterion_id="INC-003",
            criterion_type="inclusion",
            text="Patients must have an Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1.",
            score=1.0,
            source_page=1,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Inclusion Criteria — 3. ECOG performance status 0 or 1",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0004",
            trial_id="SYN-ONC-001",
            criterion_id="INC-004",
            criterion_type="inclusion",
            text="Patients must have adequate renal function, defined as an estimated glomerular filtration rate (eGFR) of at least 30 mL/min/1.73 m2 calculated using the Cockcroft-Gault or CKD-EPI formula.",
            score=1.0,
            source_page=1,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Inclusion Criteria — 4. Adequate renal function (eGFR >= 30 mL/min/1.73 m2)",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0005",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-001",
            criterion_type="exclusion",
            text="Patients with an estimated glomerular filtration rate (eGFR) of less than 30 mL/min/1.73 m2 will be excluded from the study.",
            score=1.0,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 1. eGFR < 30 mL/min/1.73 m2",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0006",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-002",
            criterion_type="exclusion",
            text="Patients with active serious infection requiring systemic antimicrobial therapy within 14 days prior to administration of study treatment will be excluded.",
            score=1.0,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 2. Active serious infection",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0007",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-003",
            criterion_type="exclusion",
            text="Patients with uncontrolled cardiac disease, including unstable angina, myocardial infarction, or clinically significant arrhythmia within 6 months prior to enrollment, will be excluded.",
            score=1.0,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 3. Uncontrolled cardiac disease",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0008",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-004",
            criterion_type="exclusion",
            text="Patients with severe hypersensitivity to any of the study drug components or excipients will be excluded.",
            score=1.0,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 4. Severe hypersensitivity to study drug or excipients",
        ),
        RetrievedChunk(
            chunk_id="SYN-ONC-001_chunk_0009",
            trial_id="SYN-ONC-001",
            criterion_id="EXC-005",
            criterion_type="exclusion",
            text="Patients who received systemic anticancer therapy within 14 days prior to the first dose of study treatment, or who are scheduled to receive such therapy during the treatment period, will be excluded.",
            score=1.0,
            source_page=2,
            source_document="SYN-ONC-001_protocol.pdf",
            source_excerpt="Exclusion Criteria — 5. Recent systemic anticancer therapy within 14 days",
        ),
    ]


def build_eligible_oncology_patient(
    infection: bool | None = None,
    cardiac: bool | None = None,
    profile_id: str = "SYN-PAT-WF-ELIGIBLE",
) -> PatientProfile:
    """Complete oncology patient satisfying every SYN-ONC-001 inclusion criterion."""
    return PatientProfile(
        patient_profile_id=profile_id,
        demographics=Demographics(
            age=52,
            pregnancy_status=PregnancyStatus.NOT_PREGNANT,
            breastfeeding_status=False,
        ),
        conditions=[
            ConditionItem(name="Advanced Solid Tumor (metastatic)", status="active", documented=True),
            ConditionItem(name="no history of severe hypersensitivity", status="none", documented=True),
        ],
        clinical_status=ClinicalStatus(
            ecog_performance_status=1,
            active_serious_infection=infection,
            uncontrolled_cardiac_disease=cardiac,
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
        treatment_history=TreatmentHistory(
            recent_systemic_anticancer_therapy=False,
            last_treatment_date="2025-01-01",
        ),
    )


@pytest.mark.asyncio
async def test_2a_1_complete_eligible_patient_is_eligible():
    """Checkpoint 2A.1: Complete eligible oncology patient -> ELIGIBLE."""
    patient = build_eligible_oncology_patient(
        infection=False,
        cardiac=False,
        profile_id="SYN-PAT-WF-ELIGIBLE",
    )
    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=build_synonc001_evidence(),
    )

    assert len(final_state["errors"]) == 0
    assert final_state["decision_assessment"] is not None
    assert final_state["decision_assessment"].final_status.value == "ELIGIBLE"
    exc = final_state["exclusion_assessment"]
    exc002 = next(c for c in exc.criteria if c.criterion_id == "EXC-002")
    exc003 = next(c for c in exc.criteria if c.criterion_id == "EXC-003")
    assert exc002.status == ExclusionStatus.CLEAR
    assert exc003.status == ExclusionStatus.CLEAR


@pytest.mark.asyncio
async def test_2a_2_active_serious_infection_true_not_eligible():
    """Checkpoint 2A.2: Same patient + active_serious_infection=True -> NOT_ELIGIBLE."""
    patient = build_eligible_oncology_patient(
        infection=True,
        cardiac=False,
        profile_id="SYN-PAT-WF-INFECTION",
    )
    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=build_synonc001_evidence(),
    )

    assert len(final_state["errors"]) == 0
    assert final_state["decision_assessment"].final_status.value == "NOT_ELIGIBLE"
    exc002 = next(c for c in final_state["exclusion_assessment"].criteria if c.criterion_id == "EXC-002")
    assert exc002.status == ExclusionStatus.TRIGGERED


@pytest.mark.asyncio
async def test_2a_3_active_serious_infection_missing_more_info():
    """Checkpoint 2A.3: Same patient + active_serious_infection missing -> MORE_INFORMATION_REQUIRED."""
    patient = build_eligible_oncology_patient(
        infection=None,
        cardiac=False,
        profile_id="SYN-PAT-WF-INF-MISSING",
    )
    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=build_synonc001_evidence(),
    )

    assert len(final_state["errors"]) == 0
    assert final_state["decision_assessment"].final_status.value == "MORE_INFORMATION_REQUIRED"
    exc002 = next(c for c in final_state["exclusion_assessment"].criteria if c.criterion_id == "EXC-002")
    assert exc002.status == ExclusionStatus.UNKNOWN
    assert "clinical_status.active_serious_infection" in final_state["exclusion_assessment"].missing_information


@pytest.mark.asyncio
async def test_2a_4_uncontrolled_cardiac_true_not_eligible():
    """Checkpoint 2A.4: Same patient + uncontrolled_cardiac_disease=True -> NOT_ELIGIBLE."""
    patient = build_eligible_oncology_patient(
        infection=False,
        cardiac=True,
        profile_id="SYN-PAT-WF-CARDIAC",
    )
    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=build_synonc001_evidence(),
    )

    assert len(final_state["errors"]) == 0
    assert final_state["decision_assessment"].final_status.value == "NOT_ELIGIBLE"
    exc003 = next(c for c in final_state["exclusion_assessment"].criteria if c.criterion_id == "EXC-003")
    assert exc003.status == ExclusionStatus.TRIGGERED


@pytest.mark.asyncio
async def test_2a_5_uncontrolled_cardiac_false_eligible():
    """Checkpoint 2A.5: Same patient + uncontrolled_cardiac_disease=False -> ELIGIBLE."""
    patient = build_eligible_oncology_patient(
        infection=False,
        cardiac=False,
        profile_id="SYN-PAT-WF-CARDIAC-FALSE",
    )
    final_state = await run_workflow(
        state_or_trial_id="SYN-ONC-001",
        patient_profile=patient,
        protocol_evidence=build_synonc001_evidence(),
    )

    assert len(final_state["errors"]) == 0
    assert final_state["decision_assessment"].final_status.value == "ELIGIBLE"
    exc003 = next(c for c in final_state["exclusion_assessment"].criteria if c.criterion_id == "EXC-003")
    assert exc003.status == ExclusionStatus.CLEAR
