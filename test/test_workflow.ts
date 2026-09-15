import {
  evaluateAllInclusionCriteria,
  evaluateAllExclusionCriteria,
} from '../server/evaluator';
import { evaluateContradictions } from '../server/contradictionEvaluator';
import { evaluateFinalEligibility } from '../server/decisionReviewer';
import {
  StructuredPatientProfile,
  ProtocolExtractionResponse,
} from '../server/types';

function assert(condition: boolean, msg: string) {
  if (!condition) {
    console.error(`❌ Assertion failed: ${msg}`);
    process.exit(1);
  }
}

console.log('🧪 Starting Multi-Agent Workflow Pipeline Test Suite...\n');

// Mock workflow runner simulating the compiled sequential graph nodes:
// Node 1: patient_profile
// Node 2: protocol_extraction
// Node 3: rag_retrieval
// Node 4: inclusion_matching
// Node 5: exclusion_detection
// Node 6: contradiction_detection
// Node 7: decision_reviewer
function executeWorkflowPipeline(
  trial: ProtocolExtractionResponse,
  patient: StructuredPatientProfile
) {
  const trialId = trial.trial_id;
  const patientId = patient.patient_profile_id;

  // Node 1 & 2: Patient and Protocol available in state
  // Node 3: RAG Retrieval (mocked)
  // Node 4: Inclusion Matching
  const incResp = evaluateAllInclusionCriteria(
    trialId,
    patientId,
    trial.inclusion_criteria,
    patient
  );

  // Node 5: Exclusion Detection
  const excResp = evaluateAllExclusionCriteria(
    trialId,
    patientId,
    trial.exclusion_criteria,
    patient
  );

  // Node 6: Contradiction & Silent Exclusion Detection
  const conResp = evaluateContradictions(
    trialId,
    patientId,
    patient,
    trial,
    incResp.criteria_results,
    excResp.criteria_results
  );

  // Node 7: Decision Reviewer Adjudication
  const finalResult = evaluateFinalEligibility(
    trialId,
    patientId,
    incResp,
    excResp,
    conResp,
    patient,
    trial
  );

  return {
    inclusion: incResp,
    exclusion: excResp,
    contradiction: conResp,
    final: finalResult,
  };
}

// =============================================================================
// TEST 1 — ELIGIBLE
// =============================================================================
{
  const trial: ProtocolExtractionResponse = {
    trial_id: 'trial-wf-01',
    trial_title: 'Type 2 Diabetes Safety Study',
    trial_identifier: 'NCT-WF-01',
    inclusion_criteria: [
      {
        criterion_id: 'INC-01',
        type: 'inclusion',
        text: 'Age >= 18 and <= 75',
        source_page: 2,
        trial_id: 'trial-wf-01',
      },
      {
        criterion_id: 'INC-02',
        type: 'inclusion',
        text: 'HbA1c between 7.0% and 10.5%',
        source_page: 2,
        trial_id: 'trial-wf-01',
      },
    ],
    exclusion_criteria: [
      {
        criterion_id: 'EXC-01',
        type: 'exclusion',
        text: 'Known pregnancy or breastfeeding female',
        source_page: 3,
        trial_id: 'trial-wf-01',
      },
      {
        criterion_id: 'EXC-02',
        type: 'exclusion',
        text: 'Severe renal impairment with eGFR < 30 mL/min/1.73m2',
        source_page: 3,
        trial_id: 'trial-wf-01',
      },
    ],
    other_requirements: [],
    processing_status: 'completed',
    total_pages_analyzed: 12,
  };

  const patient: StructuredPatientProfile = {
    patient_profile_id: 'pat-wf-01',
    profile_status: 'complete',
    medical_history: [],
    missing_information: [],
    created_at: new Date().toISOString(),
    demographics: {
      age: 52,
      sex: 'male',
    },
    conditions: [
      {
        name: 'Type 2 Diabetes Mellitus',
        normalized_name: 'type 2 diabetes',
        status: 'active',
        source: 'clinical_history',
      },
    ],
    medications: [
      {
        name: 'Metformin',
        normalized_name: 'metformin',
        dose: '1000mg',
        is_current: true,
        source: 'med_list',
      },
    ],
    lab_values: [
      {
        name: 'HbA1c',
        normalized_name: 'hba1c',
        value: 8.2,
        unit: '%',
        original_unit: '%',
        source: 'lab_report',
      },
      {
        name: 'eGFR',
        normalized_name: 'egfr',
        value: 78,
        unit: 'mL/min/1.73m2',
        original_unit: 'mL/min/1.73m2',
        source: 'lab_report',
      },
    ],
    allergies: [],
  };

  const result = executeWorkflowPipeline(trial, patient);
  assert(result.final.final_decision === 'ELIGIBLE', 'Workflow TEST 1 should be ELIGIBLE');
  assert(result.final.summary.inclusion_satisfied_count === 2, 'All 2 inclusions satisfied');
  assert(result.final.summary.exclusion_triggered_count === 0, '0 exclusions triggered');
  assert(result.final.summary.contradictions_count === 0, '0 contradictions');
  console.log('✅ TEST 1 passed: Multi-Agent Workflow -> ELIGIBLE');
}

