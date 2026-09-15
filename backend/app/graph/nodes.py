"""Node implementations for LangGraph clinical trial eligibility workflow.

Each node represents an explicit execution step:
1. validate_input_node: Validates trial_id, patient profile structure, date formats, and trial isolation.
2. retrieve_protocol_node: Retrieves inclusion & exclusion criteria scoped strictly to the trial.
3. inclusion_node: Executes InclusionMatchingAgent on inclusion criteria.
4. exclusion_node: Executes ExclusionDetectionAgent on exclusion criteria.
5. contradiction_node: Executes ContradictionAgent evaluating cross-criteria, patient facts, and silent exclusions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from app.agents.contradiction_agent import ContradictionAgent
from app.agents.decision_reviewer_agent import DecisionReviewerAgent
from app.agents.exclusion_detection_agent import ExclusionDetectionAgent
from app.agents.inclusion_matching_agent import InclusionMatchingAgent
from app.config import settings
from app.graph.state import WorkflowState
from app.rag.metadata_store import MetadataStore
from app.rag.service import RAGService, get_rag_service
from app.schemas.patient import PatientProfile
from app.schemas.rag import RetrievedChunk
from app.timing import log_node

logger = logging.getLogger(__name__)


def _rag_timeout() -> float:
    """Bounded deadline for RAG service init and retrieval (seconds)."""
    return float(settings.rag_retrieve_timeout_seconds) if settings.rag_retrieve_timeout_seconds > 0 else 60.0


class EligibilityWorkflowNodes:
    """Encapsulates node execution logic and injected service dependencies."""

    def __init__(
        self,
        rag_service: Optional[RAGService] = None,
        metadata_store: Optional[MetadataStore] = None,
        inclusion_agent: Optional[InclusionMatchingAgent] = None,
        exclusion_agent: Optional[ExclusionDetectionAgent] = None,
        contradiction_agent: Optional[ContradictionAgent] = None,
        decision_agent: Optional[DecisionReviewerAgent] = None,
    ) -> None:
        self.rag_service = rag_service
        self.metadata_store = metadata_store or MetadataStore()
        self.inclusion_agent = inclusion_agent or InclusionMatchingAgent()
        self.exclusion_agent = exclusion_agent or ExclusionDetectionAgent()
        self.contradiction_agent = contradiction_agent or ContradictionAgent()
        self.decision_agent = decision_agent or DecisionReviewerAgent()

    @log_node("validate_input")
    async def validate_input_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 1: Validates trial_id, patient profile, reference_date, and initial evidence."""
        errors: List[str] = list(state.get("errors") or [])
        warnings: List[str] = list(state.get("warnings") or [])

        trial_id = state.get("trial_id")
        if not trial_id or not isinstance(trial_id, str) or not trial_id.strip():
            errors.append("Validation failure: trial_id is required and must not be empty.")
            return {
                "errors": errors,
                "warnings": warnings,
                "current_step": "validate_input",
            }

        clean_trial_id = trial_id.strip()

        # Validate PatientProfile
        patient_profile = state.get("patient_profile")
        if not patient_profile:
            errors.append("Validation failure: patient_profile is required.")
            return {
                "errors": errors,
                "warnings": warnings,
                "current_step": "validate_input",
            }

        valid_patient: Optional[PatientProfile] = None
        if isinstance(patient_profile, PatientProfile):
            valid_patient = patient_profile
        elif isinstance(patient_profile, dict):
            try:
                valid_patient = PatientProfile.model_validate(patient_profile)
            except Exception as err:
                errors.append(f"Validation failure: invalid patient_profile structure: {err}")
                return {
                    "errors": errors,
                    "warnings": warnings,
                    "current_step": "validate_input",
                }
        else:
            errors.append("Validation failure: patient_profile must be a valid PatientProfile instance or dict.")
            return {
                "errors": errors,
                "warnings": warnings,
                "current_step": "validate_input",
            }

        # Derive patient_profile_id
        derived_pid = state.get("patient_profile_id")
        if not derived_pid and valid_patient and valid_patient.patient_profile_id:
            derived_pid = valid_patient.patient_profile_id
        if not derived_pid:
            derived_pid = "UNKNOWN_PATIENT"

        # Validate reference_date if supplied
        ref_date = state.get("reference_date")
        if ref_date and ref_date.strip():
            clean_date = ref_date.strip()
            try:
                datetime.strptime(clean_date, "%Y-%m-%d")
            except ValueError:
                errors.append(
                    f"Validation failure: invalid reference_date format '{clean_date}'. Expected YYYY-MM-DD."
                )

        # Validate trial isolation on any pre-provided protocol evidence
        existing_evidence = state.get("protocol_evidence") or []
        for chunk in existing_evidence:
            if chunk.trial_id != clean_trial_id:
                msg = (
                    f"Trial isolation violation: protocol evidence chunk '{chunk.chunk_id}' belongs to "
                    f"trial '{chunk.trial_id}', not selected trial '{clean_trial_id}'."
                )
                logger.error(msg)
                errors.append(msg)
                break

        return {
            "trial_id": clean_trial_id,
            "patient_profile": valid_patient,
            "patient_profile_id": derived_pid,
            "errors": errors,
            "warnings": warnings,
            "current_step": "validate_input",
        }

    @log_node("retrieve_protocol")
    async def retrieve_protocol_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 2: Retrieves protocol criteria scoped strictly to the selected trial."""
        errors: List[str] = list(state.get("errors") or [])
        warnings: List[str] = list(state.get("warnings") or [])

        # If previous steps encountered fatal errors, halt
        if errors:
            return {
                "errors": errors,
                "current_step": "retrieve_protocol",
            }

        trial_id = state["trial_id"]
        evidence: List[RetrievedChunk] = list(state.get("protocol_evidence") or [])

        # If evidence was already provided, verify trial isolation
        if evidence:
            for chunk in evidence:
                if chunk.trial_id != trial_id:
                    errors.append(
                        f"Trial isolation violation: retrieved chunk '{chunk.chunk_id}' belongs to "
                        f"trial '{chunk.trial_id}', not selected trial '{trial_id}'."
                    )
                    return {
                        "errors": errors,
                        "current_step": "retrieve_protocol",
                    }
            return {
                "protocol_evidence": evidence,
                "warnings": warnings,
                "current_step": "retrieve_protocol",
            }

        # Otherwise retrieve from metadata store or RAG service. Metadata is a
        # fast local JSON read. The RAG path (SentenceTransformer + FAISS) is
        # CPU/network bound and runs in a worker thread under a hard deadline so
        # it can never stall the async event loop indefinitely.
        try:
            if self.metadata_store.exists(trial_id):
                protocol_chunks = self.metadata_store.load(trial_id)
                evidence = [
                    RetrievedChunk(
                        chunk_id=c.chunk_id,
                        trial_id=c.trial_id,
                        criterion_id=c.criterion_id,
                        criterion_type=c.criterion_type,
                        text=c.text,
                        score=1.0,
                        source_page=c.source_page,
                        source_document=c.source_document,
                        source_excerpt=c.source_excerpt,
                    )
                    for c in protocol_chunks
                ]
            else:
                rag_service = self.rag_service or await asyncio.wait_for(
                    asyncio.to_thread(get_rag_service),
                    timeout=_rag_timeout(),
                )
                if rag_service.has_trial_index(trial_id):
                    res = await asyncio.wait_for(
                        asyncio.to_thread(
                            rag_service.retrieve,
                            trial_id=trial_id,
                            query="clinical eligibility criteria inclusion exclusion",
                            top_k=50,
                        ),
                        timeout=_rag_timeout(),
                    )
                    evidence = res.results
                else:
                    warnings.append(
                        f"No indexed protocol criteria found in RAG store for trial '{trial_id}'."
                    )
        except asyncio.TimeoutError:
            logger.warning("RAG retrieval timed out for trial %s", trial_id)
            errors.append(
                "Protocol retrieval error: RAG retrieval timed out after "
                f"{_rag_timeout()} seconds."
            )
            return {
                "errors": errors,
                "warnings": warnings,
                "current_step": "retrieve_protocol",
            }
        except Exception as err:
            logger.warning("RAG retrieval failed for trial %s: %s", trial_id, err)
            errors.append(f"Protocol retrieval error: {err}")
            return {
                "errors": errors,
                "warnings": warnings,
                "current_step": "retrieve_protocol",
            }

        # Verify all retrieved chunks preserve trial isolation and provenance
        if not evidence:
            errors.append(
                f"Protocol validation failure: No eligibility criteria found for trial '{trial_id}'. "
                "Clinical trial eligibility assessment requires validated protocol criteria."
            )

        for chunk in evidence:
            if chunk.trial_id != trial_id:
                errors.append(
                    f"Trial isolation violation: retrieved chunk '{chunk.chunk_id}' belongs to "
                    f"trial '{chunk.trial_id}', not selected trial '{trial_id}'."
                )
                break

        return {
            "protocol_evidence": evidence,
            "warnings": warnings,
            "errors": errors,
            "current_step": "retrieve_protocol",
        }

    @log_node("inclusion")
    async def inclusion_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 3: Executes InclusionMatchingAgent on inclusion criteria."""
        errors: List[str] = list(state.get("errors") or [])
        if errors:
            return {"errors": errors, "current_step": "inclusion"}

        trial_id = state["trial_id"]
        patient_profile = state["patient_profile"]
        evidence = state.get("protocol_evidence") or []

        # Filter strictly to inclusion criteria
        inc_evidence = [
            c for c in evidence if (c.criterion_type or "").lower() == "inclusion"
        ]

        # Verify trial isolation on inclusion evidence
        for chunk in inc_evidence:
            if chunk.trial_id != trial_id:
                errors.append(
                    f"Trial isolation violation in inclusion node: chunk '{chunk.chunk_id}' belongs to '{chunk.trial_id}'."
                )
                return {"errors": errors, "current_step": "inclusion"}

        try:
            assessment = await self.inclusion_agent.evaluate(
                trial_id=trial_id,
                patient_profile=patient_profile,
                retrieved_evidence=inc_evidence,
            )
            return {
                "inclusion_assessment": assessment,
                "current_step": "inclusion",
            }
        except Exception as err:
            logger.error("InclusionMatchingAgent failed: %s", err)
            errors.append(f"Inclusion matching failure: {err}")
            return {
                "errors": errors,
                "current_step": "inclusion",
            }

    @log_node("exclusion")
    async def exclusion_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 4: Executes ExclusionDetectionAgent on exclusion criteria."""
        errors: List[str] = list(state.get("errors") or [])
        if errors:
            return {"errors": errors, "current_step": "exclusion"}

        trial_id = state["trial_id"]
        patient_profile = state["patient_profile"]
        evidence = state.get("protocol_evidence") or []
        reference_date = state.get("reference_date")

        # Filter strictly to exclusion criteria
        exc_evidence = [
            c for c in evidence if (c.criterion_type or "").lower() == "exclusion"
        ]

        # Verify trial isolation on exclusion evidence
        for chunk in exc_evidence:
            if chunk.trial_id != trial_id:
                errors.append(
                    f"Trial isolation violation in exclusion node: chunk '{chunk.chunk_id}' belongs to '{chunk.trial_id}'."
                )
                return {"errors": errors, "current_step": "exclusion"}

        try:
            assessment = await self.exclusion_agent.evaluate(
                trial_id=trial_id,
                patient_profile=patient_profile,
                retrieved_evidence=exc_evidence,
                reference_date=reference_date,
            )
            return {
                "exclusion_assessment": assessment,
                "current_step": "exclusion",
            }
        except Exception as err:
            logger.error("ExclusionDetectionAgent failed: %s", err)
            errors.append(f"Exclusion detection failure: {err}")
            return {
                "errors": errors,
                "current_step": "exclusion",
            }

    @log_node("contradiction")
    async def contradiction_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 5: Executes ContradictionAgent evaluating criteria, patient facts, and upstream evaluations."""
        errors: List[str] = list(state.get("errors") or [])
        if errors:
            return {"errors": errors, "current_step": "contradiction"}

        trial_id = state["trial_id"]
        patient_profile = state["patient_profile"]
        evidence = state.get("protocol_evidence") or []
        inclusion_assessment = state.get("inclusion_assessment")
        exclusion_assessment = state.get("exclusion_assessment")
        reference_date = state.get("reference_date")

        try:
            assessment = await self.contradiction_agent.analyze(
                trial_id=trial_id,
                patient_profile=patient_profile,
                protocol_evidence=evidence,
                inclusion_assessment=inclusion_assessment,
                exclusion_assessment=exclusion_assessment,
                reference_date=reference_date,
            )
            return {
                "contradiction_assessment": assessment,
                "current_step": "contradiction",
            }
        except Exception as err:
            logger.error("ContradictionAgent failed: %s", err)
            errors.append(f"Contradiction analysis failure: {err}")
            return {
                "errors": errors,
                "current_step": "contradiction",
            }

    @log_node("decision")
    async def decision_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node 6: Executes DecisionReviewerAgent producing the final authoritative DecisionAssessment."""
        errors: List[str] = list(state.get("errors") or [])
        if errors:
            return {"errors": errors, "current_step": "decision"}

        trial_id = state["trial_id"]
        patient_profile = state["patient_profile"]
        evidence = state.get("protocol_evidence") or []
        inclusion_assessment = state.get("inclusion_assessment")
        exclusion_assessment = state.get("exclusion_assessment")
        contradiction_assessment = state.get("contradiction_assessment")

        if not inclusion_assessment:
            errors.append("Decision node error: inclusion_assessment is missing from state.")
            return {"errors": errors, "current_step": "decision"}

        if not exclusion_assessment:
            errors.append("Decision node error: exclusion_assessment is missing from state.")
            return {"errors": errors, "current_step": "decision"}

        try:
            assessment = self.decision_agent.evaluate(
                trial_id=trial_id,
                patient_profile=patient_profile,
                inclusion_assessment=inclusion_assessment,
                exclusion_assessment=exclusion_assessment,
                contradiction_assessment=contradiction_assessment,
                protocol_evidence=evidence,
            )
            return {
                "decision_assessment": assessment,
                "current_step": "decision",
            }
        except Exception as err:
            logger.error("DecisionReviewerAgent failed: %s", err)
            errors.append(f"Decision evaluation failure: {err}")
            return {
                "errors": errors,
                "current_step": "decision",
            }
