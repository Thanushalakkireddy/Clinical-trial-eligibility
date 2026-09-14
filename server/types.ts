export type CriterionType = 'inclusion' | 'exclusion';

export type InclusionMatchResult = 'satisfied' | 'unsatisfied' | 'unknown';
export type ExclusionMatchResult = 'triggered' | 'not_triggered' | 'unknown';

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

export interface ExtractedCriterion {
  criterion_id: string;
  type: CriterionType;
  text: string;
  source_page?: number;
  trial_id?: string;
  category?: string | null;
  structured_rule?: string | null;
  raw_text?: string;
  page_number?: number;
  source_document?: string;
  source_excerpt?: string;
  originating_agent?: string;
}

export interface ProtocolExtractionResponse {
  trial_id: string;
  trial_title: string;
  trial_identifier?: string | null;
  inclusion_criteria: ExtractedCriterion[];
  exclusion_criteria: ExtractedCriterion[];
  other_requirements: string[];
  processing_status: string;
  total_pages_analyzed?: number;
  error_message?: string | null;
}

export interface PatientEvidence {
  field: string;
  value: any;
  source: string;
}

export interface ProtocolEvidence {
  text: string;
  source_page?: number;
  trial_id?: string;
}

export interface InclusionCriterionEvaluation {
  criterion_id: string;
  criterion_text: string;
  result: InclusionMatchResult;
  reason: string;
  patient_evidence?: PatientEvidence | null;
  protocol_evidence?: ProtocolEvidence | null;
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

export interface ExclusionCriterionEvaluation {
  criterion_id: string;
  criterion_text: string;
  result: ExclusionMatchResult;
  reason: string;
  patient_evidence?: PatientEvidence | null;
  protocol_evidence?: ProtocolEvidence | null;
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

export interface RAGChunk {
  chunk_id: string;
  trial_id: string;
  text: string;
  page_number?: number;
  section?: string | null;
  criterion_type?: string | null;
  metadata?: Record<string, any>;
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

export interface RAGIndexResponse {
  trial_id: string;
  status: string;
  chunks_created: number;
  embedding_dimension: number;
}

// Module 7 Types
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
  patient_evidence: PatientEvidence[];
  protocol_evidence?: ProtocolEvidence | null;
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
  patient_evidence?: PatientEvidence | null;
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

// Module 8 Types
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
  protocol_evidence?: ProtocolEvidence | null;
  patient_field?: string | null;
  patient_value?: any;
  patient_evidence?: PatientEvidence | null;
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
  protocol_evidence: ProtocolEvidence[];
  patient_evidence: PatientEvidence[];
  explanation: string;
  evaluated_at: string;
}

