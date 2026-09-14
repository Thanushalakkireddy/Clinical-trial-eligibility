import { evaluateFinalEligibility } from '../server/decisionReviewer';
import {
  InclusionEvaluationResponse,
  ExclusionEvaluationResponse,
  ContradictionEvaluationResponse,
} from '../server/types';

function assert(condition: boolean, msg: string) {
  if (!condition) {
    console.error(`❌ Assertion failed: ${msg}`);
    process.exit(1);
  }
}

console.log('🧪 Starting Module 8 Decision Reviewer Test Suite...\n');

// -----------------------------------------------------------------------------
// TEST 1 — ELIGIBLE
// All inclusion: SATISFIED, all exclusion: NOT_TRIGGERED, no contradictions/silent
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-01',
    patient_profile_id: 'pat-01',
    overall_inclusion_status: 'satisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Age >= 18',
        result: 'satisfied',
        reason: 'Age is 45 (>= 18)',
        patient_evidence: { field: 'demographics.age', value: 45, source: 'patient_demographics' },
        protocol_evidence: { text: 'Age >= 18', source_page: 1, trial_id: 'trial-01' },
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 1, unsatisfied: 0, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-01',
    patient_profile_id: 'pat-01',
    overall_exclusion_status: 'not_triggered',
    criteria_results: [
      {
        criterion_id: 'EXC-001',
        criterion_text: 'Active heart failure',
        result: 'not_triggered',
        reason: 'No documented heart failure',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, triggered: 0, not_triggered: 1, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-01', 'pat-01', incResp, excResp, null);
  assert(res.final_decision === 'ELIGIBLE', 'TEST 1 should be ELIGIBLE');
  assert(res.decision_label === 'Eligible', 'Decision label should be Eligible');
  assert(res.summary.inclusion_satisfied_count === 1, 'Inclusion satisfied count should be 1');
  assert(res.summary.exclusion_triggered_count === 0, 'Exclusion triggered count should be 0');
  console.log('✅ TEST 1 passed: ELIGIBLE');
}

// -----------------------------------------------------------------------------
// TEST 2 — NOT ELIGIBLE THROUGH EXCLUSION
// Inclusion: SATISFIED, Exclusion: TRIGGERED
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-02',
    patient_profile_id: 'pat-02',
    overall_inclusion_status: 'satisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Baseline eGFR >= 20',
        result: 'satisfied',
        reason: 'eGFR of 25 satisfies requirement >= 20',
        patient_evidence: { field: 'labs.egfr', value: 25, source: 'patient_labs' },
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 1, unsatisfied: 0, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-02',
    patient_profile_id: 'pat-02',
    overall_exclusion_status: 'triggered',
    criteria_results: [
      {
        criterion_id: 'EXC-001',
        criterion_text: 'Severe renal impairment (eGFR < 30)',
        result: 'triggered',
        reason: 'eGFR of 25 is < 30',
        patient_evidence: { field: 'labs.egfr', value: 25, source: 'patient_labs' },
        protocol_evidence: { text: 'eGFR < 30', source_page: 2, trial_id: 'trial-02' },
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, triggered: 1, not_triggered: 0, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-02', 'pat-02', incResp, excResp, null);
  assert(res.final_decision === 'NOT_ELIGIBLE', 'TEST 2 should be NOT_ELIGIBLE');
  assert(res.summary.exclusion_triggered_count === 1, 'Exclusion triggered count should be 1');
  assert(res.decision_factors.some((f) => f.criterion_id === 'EXC-001' && f.status === 'triggered'), 'Decision factor EXC-001 should be present');
  console.log('✅ TEST 2 passed: NOT ELIGIBLE THROUGH EXCLUSION');
}

// -----------------------------------------------------------------------------
// TEST 3 — MORE INFORMATION REQUIRED
// Inclusion: SATISFIED, Exclusion: UNKNOWN
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-03',
    patient_profile_id: 'pat-03',
    overall_inclusion_status: 'satisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Age >= 18',
        result: 'satisfied',
        reason: 'Age is 32',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 1, unsatisfied: 0, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-03',
    patient_profile_id: 'pat-03',
    overall_exclusion_status: 'unknown',
    criteria_results: [
      {
        criterion_id: 'EXC-004',
        criterion_text: 'CNS metastases',
        result: 'unknown',
        reason: 'No brain MRI documented',
        missing_information: ['clinical_documentation.cns_imaging'],
        confidence_score: 0.8,
      },
    ],
    summary: { total: 1, triggered: 0, not_triggered: 0, unknown: 1 },
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-03', 'pat-03', incResp, excResp, null);
  assert(res.final_decision === 'MORE_INFORMATION_REQUIRED', 'TEST 3 should be MORE_INFORMATION_REQUIRED');
  assert(res.missing_information.includes('clinical_documentation.cns_imaging'), 'Missing information must be present');
  console.log('✅ TEST 3 passed: MORE INFORMATION REQUIRED');
}

// -----------------------------------------------------------------------------
// TEST 4 — NOT ELIGIBLE THROUGH UNSATISFIED INCLUSION
// Inclusion: UNSATISFIED, Exclusion: NOT_TRIGGERED
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-04',
    patient_profile_id: 'pat-04',
    overall_inclusion_status: 'unsatisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Age >= 18 and <= 75',
        result: 'unsatisfied',
        reason: 'Patient age is 15 (< 18)',
        patient_evidence: { field: 'demographics.age', value: 15, source: 'demographics' },
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 0, unsatisfied: 1, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-04',
    patient_profile_id: 'pat-04',
    overall_exclusion_status: 'not_triggered',
    criteria_results: [
      {
        criterion_id: 'EXC-001',
        criterion_text: 'Prior chemotherapy',
        result: 'not_triggered',
        reason: 'No prior chemotherapy',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, triggered: 0, not_triggered: 1, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-04', 'pat-04', incResp, excResp, null);
  assert(res.final_decision === 'NOT_ELIGIBLE', 'TEST 4 should be NOT_ELIGIBLE');
  assert(res.summary.inclusion_unsatisfied_count === 1, 'Inclusion unsatisfied count should be 1');
  console.log('✅ TEST 4 passed: NOT ELIGIBLE THROUGH UNSATISFIED INCLUSION');
}

// -----------------------------------------------------------------------------
// TEST 5 — MODULE 7 HARD SILENT EXCLUSION
// Inclusion: SATISFIED, Exclusion: NOT_TRIGGERED, Module 7: Hard silent hazard
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-05',
    patient_profile_id: 'pat-05',
    overall_inclusion_status: 'satisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Confirmed Glioblastoma',
        result: 'satisfied',
        reason: 'Confirmed glioblastoma',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 1, unsatisfied: 0, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-05',
    patient_profile_id: 'pat-05',
    overall_exclusion_status: 'not_triggered',
    criteria_results: [
      {
        criterion_id: 'EXC-001',
        criterion_text: 'Active infection',
        result: 'not_triggered',
        reason: 'No active infection',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, triggered: 0, not_triggered: 1, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const contraResp: ContradictionEvaluationResponse = {
    trial_id: 'trial-05',
    patient_profile_id: 'pat-05',
    clinical_safety_verdict: 'DISQUALIFIED_BY_SILENT_EXCLUSION',
    has_critical_conflicts: false,
    has_silent_exclusions: true,
    summary: {
      total_contradictions: 0,
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      total_silent_exclusions: 1,
      disqualifying_count: 1,
    },
    contradictions: [],
    silent_exclusions: [
      {
        trigger_id: 'SILENT-PACEMAKER',
        name: 'Cardiac Pacemaker vs Protocol MRI',
        category: 'device_implant',
        clinical_rationale: 'Pacemaker prevents required brain contrast MRI',
        affected_protocol_procedures: ['Contrast Brain MRI'],
        patient_evidence: { field: 'procedures', value: 'Pacemaker', source: 'patient_procedures' },
        severity: 'critical',
        is_hard_disqualification: true,
      },
    ],
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-05', 'pat-05', incResp, excResp, contraResp);
  assert(res.final_decision === 'NOT_ELIGIBLE', 'TEST 5 should be NOT_ELIGIBLE');
  assert(res.summary.silent_exclusions_count === 1, 'Silent exclusions count should be 1');
  assert(res.decision_factors.some((f) => f.type === 'silent_exclusion'), 'Silent exclusion factor must be in decision factors');
  console.log('✅ TEST 5 passed: MODULE 7 HARD SILENT EXCLUSION');
}

// -----------------------------------------------------------------------------
// PRIORITY CHECK: Confirmed Disqualification Overrides Unknown
// -----------------------------------------------------------------------------
{
  const incResp: InclusionEvaluationResponse = {
    trial_id: 'trial-prio',
    patient_profile_id: 'pat-prio',
    overall_inclusion_status: 'unsatisfied',
    criteria_results: [
      {
        criterion_id: 'INC-001',
        criterion_text: 'Age >= 18 and <= 65',
        result: 'unsatisfied',
        reason: 'Age 70 is > 65',
        missing_information: [],
        confidence_score: 1.0,
      },
    ],
    summary: { total: 1, satisfied: 0, unsatisfied: 1, unknown: 0 },
    evaluated_at: new Date().toISOString(),
  };

  const excResp: ExclusionEvaluationResponse = {
    trial_id: 'trial-prio',
    patient_profile_id: 'pat-prio',
    overall_exclusion_status: 'unknown',
    criteria_results: [
      {
        criterion_id: 'EXC-001',
        criterion_text: 'Prior immunotherapy',
        result: 'unknown',
        reason: 'Prior immunotherapy history missing',
        missing_information: ['oncology_medications'],
        confidence_score: 0.8,
      },
    ],
    summary: { total: 1, triggered: 0, not_triggered: 0, unknown: 1 },
    evaluated_at: new Date().toISOString(),
  };

  const res = evaluateFinalEligibility('trial-prio', 'pat-prio', incResp, excResp, null);
  assert(res.final_decision === 'NOT_ELIGIBLE', 'Priority check: Disqualification must override UNKNOWN');
  console.log('✅ Priority check passed: Disqualification overrides UNKNOWN');
}

console.log('\n🎉 ALL MODULE 8 TESTS PASSED SUCCESSFULLY!\n');
