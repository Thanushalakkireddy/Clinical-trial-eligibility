/**
 * Adapter mapping between the Python LangGraph workflow engine (FastAPI
 * POST /api/v1/workflow/evaluate -> WorkflowStateResponse) and the frontend's
 * existing FinalEvaluationResponse contract consumed by the result components.
 *
 * SAFETY: This adapter only re-shapes data returned by the authoritative backend.
 * It never invents missing clinical facts, thresholds, or criterion evidence.
 */

import {
  ContradictionSummary,
  DecisionFactor,
  ExclusionSummary,
  FastAPILabValue,
  FastAPIPatientProfile,
  FinalEvaluationResponse,
  FinalEligibilitySummary,
  InclusionSummary,
  PatientEvidenceItem,
  ProtocolEvidenceItem,
  StructuredPatientProfile,
  WorkflowDecisionEvidence,
  WorkflowStateResponse,
} from '../types';

const DECISION_LABELS: Record<string, string> = {
  ELIGIBLE: 'Eligible for Clinical Trial',
  NOT_ELIGIBLE: 'Not Eligible for Clinical Trial',
  MORE_INFORMATION_REQUIRED: 'More Information Required',
};

/**
 * Map a locally stored StructuredPatientProfile (Express patient model) into the
 * FastAPI PatientProfile request schema. Reads clinical_status / treatment_history
 * from their top-level keys with a legacy `metadata` fallback for older records.
 */
export function mapToFastAPIPatientProfile(
  patient: StructuredPatientProfile
): FastAPIPatientProfile {
  const demographics = patient.demographics ?? {};
  const metadata = patient.metadata ?? {};
  const clinicalStatus = patient.clinical_status ?? {};
  const treatmentHistory = patient.treatment_history ?? {};

  const labs: FastAPIPatientProfile['labs'] = {};
  for (const lab of patient.lab_values ?? []) {
    const normalized = (lab.normalized_name || lab.name || '').toLowerCase();
    const value: FastAPILabValue = {
      value: lab.value ?? null,
      unit: lab.unit ?? null,
      reference_range: lab.reference_range ?? null,
    };
    if (normalized === 'egfr' || normalized.includes('gfr')) labs.egfr = value;
    else if (normalized === 'anc' || normalized.includes('neutrophil')) labs.anc = value;
    else if (normalized.includes('platelet')) labs.platelets = value;
    else if (normalized.includes('hemoglobin') || normalized.includes('haemoglobin'))
      labs.hemoglobin = value;
    else if (normalized === 'ast' || normalized.includes('aspartate')) labs.ast = value;
    else if (normalized === 'alt' || normalized.includes('alanine')) labs.alt = value;
    else if (normalized.includes('bilirubin')) labs.bilirubin = value;
    else {
      labs.other_labs = labs.other_labs ?? {};
      labs.other_labs[normalized.replace(/[^a-z0-9_]/g, '_') || 'lab'] = value;
    }
  }

  const profile: FastAPIPatientProfile = {
    patient_profile_id: patient.patient_profile_id,
    demographics: {
      age: demographics.age ?? null,
      sex: demographics.sex ?? null,
      pregnancy_status: demographics.pregnancy_status ?? null,
      breastfeeding_status: demographics.breastfeeding_status ?? null,
      height_cm: demographics.height ?? null,
      weight_kg: demographics.weight ?? null,
    },
    conditions: (patient.conditions ?? []).map((c) => ({
      name: c.normalized_name || c.name,
      status: c.status ?? 'active',
      documented: true,
      source_provenance: c.source ?? null,
    })),
    clinical_status: {
      ecog_performance_status:
        clinicalStatus.ecog_performance_status ?? metadata.ecog_score ?? null,
      active_serious_infection:
        clinicalStatus.active_serious_infection ?? metadata.active_serious_infection ?? null,
      uncontrolled_cardiac_disease:
        clinicalStatus.uncontrolled_cardiac_disease ??
        metadata.uncontrolled_cardiac_disease ??
        null,
    },
    labs,
    allergies: (patient.allergies ?? []).map((a) => ({
      substance: a.normalized_allergen || a.substance || a.allergen || 'Unknown allergen',
      severity: a.severity ?? null,
      documented: true,
    })),
    medications: (patient.medications ?? []).map((m) => ({
      name: m.normalized_name || m.name,
      dose: m.dose ?? null,
      frequency: m.frequency ?? null,
      status: m.is_current ? 'active' : 'historical',
    })),
    treatment_history: {
      recent_systemic_anticancer_therapy:
        treatmentHistory.recent_systemic_anticancer_therapy ??
        metadata.recent_systemic_anticancer_therapy ??
        null,
      prior_therapies: treatmentHistory.prior_therapies ?? [],
      last_treatment_date: treatmentHistory.last_treatment_date ?? null,
    },
  };

  if (patient.vital_signs) {
    const vs = patient.vital_signs;
    profile.vital_signs = {
      blood_pressure:
        vs.systolic_bp != null || vs.diastolic_bp != null
          ? { systolic: vs.systolic_bp ?? null, diastolic: vs.diastolic_bp ?? null, unit: 'mmHg' }
          : null,
      heart_rate: vs.heart_rate ?? null,
      temperature_c: null,
    };
  }

  return profile;
}

