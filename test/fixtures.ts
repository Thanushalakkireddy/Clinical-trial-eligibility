import { ProtocolExtractionResponse, StructuredPatientProfile } from '../server/types';
import { buildStructuredProfile } from '../server/normalization';

/**
 * Automated test fixtures for test suites (test_workflow, test_module8, test_module9).
 * These fixtures are strictly for automated testing and MUST NOT be loaded automatically
 * into production data stores.
 */

export const testTrialOncology01: ProtocolExtractionResponse = {
  trial_id: 'trial-oncology-01',
  trial_title: 'Phase 3 Study of Pemigatinib in Advanced Renal Cell Carcinoma',
  trial_identifier: 'NCT04567890',
  inclusion_criteria: [
    {
      criterion_id: 'INC-001',
      type: 'inclusion',
      text: 'Patient must be age >= 18 and <= 75 years at time of signing consent.',
      source_page: 2,
      trial_id: 'trial-oncology-01',
      page_number: 2,
    },
    {
      criterion_id: 'INC-002',
      type: 'inclusion',
      text: 'Histologically confirmed advanced or metastatic clear cell RCC.',
      source_page: 2,
      trial_id: 'trial-oncology-01',
      page_number: 2,
    },
    {
      criterion_id: 'INC-003',
      type: 'inclusion',
      text: 'Absolute neutrophil count (ANC) >= 1,500/mcL and platelets >= 100,000/mcL.',
      source_page: 2,
      trial_id: 'trial-oncology-01',
      page_number: 2,
    },
    {
      criterion_id: 'INC-004',
      type: 'inclusion',
      text: 'Eastern Cooperative Oncology Group (ECOG) performance status <= 1.',
      source_page: 2,
      trial_id: 'trial-oncology-01',
      page_number: 2,
    },
  ],
  exclusion_criteria: [
    {
      criterion_id: 'EXC-001',
      type: 'exclusion',
      text: 'Patients with severe renal impairment (eGFR < 30 mL/min/1.73m²).',
      source_page: 3,
      trial_id: 'trial-oncology-01',
      page_number: 3,
    },
    {
      criterion_id: 'EXC-002',
      type: 'exclusion',
      text: 'Active central nervous system (CNS) metastases or untreated brain metastases.',
      source_page: 3,
      trial_id: 'trial-oncology-01',
      page_number: 3,
    },
    {
      criterion_id: 'EXC-003',
      type: 'exclusion',
      text: 'Prior treatment with anti-PD-1 or anti-CTLA-4 therapeutic antibodies.',
      source_page: 3,
      trial_id: 'trial-oncology-01',
      page_number: 3,
    },
    {
      criterion_id: 'EXC-004',
      type: 'exclusion',
      text: 'Pregnant or breastfeeding female patients.',
      source_page: 3,
      trial_id: 'trial-oncology-01',
      page_number: 3,
    },
    {
      criterion_id: 'EXC-005',
      type: 'exclusion',
      text: 'Uncontrolled hypertension with systolic blood pressure > 160 mmHg.',
      source_page: 3,
      trial_id: 'trial-oncology-01',
      page_number: 3,
    },
  ],
  other_requirements: [
    'Documented signed informed consent.',
    'Willingness to adhere to clinic visit schedule.',
  ],
  processing_status: 'completed',
  total_pages_analyzed: 4,
};