// =============================================================================
// TEST 2 — EXPLICIT EXCLUSION
// =============================================================================
{
  const trial: ProtocolExtractionResponse = {
    trial_id: 'trial-wf-02',
    trial_title: 'Renal Protection Study',
    trial_identifier: 'NCT-WF-02',
    inclusion_criteria: [
      {
        criterion_id: 'INC-01',
        type: 'inclusion',
        text: 'Age >= 18',
        source_page: 2,
        trial_id: 'trial-wf-02',
      },
    ],
    exclusion_criteria: [
      {
        criterion_id: 'EXC-01',
        type: 'exclusion',
        text: 'Severe renal impairment with eGFR < 30',
        source_page: 3,
        trial_id: 'trial-wf-02',
      },
    ],
    other_requirements: [],
    processing_status: 'completed',
    total_pages_analyzed: 15,
  };

  const patient: StructuredPatientProfile = {
    patient_profile_id: 'pat-wf-02',
    profile_status: 'complete',
    medical_history: [],
    missing_information: [],
    created_at: new Date().toISOString(),
    demographics: { age: 64, sex: 'male' },
    conditions: [
      {
        name: 'Chronic Kidney Disease Stage 4',
        normalized_name: 'chronic kidney disease',
        status: 'active',
        source: 'history',
      },
    ],
    medications: [],
    lab_values: [
      {
        name: 'eGFR',
        normalized_name: 'egfr',
        value: 22,
        unit: 'mL/min/1.73m2',
        original_unit: 'mL/min/1.73m2',
        source: 'lab_report',
      },
    ],
    allergies: [],
  };

  const result = executeWorkflowPipeline(trial, patient);
  assert(result.final.final_decision === 'NOT_ELIGIBLE', 'Workflow TEST 2 should be NOT_ELIGIBLE');
  assert(result.final.summary.exclusion_triggered_count === 1, '1 exclusion triggered');
  console.log('✅ TEST 2 passed: Multi-Agent Workflow -> EXPLICIT EXCLUSION (NOT_ELIGIBLE)');
}