function inferPatientField(
  evidence: WorkflowDecisionEvidence,
  missingFields: string[]
): string | null {
  const text = `${evidence.criterion_text} ${evidence.source_excerpt ?? ''}`.toLowerCase();
  const matches = missingFields.filter((field) => {
    const leaf = field.split('.').pop();
    if (!leaf || leaf.length <= 3) return false;
    return text.includes(leaf.replace(/_/g, ' '));
  });
  return matches.length === 1 ? matches[0] : null;
}

function buildFactorReason(evidence: WorkflowDecisionEvidence): string {
  const valueStr =
    evidence.patient_value != null
      ? ` Observed patient value: ${JSON.stringify(evidence.patient_value)}.`
      : '';
  switch (evidence.status) {
    case 'PASS':
      return `Inclusion criterion satisfied.${valueStr}`;
    case 'FAIL':
      return `Inclusion criterion not satisfied.${valueStr}`;
    case 'TRIGGERED':
      return `Exclusion criterion triggered.${valueStr}`;
    case 'CLEAR':
      return `No exclusion risk; criterion clear.${valueStr}`;
    case 'SILENT_EXCLUSION':
      return `Confirmed silent exclusion identified: ${evidence.criterion_text}.`;
    case 'UNKNOWN':
      return `Unable to evaluate; required patient information is missing.${valueStr}`;
    default:
      return evidence.criterion_text || evidence.status;
  }
}

function mapEvidenceToDecisionFactor(
  evidence: WorkflowDecisionEvidence,
  missingFields: string[]
): { type: DecisionFactor['type']; status: DecisionFactor['status'] } {
  const originating = evidence.originating_agent;
  let type: DecisionFactor['type'];
  if (originating === 'InclusionMatchingAgent') type = 'inclusion';
  else if (originating === 'ExclusionDetectionAgent') type = 'exclusion';
  else if (originating === 'ContradictionAgent' && evidence.status === 'SILENT_EXCLUSION')
    type = 'silent_exclusion';
  else type = 'contradiction';

  let status: DecisionFactor['status'] = evidence.status;
  if (evidence.status === 'PASS') status = 'satisfied';
  else if (evidence.status === 'FAIL') status = 'unsatisfied';
  else if (evidence.status === 'TRIGGERED') status = 'triggered';
  else if (evidence.status === 'CLEAR') status = 'not_triggered';
  else if (evidence.status === 'UNKNOWN') status = 'unknown';

  return { type, status };
}

/**
 * Build the final decision factors, enriching UNKNOWN factors with the exact
 * missing patient field the backend listed so the frontend can link them.
 */
