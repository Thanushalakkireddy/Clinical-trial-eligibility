import {
  InclusionEvaluationResponse,
  ExclusionEvaluationResponse,
  ContradictionEvaluationResponse,
  FinalEvaluationResponse,
  FinalEligibilityDecision,
  FinalEligibilitySummary,
  DecisionFactor,
  ProtocolEvidence,
  PatientEvidence,
  StructuredPatientProfile,
  ProtocolExtractionResponse,
} from './types';
import { dataStore } from './dataStore';

/**
 * Module 8: Deterministic Decision Reviewer.
 * 
 * Synthesizes:
 *   1. Module 5 — Inclusion Matching
 *   2. Module 6 — Exclusion Detection
 *   3. Module 7 — Contradictions & Silent Exclusions
 * 
 * Rules:
 *   RULE A (NOT_ELIGIBLE):
 *     - Any required inclusion is UNSATISFIED.
 *     - Any explicit exclusion is TRIGGERED.
 *     - Module 7 identifies a hard disqualifying silent exclusion or critical disqualification.
 *     - Priority: Confirmed disqualification overrides UNKNOWN status.
 * 
 *   RULE B (MORE_INFORMATION_REQUIRED):
 *     - Any required inclusion is UNKNOWN.
 *     - Any required exclusion is UNKNOWN.
 *     - Missing clinical information needed for evaluation.
 *     - Unresolved safety investigation warning without hard disqualifier.
 *     - Missing data must never be presumed satisfied or not triggered.
 * 
 *   RULE C (ELIGIBLE):
 *     - All required inclusion SATISFIED.
 *     - No exclusion TRIGGERED.
 *     - No hard silent exclusions.
 *     - Zero required items UNKNOWN.
 *     - No unresolved blocking safety conflicts.
 */
