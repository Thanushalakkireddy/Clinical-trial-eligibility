/**
 * Shared TypeScript types for Clinical Trial Eligibility System
 * Synchronized with backend Pydantic schemas.
 */

export interface HealthResponse {
  status: string;
  service: string;
}

export type CriterionType = 'inclusion' | 'exclusion';

export type EligibilityStatus = 'Eligible' | 'Not Eligible' | 'More Information Required';

export type CriterionMatchStatus = 'Met' | 'Unmet' | 'Unknown' | 'Contradicted';

export interface PDFUploadResponse {
  trial_id: string;
  filename: string;
  status: string;
  file_size_bytes?: number;
}

export interface ExtractedCriterion {
  criterion_id: string;
  type: CriterionType;
  text: string;
  source_page?: number;
  trial_id?: string;
  category?: string;
  structured_rule?: string;
  raw_text?: string;
  page_number?: number;
}

export interface ProtocolExtractionResponse {
  trial_id: string;
  trial_title: string;
  trial_identifier?: string;
  inclusion_criteria: ExtractedCriterion[];
  exclusion_criteria: ExtractedCriterion[];
  other_requirements: string[];
  processing_status: string;
  total_pages_analyzed?: number;
  error_message?: string;
}

export interface ProtocolCriterion {
  criterion_id: string;
  type: CriterionType;
  category?: string;
  raw_text: string;
  structured_rule?: string;
  page_number?: number;
}

export interface ProtocolSummary {
  protocol_id: string;
  nct_id?: string;
  title: string;
  phase?: string;
  indication?: string;
  inclusion_criteria: ProtocolCriterion[];
  exclusion_criteria: ProtocolCriterion[];
}