function buildDecisionFactors(
  workflow: WorkflowStateResponse,
  missingFields: string[]
): DecisionFactor[] {
  const decision = workflow.decision_assessment;
  const factors: DecisionFactor[] = [];

  for (const evidence of decision?.decision_evidence ?? []) {
    const { type, status } = mapEvidenceToDecisionFactor(evidence, missingFields);
    let criterionId = evidence.criterion_id;
    if (criterionId === 'PROTOCOL-VALIDATION-ERROR') {
      criterionId = 'PROTOCOL-VALIDATION-REQUIRED';
    }
    factors.push({
      type,
      criterion_id: criterionId,
      criterion_text: evidence.criterion_text,
      status,
      reason: buildFactorReason(evidence),
      protocol_page: evidence.source_page,
      protocol_evidence: evidence.source_excerpt
        ? { text: evidence.source_excerpt, source_page: evidence.source_page, trial_id: workflow.trial_id }
        : null,
      patient_field: status === 'unknown' ? inferPatientField(evidence, missingFields) : null,
      patient_value: evidence.patient_value,
    });
  }

  // Include critical/warning contradiction findings and silent exclusions as factors
  for (const finding of workflow.contradiction_assessment?.findings ?? []) {
    if (factors.some((f) => f.criterion_id === finding.finding_id)) continue;
    const isSilent = finding.contradiction_type === 'SILENT_EXCLUSION';
    factors.push({
      type: isSilent ? 'silent_exclusion' : 'contradiction',
      criterion_id: finding.criterion_ids[0] || finding.finding_id,
      criterion_text: finding.title,
      status: finding.severity === 'CRITICAL' ? 'critical_conflict' : finding.severity === 'WARNING' ? 'warning' : 'info',
      reason: `${finding.description}${finding.recommended_action ? ` Recommended action: ${finding.recommended_action}` : ''}`,
      patient_field: finding.patient_fields[0] ?? null,
      protocol_evidence: null,
      patient_value: null,
    });
  }

  // Protocol validation failure produced by the workflow (retrieval errors, zero criteria)
  if ((workflow.errors?.length ?? 0) > 0 && !decision) {
    factors.push({
      type: 'contradiction',
      criterion_id: 'PROTOCOL-VALIDATION-REQUIRED',
      criterion_text: 'Protocol Source of Truth & Criteria Verification',
      status: 'unknown',
      reason: workflow.errors[0],
      protocol_page: null,
      protocol_evidence: null,
      patient_field: null,
      patient_value: null,
    });
  } else if (
    decision?.decision_evidence.some((e) => e.criterion_id === 'PROTOCOL-VALIDATION-ERROR')
  ) {
    factors.push({
      type: 'contradiction',
      criterion_id: 'PROTOCOL-VALIDATION-REQUIRED',
      criterion_text: 'Protocol Source of Truth & Criteria Verification',
      status: 'unknown',
      reason: decision?.primary_reasons?.[0] ?? 'Protocol validation failed: zero evaluable criteria.',
      protocol_page: null,
      protocol_evidence: null,
      patient_field: null,
      patient_value: null,
    });
  }

  return factors;
}

/**
 * Convert a WorkflowStateResponse from the Python engine into the frontend's
 * FinalEvaluationResponse so all existing result components render unchanged.
 */