export function evaluateFinalEligibility(
  trialId: string,
  patientProfileId: string,
  inclusionResp: InclusionEvaluationResponse,
  exclusionResp: ExclusionEvaluationResponse,
  contradictionResp?: ContradictionEvaluationResponse | null,
  patientProfile?: StructuredPatientProfile | null,
  protocol?: ProtocolExtractionResponse | null
): FinalEvaluationResponse {
  const decisionFactors: DecisionFactor[] = [];
  const protocolEvidenceList: ProtocolEvidence[] = [];
  const patientEvidenceList: PatientEvidence[] = [];
  const missingInfoSet = new Set<string>();

  const protoKeys = new Set<string>();
  const patientKeys = new Set<string>();

  function addProtoEv(ev?: ProtocolEvidence | null) {
    if (!ev || !ev.text) return;
    const key = `${ev.text}_${ev.source_page}_${ev.trial_id}`;
    if (!protoKeys.has(key)) {
      protoKeys.add(key);
      protocolEvidenceList.push(ev);
    }
  }

  function addPatientEv(ev?: PatientEvidence | null) {
    if (!ev || !ev.field) return;
    const key = `${ev.field}_${String(ev.value)}_${ev.source}`;
    if (!patientKeys.has(key)) {
      patientKeys.add(key);
      patientEvidenceList.push(ev);
    }
  }

  // 1. Analyze Inclusion Criteria
  let incSatisfied = 0;
  let incUnsatisfied = 0;
  let incUnknown = 0;
  const unsatisfiedInclusions = [];
  const unknownInclusions = [];
  const satisfiedInclusions = [];

  for (const inc of inclusionResp.criteria_results || []) {
    if (inc.patient_evidence) addPatientEv(inc.patient_evidence);
    if (inc.protocol_evidence) addProtoEv(inc.protocol_evidence);
    for (const m of inc.missing_information || []) {
      missingInfoSet.add(m);
    }

    if (inc.result === 'satisfied') {
      incSatisfied++;
      satisfiedInclusions.push(inc);
    } else if (inc.result === 'unsatisfied') {
      incUnsatisfied++;
      unsatisfiedInclusions.push(inc);
    } else {
      incUnknown++;
      unknownInclusions.push(inc);
    }
  }

  // 2. Analyze Exclusion Criteria
  let excTriggered = 0;
  let excNotTriggered = 0;
  let excUnknown = 0;
  const triggeredExclusions = [];
  const unknownExclusions = [];
  const notTriggeredExclusions = [];

  for (const exc of exclusionResp.criteria_results || []) {
    if (exc.patient_evidence) addPatientEv(exc.patient_evidence);
    if (exc.protocol_evidence) addProtoEv(exc.protocol_evidence);
    for (const m of exc.missing_information || []) {
      missingInfoSet.add(m);
    }

    if (exc.result === 'triggered') {
      excTriggered++;
      triggeredExclusions.push(exc);
    } else if (exc.result === 'not_triggered') {
      excNotTriggered++;
      notTriggeredExclusions.push(exc);
    } else {
      excUnknown++;
      unknownExclusions.push(exc);
    }
  }

  // 3. Analyze Contradictions & Silent Exclusions
  const hardSilentExclusions = [];
  const disqualifyingContradictions = [];
  const safetyWarnings = [];

  if (contradictionResp) {
    for (const c of contradictionResp.contradictions || []) {
      if (c.patient_evidence) {
        c.patient_evidence.forEach(addPatientEv);
      }
      if (c.protocol_evidence) {
        addProtoEv(c.protocol_evidence);
      }
      if (c.is_disqualifying) {
        disqualifyingContradictions.push(c);
      } else if (c.severity === 'critical' || c.severity === 'high') {
        safetyWarnings.push(c);
      }
    }

    for (const s of contradictionResp.silent_exclusions || []) {
      if (s.patient_evidence) {
        addPatientEv(s.patient_evidence);
      }
      if (s.is_hard_disqualification) {
        hardSilentExclusions.push(s);
      } else {
        safetyWarnings.push(s);
      }
    }
  }

  // 4. Decision Adjudication
  const totalCriteriaEvaluated =
    (inclusionResp.criteria_results?.length || 0) + (exclusionResp.criteria_results?.length || 0);
  const trialRecord = dataStore.getTrial(trialId);
  const isValidationFailed =
    trialRecord?.processing_status === 'validation_failed' || totalCriteriaEvaluated === 0;

  const hasDisqualification =
    incUnsatisfied > 0 ||
    excTriggered > 0 ||
    disqualifyingContradictions.length > 0 ||
    hardSilentExclusions.length > 0;

  const hasUnknowns =
    incUnknown > 0 ||
    excUnknown > 0 ||
    missingInfoSet.size > 0 ||
    safetyWarnings.length > 0;

  let finalDecision: FinalEligibilityDecision;
  let decisionLabel: string;
  let explanation: string;

  if (isValidationFailed) {
    finalDecision = 'MORE_INFORMATION_REQUIRED';
    decisionLabel = 'More Information Required';
    explanation = `More information is required to evaluate eligibility for trial ${trialId}: The protocol document contains zero verifiable eligibility criteria (protocol validation requirement not met). An authentic clinical trial protocol containing inclusion and exclusion criteria must be provided.`;
    missingInfoSet.add('Clinical Trial Protocol Criteria (Inclusion and exclusion criteria from validated protocol)');
    decisionFactors.push({
      type: 'inclusion',
      criterion_id: 'PROTOCOL-VALIDATION-REQUIRED',
      criterion_text: 'Verified Clinical Trial Eligibility Protocol',
      status: 'unknown',
      reason:
        trialRecord?.error_message ||
        'The uploaded document does not contain verifiable clinical trial eligibility criteria. Non-protocol documents (e.g., resumes, invoices, general text) cannot be evaluated. An authentic clinical trial protocol PDF is required.',
      protocol_page: null,
      protocol_evidence: null,
      patient_field: null,
      patient_value: null,
      patient_evidence: null,
    });
  } else if (hasDisqualification) {
    finalDecision = 'NOT_ELIGIBLE';
    decisionLabel = 'Not Eligible';

    const reasons: string[] = [];

    for (const inc of unsatisfiedInclusions) {
      decisionFactors.push({
        type: 'inclusion',
        criterion_id: inc.criterion_id,
        criterion_text: inc.criterion_text,
        status: 'unsatisfied',
        reason: inc.reason,
        protocol_page: inc.protocol_evidence?.source_page || null,
        protocol_evidence: inc.protocol_evidence,
        patient_field: inc.patient_evidence?.field || null,
        patient_value: inc.patient_evidence?.value,
        patient_evidence: inc.patient_evidence,
      });
      reasons.push(`Inclusion criterion ${inc.criterion_id} is unsatisfied: ${inc.reason}`);
    }

    for (const exc of triggeredExclusions) {
      decisionFactors.push({
        type: 'exclusion',
        criterion_id: exc.criterion_id,
        criterion_text: exc.criterion_text,
        status: 'triggered',
        reason: exc.reason,
        protocol_page: exc.protocol_evidence?.source_page || null,
        protocol_evidence: exc.protocol_evidence,
        patient_field: exc.patient_evidence?.field || null,
        patient_value: exc.patient_evidence?.value,
        patient_evidence: exc.patient_evidence,
      });
      reasons.push(`Exclusion criterion ${exc.criterion_id} was triggered: ${exc.reason}`);
    }

    for (const se of hardSilentExclusions) {
      decisionFactors.push({
        type: 'silent_exclusion',
        criterion_id: se.trigger_id,
        criterion_text: se.name,
        status: 'triggered_hazard',
        reason: se.clinical_rationale,
        patient_field: se.patient_evidence?.field || null,
        patient_value: se.patient_evidence?.value,
        patient_evidence: se.patient_evidence,
      });
      reasons.push(`Latent silent hazard (${se.name}) detected: ${se.clinical_rationale}`);
    }

    for (const dc of disqualifyingContradictions) {
      decisionFactors.push({
        type: 'contradiction',
        criterion_id: dc.contradiction_id,
        criterion_text: dc.title,
        status: 'critical_conflict',
        reason: dc.description,
        patient_evidence: dc.patient_evidence[0] || null,
      });
      reasons.push(`Critical conflict: ${dc.title} - ${dc.description}`);
    }

    explanation = `The patient is Not Eligible for trial ${trialId} due to confirmed protocol disqualification. ${reasons.slice(0, 3).join(' ')}`;
  } else if (hasUnknowns) {
    finalDecision = 'MORE_INFORMATION_REQUIRED';
    decisionLabel = 'More Information Required';

    const moreReasons: string[] = [];

    for (const inc of unknownInclusions) {
      decisionFactors.push({
        type: 'inclusion',
        criterion_id: inc.criterion_id,
        criterion_text: inc.criterion_text,
        status: 'unknown',
        reason: inc.reason,
        protocol_page: inc.protocol_evidence?.source_page || null,
        protocol_evidence: inc.protocol_evidence,
      });
      moreReasons.push(`Inclusion requirement ${inc.criterion_id} cannot be verified (${inc.reason}).`);
    }

    for (const exc of unknownExclusions) {
      decisionFactors.push({
        type: 'exclusion',
        criterion_id: exc.criterion_id,
        criterion_text: exc.criterion_text,
        status: 'unknown',
        reason: exc.reason,
        protocol_page: exc.protocol_evidence?.source_page || null,
        protocol_evidence: exc.protocol_evidence,
      });
      moreReasons.push(`Exclusion requirement ${exc.criterion_id} cannot be evaluated (${exc.reason}).`);
    }

    for (const warn of safetyWarnings) {
      const title = (warn as any).title || (warn as any).name || 'Clinical Warning';
      const desc = (warn as any).description || (warn as any).clinical_rationale || '';
      decisionFactors.push({
        type: 'contradiction',
        criterion_id: (warn as any).contradiction_id || (warn as any).trigger_id || 'WARN-01',
        criterion_text: title,
        status: 'investigation_required',
        reason: desc,
      });
      moreReasons.push(`Safety warning requiring investigation: ${title}.`);
    }

    const missingStr = Array.from(missingInfoSet).slice(0, 4).join(', ') || 'essential clinical documentation';
    explanation = `More information is required to determine eligibility for trial ${trialId}. Essential protocol criteria remain unknown because documentation (${missingStr}) is missing. In accordance with clinical trial protocol safety principles, missing information cannot be presumed satisfied or non-triggered without verified records.`;
  } else if (incSatisfied > 0) {
    finalDecision = 'ELIGIBLE';
    decisionLabel = 'Eligible';

    for (const inc of satisfiedInclusions.slice(0, 3)) {
      decisionFactors.push({
        type: 'inclusion',
        criterion_id: inc.criterion_id,
        criterion_text: inc.criterion_text,
        status: 'satisfied',
        reason: inc.reason,
        protocol_page: inc.protocol_evidence?.source_page || null,
        protocol_evidence: inc.protocol_evidence,
        patient_field: inc.patient_evidence?.field || null,
        patient_value: inc.patient_evidence?.value,
        patient_evidence: inc.patient_evidence,
      });
    }

    for (const exc of notTriggeredExclusions.slice(0, 2)) {
      decisionFactors.push({
        type: 'exclusion',
        criterion_id: exc.criterion_id,
        criterion_text: exc.criterion_text,
        status: 'not_triggered',
        reason: exc.reason,
        protocol_page: exc.protocol_evidence?.source_page || null,
        protocol_evidence: exc.protocol_evidence,
        patient_field: exc.patient_evidence?.field || null,
        patient_value: exc.patient_evidence?.value,
        patient_evidence: exc.patient_evidence,
      });
    }

    explanation = `Eligible based on currently documented information. All ${incSatisfied} required inclusion criteria are satisfied, none of the ${excNotTriggered} exclusion criteria are triggered, no latent silent hazards were detected, and no required evaluation facts remain unknown.`;
  } else {
    finalDecision = 'MORE_INFORMATION_REQUIRED';
    decisionLabel = 'More Information Required';
    explanation = `More information is required for trial ${trialId}: No inclusion criteria were verified as satisfied for this patient.`;
    decisionFactors.push({
      type: 'inclusion',
      criterion_id: 'INC-NONE-SATISFIED',
      criterion_text: 'Mandatory Inclusion Criteria',
      status: 'unknown',
      reason: 'No protocol inclusion criteria could be confirmed satisfied with the provided patient clinical record.',
      protocol_page: null,
      protocol_evidence: null,
      patient_field: null,
      patient_value: null,
      patient_evidence: null,
    });
  }

  const disqCount =
    incUnsatisfied +
    excTriggered +
    disqualifyingContradictions.length +
    hardSilentExclusions.length;

  const summary: FinalEligibilitySummary = {
    final_decision: finalDecision,
    inclusion_satisfied_count: incSatisfied,
    inclusion_unsatisfied_count: incUnsatisfied,
    inclusion_unknown_count: incUnknown,
    exclusion_triggered_count: excTriggered,
    exclusion_not_triggered_count: excNotTriggered,
    exclusion_unknown_count: excUnknown,
    contradictions_count: contradictionResp?.summary.total_contradictions || 0,
    silent_exclusions_count: contradictionResp?.summary.total_silent_exclusions || 0,
    disqualifying_factors_count: disqCount,
    missing_items_count: missingInfoSet.size,
  };

  return {
    trial_id: trialId,
    patient_profile_id: patientProfileId,
    final_decision: finalDecision,
    decision_label: decisionLabel,
    summary,
    inclusion_summary: inclusionResp.summary,
    exclusion_summary: exclusionResp.summary,
    contradiction_summary: contradictionResp?.summary || null,
    missing_information: Array.from(missingInfoSet).sort(),
    decision_factors: decisionFactors,
    protocol_evidence: protocolEvidenceList,
    patient_evidence: patientEvidenceList,
    explanation,
    evaluated_at: new Date().toISOString(),
  };
}
