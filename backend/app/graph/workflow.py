"""Real LangGraph Multi-Agent Orchestration Workflow for Clinical Trial Eligibility.

Target Workflow Architecture:
START
  ↓
Validate Input
  ↓
Retrieve Trial Protocol Evidence
  ↓
Inclusion Matching
  ↓
Exclusion Detection
  ↓
Contradiction Analysis
  ↓
END
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.contradiction_agent import ContradictionAgent
from app.agents.decision_reviewer_agent import DecisionReviewerAgent
from app.agents.exclusion_detection_agent import ExclusionDetectionAgent
from app.agents.inclusion_matching_agent import InclusionMatchingAgent
from app.graph.nodes import EligibilityWorkflowNodes
from app.graph.state import WorkflowState, create_initial_state
from app.rag.metadata_store import MetadataStore
from app.rag.service import RAGService
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)


def _route_after_validate(state: WorkflowState) -> str:
    """Conditional router after validate_input: stop if errors occurred."""
    if state.get("errors"):
        return END
    return "retrieve_protocol"


def _route_after_retrieve(state: WorkflowState) -> str:
    """Conditional router after retrieve_protocol: stop if errors occurred."""
    if state.get("errors"):
        return END
    return "inclusion"


def _route_after_inclusion(state: WorkflowState) -> str:
    """Conditional router after inclusion: stop if errors occurred."""
    if state.get("errors"):
        return END
    return "exclusion"


def _route_after_exclusion(state: WorkflowState) -> str:
    """Conditional router after exclusion: stop if errors occurred."""
    if state.get("errors"):
        return END
    return "contradiction"


def _route_after_contradiction(state: WorkflowState) -> str:
    """Conditional router after contradiction: stop if errors occurred."""
    if state.get("errors"):
        return END
    return "decision"


def build_workflow(
    rag_service: Optional[RAGService] = None,
    metadata_store: Optional[MetadataStore] = None,
    inclusion_agent: Optional[InclusionMatchingAgent] = None,
    exclusion_agent: Optional[ExclusionDetectionAgent] = None,
    contradiction_agent: Optional[ContradictionAgent] = None,
    decision_agent: Optional[DecisionReviewerAgent] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """Constructs and compiles the real LangGraph clinical trial eligibility workflow.

    Supports dependency injection for deterministic testing and modular execution.

    ``checkpointer`` (optional) enables LangGraph persistent state/checkpointing:
    saved state is recovered by ``thread_id`` on subsequent invocations.
    """
    node_container = EligibilityWorkflowNodes(
        rag_service=rag_service,
        metadata_store=metadata_store,
        inclusion_agent=inclusion_agent,
        exclusion_agent=exclusion_agent,
        contradiction_agent=contradiction_agent,
        decision_agent=decision_agent,
    )

    builder = StateGraph(WorkflowState)

    # Register nodes
    builder.add_node("validate_input", node_container.validate_input_node)
    builder.add_node("retrieve_protocol", node_container.retrieve_protocol_node)
    builder.add_node("inclusion", node_container.inclusion_node)
    builder.add_node("exclusion", node_container.exclusion_node)
    builder.add_node("contradiction", node_container.contradiction_node)
    builder.add_node("decision", node_container.decision_node)

    # Wire edges with conditional stops on error
    builder.add_edge(START, "validate_input")
    builder.add_conditional_edges(
        "validate_input",
        _route_after_validate,
        {"retrieve_protocol": "retrieve_protocol", END: END},
    )
    builder.add_conditional_edges(
        "retrieve_protocol",
        _route_after_retrieve,
        {"inclusion": "inclusion", END: END},
    )
    builder.add_conditional_edges(
        "inclusion",
        _route_after_inclusion,
        {"exclusion": "exclusion", END: END},
    )
    builder.add_conditional_edges(
        "exclusion",
        _route_after_exclusion,
        {"contradiction": "contradiction", END: END},
    )
    builder.add_conditional_edges(
        "contradiction",
        _route_after_contradiction,
        {"decision": "decision", END: END},
    )
    builder.add_edge("decision", END)

    return builder.compile(checkpointer=checkpointer)


async def run_workflow(
    state_or_trial_id: Union[WorkflowState, Dict[str, Any], str],
    patient_profile: Optional[PatientProfile] = None,
    reference_date: Optional[str] = None,
    protocol_evidence: Optional[list[RetrievedChunk]] = None,
    rag_service: Optional[RAGService] = None,
    metadata_store: Optional[MetadataStore] = None,
    inclusion_agent: Optional[InclusionMatchingAgent] = None,
    exclusion_agent: Optional[ExclusionDetectionAgent] = None,
    contradiction_agent: Optional[ContradictionAgent] = None,
    decision_agent: Optional[DecisionReviewerAgent] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    thread_id: Optional[str] = None,
) -> WorkflowState:
    """Executes the compiled LangGraph workflow to completion.

    Accepts either an existing WorkflowState / dict or explicit parameters.

    ``checkpointer`` enables LangGraph persistent state/checkpointing. When a
    ``thread_id`` is provided it is used as the LangGraph thread identifier, so
    the same ``checkpointer`` + ``thread_id`` pair lets a caller recover or
    resume the saved workflow state for that execution.
    """
    timer = start_timer()
    compiled_app = build_workflow(
        rag_service=rag_service,
        metadata_store=metadata_store,
        inclusion_agent=inclusion_agent,
        exclusion_agent=exclusion_agent,
        contradiction_agent=contradiction_agent,
        decision_agent=decision_agent,
        checkpointer=checkpointer,
    )
    log_stage("graph.build", timer.elapsed_ms(), ok=True)

    if isinstance(state_or_trial_id, str):
        if patient_profile is None:
            raise ValueError("patient_profile must be provided when passing trial_id as string.")
        init_state = create_initial_state(
            trial_id=state_or_trial_id,
            patient_profile=patient_profile,
            reference_date=reference_date,
            protocol_evidence=protocol_evidence,
        )
    else:
        init_state = dict(state_or_trial_id)  # type: ignore

    config: Optional[Dict[str, Any]] = None
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
    invoke_timer = start_timer()
    final_state = await compiled_app.ainvoke(init_state, config=config)
    log_stage("workflow.invoke", invoke_timer.elapsed_ms(), ok=True)

    return final_state  # type: ignore