export function mapWorkflowStateToFinalEvaluation(
  workflow: WorkflowStateResponse
): FinalEvaluationResponse {
  const inclusion = workflow.inclusion_assessment;
  const exclusion = workflow.exclusion_assessment;
  const findings = workflow.contradiction_assessment?.findings ?? [];
  const decision = workflow.decision_assessment;

  const protocolEvidence: ProtocolEvidenceItem[] = (workflow.protocol_evidence ?? []).map(
    (chunk) => ({
      text: chunk.text,
      source_page: chunk.source_page,
      trial_id: chunk.trial_id,
    })
  );

  const missingInfoSet = new Set<string>();
  (inclusion?.missing_information ?? []).forEach((f) => missingInfoSet.add(f));
  (exclusion?.missing_information ?? []).forEach((f) => missingInfoSet.add(f));
  (decision?.unresolved_information ?? []).forEach((f) => missingInfoSet.add(f));
  const missingInformation = Array.from(missingInfoSet);

  const inclusionSummary: InclusionSummary = {
    total: inclusion?.criteria.length ?? 0,
    satisfied: (inclusion?.criteria ?? []).filter((c) => c.status === 'PASS').length,
    unsatisfied: (inclusion?.criteria ?? []).filter((c) => c.status === 'FAIL').length,
    unknown: (inclusion?.criteria ?? []).filter((c) => c.status === 'UNKNOWN').length,
  };

  const exclusionSummary: ExclusionSummary = {
    total: exclusion?.criteria.length ?? 0,
    triggered: (exclusion?.criteria ?? []).filter((c) => c.status === 'TRIGGERED').length,
    not_triggered: (exclusion?.criteria ?? []).filter((c) => c.status === 'CLEAR').length,
    unknown: (exclusion?.criteria ?? []).filter((c) => c.status === 'UNKNOWN').length,
  };

  const silentExclusions = findings.filter((f) => f.contradiction_type === 'SILENT_EXCLUSION');
  const contradictionSummary: ContradictionSummary = {
    total_contradictions: findings.filter((f) => f.contradiction_type !== 'SILENT_EXCLUSION').length,
    critical: findings.filter((f) => f.severity === 'CRITICAL').length,
    high: findings.filter((f) => f.severity === 'WARNING').length,
    medium: 0,
    low: findings.filter((f) => f.severity === 'INFO').length,
    total_silent_exclusions: silentExclusions.length,
    disqualifying_count: silentExclusions.length,
  };

  const decisionFactors = buildDecisionFactors(workflow, missingInformation);

  const disqualifyingCount = decisionFactors.filter(
    (f) => f.status === 'unsatisfied' || f.status === 'triggered' || f.status === 'critical_conflict'
  ).length;

  const finalDecision = decision?.final_status ?? 'MORE_INFORMATION_REQUIRED';

  const summary: FinalEligibilitySummary = {
    final_decision: finalDecision,
    inclusion_satisfied_count: inclusionSummary.satisfied,
    inclusion_unsatisfied_count: inclusionSummary.unsatisfied,
    inclusion_unknown_count: inclusionSummary.unknown,
    exclusion_triggered_count: exclusionSummary.triggered,
    exclusion_not_triggered_count: exclusionSummary.not_triggered,
    exclusion_unknown_count: exclusionSummary.unknown,
    contradictions_count: contradictionSummary.total_contradictions,
    silent_exclusions_count: contradictionSummary.total_silent_exclusions,
    disqualifying_factors_count: disqualifyingCount,
    missing_items_count: missingInformation.length,
  };

  const primaryReasons = decision?.primary_reasons ?? [];
  const explanation =
    primaryReasons.length > 0
      ? primaryReasons.join(' ')
      : (workflow.errors?.length ?? 0) > 0
        ? workflow.errors.join(' ')
        : (decision?.disclaimer ?? '');

  const patientEvidence: PatientEvidenceItem[] = [];
  const seenFields = new Set<string>();
  const ingestEvidence = (evidence: Record<string, unknown> | string | null | undefined) => {
    if (!evidence || typeof evidence === 'string') return;
    for (const [field, value] of Object.entries(evidence)) {
      const isPatientField = field.includes('.') || field === 'conditions';
      if (!isPatientField) continue;
      if (seenFields.has(field)) continue;
      seenFields.add(field);
      patientEvidence.push({ field, value: value as any, source: 'patient_json' });
    }
  };
  (inclusion?.criteria ?? []).forEach((c) => ingestEvidence(c.evidence));
  (exclusion?.criteria ?? []).forEach((c) => ingestEvidence(c.evidence));

  return {
    assessment_id: workflow.assessment_id ?? null,
    trial_id: workflow.trial_id,
    patient_profile_id: workflow.patient_profile_id,
    final_decision: finalDecision,
    decision_label: DECISION_LABELS[finalDecision] ?? finalDecision,
    summary,
    inclusion_summary: inclusionSummary,
    exclusion_summary: exclusionSummary,
    contradiction_summary: contradictionSummary,
    missing_information: missingInformation,
    decision_factors: decisionFactors,
    protocol_evidence: protocolEvidence,
    patient_evidence: patientEvidence,
    explanation,
    evaluated_at: new Date().toISOString(),
  };
}