export interface RAGIndexRequest {
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface RAGIndexResponse {
  trial_id: string;
  status: string;
  chunks_created: number;
  embedding_dimension: number;
}

export interface RAGSearchRequest {
  query: string;
  top_k?: number;
}

export interface RAGSearchResult {
  chunk_id: string;
  trial_id: string;
  text: string;
  page_number?: number;
  section?: string;
  criterion_type?: string;
  similarity_score: number;
}

export interface RAGSearchResponse {
  trial_id: string;
  query: string;
  results: RAGSearchResult[];
}

export interface RAGStatusResponse {
  trial_id: string;
  is_indexed: boolean;
}

export interface MedicalCondition {
  condition_name: string;
  icd10_code?: string;
  status: string;
  diagnosed_date?: string;
}

export interface Medication {
  drug_name: string;
  dosage?: string;
  route?: string;
  frequency?: string;
  is_current: boolean;
}

export interface LabValue {
  test_name: string;
  value: number;
  unit: string;
  reference_range?: string;
}

export interface PatientProfile {
  patient_id: string;
  age: number;
  gender: string;
  primary_diagnosis: string;
  ecog_score?: number;
  conditions: MedicalCondition[];
  medications: Medication[];
  labs: LabValue[];
  clinical_notes_raw?: string;
}

export interface EvidenceTrace {
  criterion_id: string;
  criterion_type: CriterionType;
  criterion_text: string;
  patient_fact_summary: string;
  citation_source: string;
  confidence_score: number;
  reasoning: string;
}

export interface ContradictionAlert {
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  description: string;
  conflicting_factors: string[];
  suggested_action?: string;
}

export interface CriterionEvaluationResult {
  criterion_id: string;
  criterion_type: CriterionType;
  status: CriterionMatchStatus;
  evidence: EvidenceTrace;
  is_disqualifying: boolean;
}

export interface EligibilityDecision {
  evaluation_id: string;
  protocol_id: string;
  patient_id: string;
  final_status: EligibilityStatus;
  summary_rationale: string;
  contradictions_detected: ContradictionAlert[];
  criteria_evaluations: CriterionEvaluationResult[];
  traceable_evidence: EvidenceTrace[];
}

export interface WorkflowStep {
  id: string;
  name: string;
  role: string;
  description: string;
  status: 'pending' | 'active' | 'completed';
}

// ==============================================================================
// MODULE 5 — INCLUSION MATCHING AGENT TYPES
// ==============================================================================

export type InclusionMatchResult = 'satisfied' | 'unsatisfied' | 'unknown';

export interface PatientEvidenceItem {
  field: string;
  value: any;
  source: string;
}

export interface ProtocolEvidenceItem {
  text: string;
  source_page?: number;
  trial_id?: string;
}

export interface InclusionCriterionEvaluation {
  criterion_id: string;
  criterion_text: string;
  result: InclusionMatchResult;
  reason: string;
  patient_evidence?: PatientEvidenceItem | null;
  protocol_evidence?: ProtocolEvidenceItem | null;
  missing_information: string[];
  confidence_score: number;
}

export interface InclusionSummary {
  total: number;
  satisfied: number;
  unsatisfied: number;
  unknown: number;
}

export interface InclusionEvaluationResponse {
  trial_id: string;
  patient_profile_id: string;
  overall_inclusion_status: InclusionMatchResult;
  criteria_results: InclusionCriterionEvaluation[];
  summary: InclusionSummary;
  evaluated_at: string;
}

// ==============================================================================
// MODULE 6 — EXCLUSION DETECTION AGENT TYPES
// ==============================================================================

export type ExclusionMatchResult = 'triggered' | 'not_triggered' | 'unknown';

export interface ExclusionCriterionEvaluation {
  criterion_id: string;
  criterion_text: string;
  result: ExclusionMatchResult;
  reason: string;
  patient_evidence?: PatientEvidenceItem | null;
  protocol_evidence?: ProtocolEvidenceItem | null;
  missing_information: string[];
  confidence_score: number;
}

export interface ExclusionSummary {
  total: number;
  triggered: number;
  not_triggered: number;
  unknown: number;
}

export interface ExclusionEvaluationResponse {
  trial_id: string;
  patient_profile_id: string;
  overall_exclusion_status: ExclusionMatchResult;
  criteria_results: ExclusionCriterionEvaluation[];
  summary: ExclusionSummary;
  evaluated_at: string;
}

// ==============================================================================
// MODULE 7 — CONTRADICTIONS & SILENT EXCLUSIONS TYPES
// ==============================================================================

export type ContradictionSeverity = 'low' | 'medium' | 'high' | 'critical';
export type ContradictionCategory =
  | 'internal_patient_conflict'
  | 'protocol_criteria_conflict'
  | 'medication_contraindication'
  | 'status_negation_conflict';

export type SilentExclusionCategory =
  | 'prohibited_co_medication'
  | 'latent_organ_toxicity'
  | 'device_implant'
  | 'undiagnosed_surrogate'
  | 'biopsy_procedure_risk';

export interface ContradictionAlert {
  contradiction_id: string;
  category: ContradictionCategory;
  severity: ContradictionSeverity;
  title: string;
  description: string;
  conflicting_facts: string[];
  patient_evidence: PatientEvidenceItem[];
  protocol_evidence?: ProtocolEvidenceItem | null;
  clinical_risk_rationale: string;
  suggested_reconciliation?: string | null;
  is_disqualifying: boolean;
}

export interface SilentExclusionTrigger {
  trigger_id: string;
  name: string;
  category: SilentExclusionCategory;
  clinical_rationale: string;
  affected_protocol_procedures: string[];
  patient_evidence?: PatientEvidenceItem | null;
  severity: ContradictionSeverity;
  is_hard_disqualification: boolean;
}

export interface ContradictionSummary {
  total_contradictions: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  total_silent_exclusions: number;
  disqualifying_count: number;
}

export interface ContradictionEvaluationResponse {
  trial_id: string;
  patient_profile_id: string;
  clinical_safety_verdict: string;
  has_critical_conflicts: boolean;
  has_silent_exclusions: boolean;
  summary: ContradictionSummary;
  contradictions: ContradictionAlert[];
  silent_exclusions: SilentExclusionTrigger[];
  evaluated_at: string;
}

// ==============================================================================
// MODULE 8 — DECISION / REVIEWER AGENT TYPES
// ==============================================================================

export type FinalEligibilityDecision =
  | 'ELIGIBLE'
  | 'NOT_ELIGIBLE'
  | 'MORE_INFORMATION_REQUIRED';

export interface DecisionFactor {
  type: 'inclusion' | 'exclusion' | 'contradiction' | 'silent_exclusion';
  criterion_id?: string | null;
  criterion_text?: string | null;
  status: string;
  reason: string;
  protocol_page?: number | null;
  protocol_evidence?: ProtocolEvidenceItem | null;
  patient_field?: string | null;
  patient_value?: any;
  patient_evidence?: PatientEvidenceItem | null;
}

export interface FinalEligibilitySummary {
  final_decision: FinalEligibilityDecision;
  inclusion_satisfied_count: number;
  inclusion_unsatisfied_count: number;
  inclusion_unknown_count: number;
  exclusion_triggered_count: number;
  exclusion_not_triggered_count: number;
  exclusion_unknown_count: number;
  contradictions_count: number;
  silent_exclusions_count: number;
  disqualifying_factors_count: number;
  missing_items_count: number;
}

export interface FinalEvaluationResponse {
  assessment_id?: string | null;
  trial_id: string;
  patient_profile_id: string;
  final_decision: FinalEligibilityDecision;
  decision_label: string;
  summary: FinalEligibilitySummary;
  inclusion_summary: InclusionSummary;
  exclusion_summary: ExclusionSummary;
  contradiction_summary?: ContradictionSummary | null;
  missing_information: string[];
  decision_factors: DecisionFactor[];
  protocol_evidence: ProtocolEvidenceItem[];
  patient_evidence: PatientEvidenceItem[];
  explanation: string;
  evaluated_at: string;
}

export interface PatientDemographics {
  age?: number | null;
  sex?: string | null;
  height?: number | null;
  weight?: number | null;
  bmi?: number | null;
  pregnancy_status?: string | null;
  breastfeeding_status?: boolean | null;
}

export interface NormalizedCondition {
  name: string;
  normalized_name: string;
  icd10_code?: string | null;
  status: string;
  diagnosed_date?: string | null;
  source: string;
}

export interface NormalizedMedication {
  name: string;
  normalized_name: string;
  dose?: string | null;
  unit?: string | null;
  frequency?: string | null;
  route?: string | null;
  is_current: boolean;
  start_date?: string | null;
  end_date?: string | null;
  source: string;
}

export interface NormalizedLabValue {
  name: string;
  normalized_name: string;
  value: number;
  unit: string;
  original_unit: string;
  reference_range?: string | null;
  normalization_status?: string;
  source: string;
  source_document?: string;
  original_field?: string;
}

export interface NormalizedAllergy {
  allergen: string;
  normalized_allergen: string;
  reaction?: string | null;
  severity?: string | null;
  source: string;
  source_document?: string;
  original_field?: string;
  substance?: string;
}

export interface NormalizedVitalSigns {
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  heart_rate?: number | null;
  spo2_percent?: number | null;
  unit?: string | null;
  source?: string;
  source_document?: string;
  original_field?: string;
}

export interface MissingInformation {
  field: string;
  status: string;
  category: string;
  description: string;
}

export interface StructuredPatientProfile {
  patient_profile_id: string;
  profile_status: string;
  created_at?: string;
  demographics: PatientDemographics;
  conditions: NormalizedCondition[];
  medical_history: NormalizedCondition[];
  medications: NormalizedMedication[];
  lab_values: NormalizedLabValue[];
  allergies: NormalizedAllergy[];
  vital_signs?: NormalizedVitalSigns | null;
  missing_information: MissingInformation[];
  clinical_notes_raw?: string | null;
  metadata?: Record<string, any>;
  clinical_status?: {
    ecog_performance_status?: number | null;
    active_serious_infection?: boolean | null;
    uncontrolled_cardiac_disease?: boolean | null;
    [key: string]: any;
  } | null;
  treatment_history?: {
    recent_systemic_anticancer_therapy?: boolean | null;
    investigational_therapy_hypersensitivity?: boolean | null;
    severe_hypersensitivity_to_investigational_therapy?: boolean | null;
    [key: string]: any;
  } | null;
}

// ==============================================================================
// MODULE 9 — LANGGRAPH WORKFLOW ENGINE TYPES (Python FastAPI /api/v1/workflow)
// ==============================================================================

export type WorkflowInclusionStatus = 'PASS' | 'FAIL' | 'UNKNOWN';
export type WorkflowExclusionStatus = 'TRIGGERED' | 'CLEAR' | 'UNKNOWN';
export type WorkflowContradictionType =
  | 'PROTOCOL_CONTRADICTION'
  | 'PATIENT_FACT_CONTRADICTION'
  | 'ASSESSMENT_CONTRADICTION'
  | 'SILENT_EXCLUSION'
  | 'EVIDENCE_CONFLICT';
export type WorkflowContradictionSeverity = 'INFO' | 'WARNING' | 'CRITICAL';

export interface FastAPILabValue {
  value?: number | null;
  unit?: string | null;
  reference_range?: string | null;
}

export interface FastAPILabs {
  egfr?: FastAPILabValue | null;
  anc?: FastAPILabValue | null;
  platelets?: FastAPILabValue | null;
  hemoglobin?: FastAPILabValue | null;
  ast?: FastAPILabValue | null;
  alt?: FastAPILabValue | null;
  bilirubin?: FastAPILabValue | null;
  other_labs?: Record<string, FastAPILabValue>;
}

export interface FastAPIPatientProfile {
  patient_profile_id: string;
  demographics?: {
    age?: number | null;
    sex?: string | null;
    pregnancy_status?: string | null;
    breastfeeding_status?: boolean | null;
    height_cm?: number | null;
    weight_kg?: number | null;
  };
  conditions?: Array<{
    name: string;
    status?: string | null;
    documented?: boolean;
    source_provenance?: string | null;
  }>;
  clinical_status?: {
    ecog_performance_status?: number | null;
    active_serious_infection?: boolean | null;
    uncontrolled_cardiac_disease?: boolean | null;
  };
  labs?: FastAPILabs;
  vital_signs?: {
    blood_pressure?: { systolic?: number | null; diastolic?: number | null; unit?: string } | null;
    heart_rate?: number | null;
    temperature_c?: number | null;
  } | null;
  allergies?: Array<{ substance: string; severity?: string | null; documented?: boolean }>;
  medications?: Array<{ name: string; dose?: string | null; frequency?: string | null; status?: string | null }>;
  treatment_history?: {
    recent_systemic_anticancer_therapy?: boolean | null;
    prior_therapies?: string[];
    last_treatment_date?: string | null;
  };
}

export interface WorkflowEvaluateRequest {
  trial_id: string;
  patient_profile: FastAPIPatientProfile;
  reference_date?: string | null;
  protocol_evidence?: RetrievedWorkflowChunk[];
}

export interface RetrievedWorkflowChunk {
  chunk_id: string;
  trial_id: string;
  criterion_id: string;
  criterion_type: string;
  text: string;
  score: number;
  source_page: number;
  source_document: string;
  source_excerpt?: string | null;
  section?: string | null;
  metadata?: Record<string, any>;
}

export interface WorkflowInclusionCriterion {
  criterion_id: string;
  trial_id: string;
  status: WorkflowInclusionStatus;
  criterion_text: string;
  patient_value?: any;
  expected_requirement: string;
  rationale: string;
  evidence?: Record<string, any> | string | null;
  source_page: number;
  source_document: string;
  source_excerpt?: string | null;
}

export interface WorkflowInclusionAssessment {
  trial_id: string;
  patient_profile_id: string;
  overall_status: WorkflowInclusionStatus;
  criteria: WorkflowInclusionCriterion[];
  missing_information: string[];
  warnings: string[];
}

export interface WorkflowExclusionCriterion {
  criterion_id: string;
  trial_id: string;
  status: WorkflowExclusionStatus;
  criterion_text: string;
  patient_value?: any;
  exclusion_requirement: string;
  rationale: string;
  evidence?: Record<string, any> | string | null;
  source_page: number;
  source_document: string;
  source_excerpt?: string | null;
}

export interface WorkflowExclusionAssessment {
  trial_id: string;
  patient_profile_id: string;
  overall_status: WorkflowExclusionStatus;
  criteria: WorkflowExclusionCriterion[];
  missing_information: string[];
  warnings: string[];
}

export interface WorkflowContradictionFinding {
  finding_id: string;
  trial_id: string;
  contradiction_type: WorkflowContradictionType;
  severity: WorkflowContradictionSeverity;
  title: string;
  description: string;
  criterion_ids: string[];
  patient_fields: string[];
  evidence?: Record<string, any> | any[] | string | null;
  recommended_action: string;
}

export interface WorkflowContradictionAssessment {
  trial_id: string;
  patient_profile_id: string;
  findings: WorkflowContradictionFinding[];
  checked_criteria: string[];
  warnings: string[];
  has_critical_findings: boolean;
}

export interface WorkflowDecisionEvidence {
  criterion_id: string;
  criterion_text: string;
  patient_value?: any;
  status: string;
  source_page: number;
  source_document: string;
  source_excerpt?: string | null;
  originating_agent: string;
}

export interface WorkflowDecisionAssessment {
  trial_id: string;
  patient_profile_id: string;
  final_status: FinalEligibilityDecision;
  requires_human_review: boolean;
  primary_reasons: string[];
  decision_evidence: WorkflowDecisionEvidence[];
  unresolved_information: string[];
  contradiction_findings: WorkflowContradictionFinding[];
  warnings: string[];
  disclaimer: string;
}

export interface WorkflowStateResponse {
  assessment_id?: string | null;
  trial_id: string;
  patient_profile_id: string;
  protocol_evidence: RetrievedWorkflowChunk[];
  inclusion_assessment?: WorkflowInclusionAssessment | null;
  exclusion_assessment?: WorkflowExclusionAssessment | null;
  contradiction_assessment?: WorkflowContradictionAssessment | null;
  decision_assessment?: WorkflowDecisionAssessment | null;
  warnings: string[];
  errors: string[];
  current_step: string;
}

// ==============================================================================
// MODULE 10 — PERSISTED ASSESSMENT HISTORY TYPES (FastAPI /api/v1/assessments)
// Matches backend/app/schemas/assessment.py
// ==============================================================================

export interface AssessmentSummaryResponse {
  assessment_id: string;
  trial_id: string;
  patient_profile_id: string;
  reference_date?: string | null;
  workflow_status: string;
  final_decision?: FinalEligibilityDecision | null;
  current_step?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  has_errors: boolean;
  error_count: number;
  warning_count: number;
}

export interface AssessmentTraceResponse {
  sequence: number;
  stage: string;
  status?: string | null;
  payload?: Record<string, any> | null;
  created_at?: string | null;
}

export interface AssessmentDetailResponse extends AssessmentSummaryResponse {
  warnings: string[];
  errors: string[];
  snapshot?: Record<string, any> | null;
  traces: AssessmentTraceResponse[];
}