// =============================================================================
// TEST 3 — UNKNOWN
// =============================================================================
{
  const trial: ProtocolExtractionResponse = {
    trial_id: 'trial-wf-03',
    trial_title: 'Novel Statin Cardiovascular Trial',
    trial_identifier: 'NCT-WF-03',
    inclusion_criteria: [
      {
        criterion_id: 'INC-01',
        type: 'inclusion',
        text: 'Age >= 18',
        source_page: 2,
        trial_id: 'trial-wf-03',
      },
      {
        criterion_id: 'INC-02',
        type: 'inclusion',
        text: 'Fasting LDL cholesterol >= 130 mg/dL',
        source_page: 2,
        trial_id: 'trial-wf-03',
      },
    ],
    exclusion_criteria: [
      {
        criterion_id: 'EXC-01',
        type: 'exclusion',
        text: 'Known pregnancy or breastfeeding female',
        source_page: 3,
        trial_id: 'trial-wf-03',
      },
    ],
    other_requirements: [],
    processing_status: 'completed',
    total_pages_analyzed: 10,
  };

  const patient: StructuredPatientProfile = {
    patient_profile_id: 'pat-wf-03',
    profile_status: 'partial',
    medical_history: [],
    missing_information: [],
    created_at: new Date().toISOString(),
    demographics: { age: 40, sex: 'male' },
    conditions: [
      {
        name: 'Hyperlipidemia',
        normalized_name: 'hyperlipidemia',
        status: 'active',
        source: 'history',
      },
    ],
    medications: [],
    lab_values: [], // Missing LDL lab value
    allergies: [],
  };

  const result = executeWorkflowPipeline(trial, patient);
  assert(
    result.final.final_decision === 'MORE_INFORMATION_REQUIRED',
    'Workflow TEST 3 should be MORE_INFORMATION_REQUIRED'
  );
  assert(result.final.summary.inclusion_unknown_count >= 1, 'Inclusion unknown >= 1');
  assert(result.final.missing_information.length > 0, 'Missing information populated');
  console.log('✅ TEST 3 passed: Multi-Agent Workflow -> UNKNOWN (MORE_INFORMATION_REQUIRED)');
}

// =============================================================================
// TEST 4 — HARD SILENT EXCLUSION
// =============================================================================
{
  const trial: ProtocolExtractionResponse = {
    trial_id: 'trial-wf-04',
    trial_title: 'Contrast MRI Cardiac Imaging Protocol',
    trial_identifier: 'NCT-WF-04',
    inclusion_criteria: [
      {
        criterion_id: 'INC-01',
        type: 'inclusion',
        text: 'Age >= 18',
        source_page: 2,
        trial_id: 'trial-wf-04',
      },
      {
        criterion_id: 'INC-02',
        type: 'inclusion',
        text: 'Undergo contrast-enhanced cardiac MRI imaging at baseline',
        source_page: 2,
        trial_id: 'trial-wf-04',
      },
    ],
    exclusion_criteria: [
      {
        criterion_id: 'EXC-01',
        type: 'exclusion',
        text: 'Known pregnancy or breastfeeding female',
        source_page: 3,
        trial_id: 'trial-wf-04',
      },
    ],
    other_requirements: ['Cardiac MRI scan protocol'],
    processing_status: 'completed',
    total_pages_analyzed: 18,
  };

  const patient: StructuredPatientProfile = {
    patient_profile_id: 'pat-wf-04',
    profile_status: 'complete',
    medical_history: [],
    missing_information: [],
    created_at: new Date().toISOString(),
    demographics: { age: 60, sex: 'male' },
    conditions: [
      {
        name: 'Coronary Artery Disease',
        normalized_name: 'coronary artery disease',
        status: 'active',
        source: 'history',
      },
      {
        name: 'Cardiac Pacemaker in situ',
        normalized_name: 'cardiac pacemaker',
        status: 'active',
        source: 'device_history',
      },
    ],
    medications: [],
    lab_values: [],
    allergies: [],
  };

  const result = executeWorkflowPipeline(trial, patient);
  assert(
    result.final.final_decision === 'NOT_ELIGIBLE',
    'Workflow TEST 4 should be NOT_ELIGIBLE due to hard silent exclusion'
  );
  assert(
    result.final.summary.silent_exclusions_count >= 1,
    'Silent exclusion hazard detected'
  );
  console.log('✅ TEST 4 passed: Multi-Agent Workflow -> HARD SILENT EXCLUSION (NOT_ELIGIBLE)');
}

console.log('\n🎉 ALL MULTI-AGENT WORKFLOW PIPELINE TESTS PASSED!');