export const testTrialDiabetesDemo: ProtocolExtractionResponse = {
  trial_id: 'trial-diabetes-demo',
  trial_title: 'Phase 2 Trial of SGLT2 Dual Therapy in Adult Type 2 Diabetes',
  trial_identifier: 'NCT09876543',
  inclusion_criteria: [
    {
      criterion_id: 'INC-001',
      type: 'inclusion',
      text: 'Patient must be age >= 18 and <= 75 years.',
      source_page: 1,
      trial_id: 'trial-diabetes-demo',
      page_number: 1,
    },
    {
      criterion_id: 'INC-002',
      type: 'inclusion',
      text: 'Documented diagnosis of Type 2 Diabetes Mellitus.',
      source_page: 1,
      trial_id: 'trial-diabetes-demo',
      page_number: 1,
    },
    {
      criterion_id: 'INC-003',
      type: 'inclusion',
      text: 'Baseline HbA1c between 7.0% and 10.5%.',
      source_page: 1,
      trial_id: 'trial-diabetes-demo',
      page_number: 1,
    },
    {
      criterion_id: 'INC-004',
      type: 'inclusion',
      text: 'Current baseline monotherapy with Metformin.',
      source_page: 1,
      trial_id: 'trial-diabetes-demo',
      page_number: 1,
    },
  ],
  exclusion_criteria: [
    {
      criterion_id: 'EXC-001',
      type: 'exclusion',
      text: 'Severe renal impairment defined as eGFR < 30 mL/min/1.73m².',
      source_page: 2,
      trial_id: 'trial-diabetes-demo',
      page_number: 2,
    },
    {
      criterion_id: 'EXC-002',
      type: 'exclusion',
      text: 'Documented history of diabetic ketoacidosis (DKA).',
      source_page: 2,
      trial_id: 'trial-diabetes-demo',
      page_number: 2,
    },
    {
      criterion_id: 'EXC-003',
      type: 'exclusion',
      text: 'Pregnant or nursing female patients.',
      source_page: 2,
      trial_id: 'trial-diabetes-demo',
      page_number: 2,
    },
  ],
  other_requirements: ['Standard blood monitoring compliance'],
  processing_status: 'completed',
  total_pages_analyzed: 3,
};

export const testPatientDemo01: StructuredPatientProfile = buildStructuredProfile({
  patient_profile_id: 'patient-demo-01',
  age: 55,
  sex: 'male',
  height: 178,
  weight: 80,
  conditions: ['Advanced clear cell renal cell carcinoma', 'Hypertension'],
  medical_history: ['Appendectomy (2014)'],
  medications: [
    { name: 'Lisinopril', dose: '10', unit: 'mg', frequency: 'daily', is_current: true },
  ],
  lab_values: [
    { name: 'ANC', value: 2500, unit: 'cells/µL' },
    { name: 'Platelets', value: 180000, unit: '/µL' },
    { name: 'eGFR', value: 68, unit: 'mL/min/1.73m²' },
    { name: 'ALT', value: 28, unit: 'U/L' },
    { name: 'AST', value: 24, unit: 'U/L' },
  ],
  vital_signs: {
    systolic_bp: 130,
    diastolic_bp: 82,
    heart_rate: 72,
    source: 'patient_vitals',
  },
});
(testPatientDemo01.metadata as any).ecog_score = 0;

export const testPatientRenalDisqualified: StructuredPatientProfile = buildStructuredProfile({
  patient_profile_id: 'patient-demo-renal-disqualified',
  age: 62,
  sex: 'male',
  height: 175,
  weight: 82,
  conditions: ['Advanced clear cell renal cell carcinoma', 'Severe Chronic Kidney Disease Stage 4'],
  medical_history: [],
  medications: [
    { name: 'Amlodipine', dose: '5', unit: 'mg', frequency: 'daily', is_current: true },
  ],
  lab_values: [
    { name: 'ANC', value: 2200, unit: 'cells/µL' },
    { name: 'Platelets', value: 195000, unit: '/µL' },
    { name: 'eGFR', value: 22, unit: 'mL/min/1.73m²' },
    { name: 'ALT', value: 30, unit: 'U/L' },
  ],
  vital_signs: {
    systolic_bp: 138,
    diastolic_bp: 85,
    heart_rate: 76,
    source: 'patient_vitals',
  },
});
(testPatientRenalDisqualified.metadata as any).ecog_score = 1;

export const testPatientDiabetesDemo: StructuredPatientProfile = buildStructuredProfile({
  patient_profile_id: 'patient-diabetes-demo',
  age: 58,
  sex: 'male',
  height: 172,
  weight: 84,
  conditions: ['Type 2 Diabetes Mellitus', 'Hypertension'],
  medical_history: [],
  medications: [
    { name: 'Metformin', dose: '500', unit: 'mg', frequency: 'twice daily', is_current: true },
  ],
  lab_values: [
    { name: 'HbA1c', value: 7.8, unit: '%' },
    { name: 'eGFR', value: 65, unit: 'mL/min/1.73m²' },
  ],
  vital_signs: {
    systolic_bp: 128,
    diastolic_bp: 80,
    heart_rate: 70,
    source: 'patient_vitals',
  },
});
