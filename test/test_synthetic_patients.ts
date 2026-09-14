import fs from 'fs';
import path from 'path';
import {
  evaluateAllInclusionCriteria,
  evaluateAllExclusionCriteria,
} from '../server/evaluator';
import { evaluateContradictions } from '../server/contradictionEvaluator';
import { evaluateFinalEligibility } from '../server/decisionReviewer';
import { extractPatientFromJson } from '../server/patientExtractor';
import { dataStore } from '../server/dataStore';
import { ProtocolExtractionResponse, StructuredPatientProfile } from '../server/types';

function runTests() {
  console.log('🧪 Starting Synthetic Patients Verification Test Suite...');

  // 1. Load protocol SYN-ONC-001
  const protocolPath = path.join(process.cwd(), 'storage/pdfs/SYN-ONC-001_protocol.json');
  if (!fs.existsSync(protocolPath)) {
    throw new Error(`SYN-ONC-001 protocol not found at ${protocolPath}`);
  }
  const protocol: ProtocolExtractionResponse = JSON.parse(fs.readFileSync(protocolPath, 'utf8'));

  console.log(`Loaded protocol: ${protocol.trial_id} (${protocol.inclusion_criteria.length} inclusions, ${protocol.exclusion_criteria.length} exclusions)`);

  // 2. Test Complete Patient: synthetic-patient-full-001
  const fullPatientPath = path.join(process.cwd(), 'data/patients/synthetic-patient-full-001.json');
  const fullPatient: StructuredPatientProfile = JSON.parse(fs.readFileSync(fullPatientPath, 'utf8'));

  const fullInc = evaluateAllInclusionCriteria(protocol.trial_id, fullPatient.patient_profile_id, protocol.inclusion_criteria, fullPatient);
  const fullExc = evaluateAllExclusionCriteria(protocol.trial_id, fullPatient.patient_profile_id, protocol.exclusion_criteria, fullPatient);
  const fullContradictions = evaluateContradictions(protocol.trial_id, fullPatient.patient_profile_id, fullPatient, protocol, fullInc.criteria_results, fullExc.criteria_results);

  const fullDecision = evaluateFinalEligibility(
    protocol.trial_id,
    fullPatient.patient_profile_id,
    fullInc,
    fullExc,
    fullContradictions,
    fullPatient,
    protocol
  );

  console.log('--- TEST 1: COMPLETE PATIENT ---');
  console.log('Inclusion overall:', fullInc.overall_inclusion_status);
  fullInc.criteria_results.forEach(r => console.log(`  ${r.criterion_id}: ${r.result} - ${r.reason}`));
  console.log('Exclusion overall:', fullExc.overall_exclusion_status);
  fullExc.criteria_results.forEach(r => console.log(`  ${r.criterion_id}: ${r.result} - ${r.reason}`));
  console.log('Final Decision:', fullDecision.final_decision);

  if (fullDecision.final_decision !== 'ELIGIBLE') {
    throw new Error(`TEST 1 FAILED: Expected ELIGIBLE but got ${fullDecision.final_decision}. Missing info: ${JSON.stringify(fullDecision.missing_information)}`);
  }
  console.log('✅ TEST 1 PASSED: synthetic-patient-full-001 -> ELIGIBLE');

  // 3. Test Partial Patient: synthetic-patient-partial-001
  const partialPatientPath = path.join(process.cwd(), 'data/patients/synthetic-patient-partial-001.json');
  const partialPatient: StructuredPatientProfile = JSON.parse(fs.readFileSync(partialPatientPath, 'utf8'));

  const partInc = evaluateAllInclusionCriteria(protocol.trial_id, partialPatient.patient_profile_id, protocol.inclusion_criteria, partialPatient);
  const partExc = evaluateAllExclusionCriteria(protocol.trial_id, partialPatient.patient_profile_id, protocol.exclusion_criteria, partialPatient);
  const partContradictions = evaluateContradictions(protocol.trial_id, partialPatient.patient_profile_id, partialPatient, protocol, partInc.criteria_results, partExc.criteria_results);

  const partDecision = evaluateFinalEligibility(
    protocol.trial_id,
    partialPatient.patient_profile_id,
    partInc,
    partExc,
    partContradictions,
    partialPatient,
    protocol
  );

  console.log('--- TEST 2: PARTIAL PATIENT ---');
  console.log('Final Decision:', partDecision.final_decision);
  if (partDecision.final_decision !== 'MORE_INFORMATION_REQUIRED') {
    throw new Error(`TEST 2 FAILED: Expected MORE_INFORMATION_REQUIRED but got ${partDecision.final_decision}`);
  }
  console.log('✅ TEST 2 PASSED: synthetic-patient-partial-001 -> MORE_INFORMATION_REQUIRED');

  // 4. Test Empty Patient: synthetic-patient-empty-001
  const emptyPatientPath = path.join(process.cwd(), 'data/patients/synthetic-patient-empty-001.json');
  const emptyPatient: StructuredPatientProfile = JSON.parse(fs.readFileSync(emptyPatientPath, 'utf8'));

  const emptyInc = evaluateAllInclusionCriteria(protocol.trial_id, emptyPatient.patient_profile_id, protocol.inclusion_criteria, emptyPatient);
  const emptyExc = evaluateAllExclusionCriteria(protocol.trial_id, emptyPatient.patient_profile_id, protocol.exclusion_criteria, emptyPatient);
  const emptyContradictions = evaluateContradictions(protocol.trial_id, emptyPatient.patient_profile_id, emptyPatient, protocol, emptyInc.criteria_results, emptyExc.criteria_results);

  const emptyDecision = evaluateFinalEligibility(
    protocol.trial_id,
    emptyPatient.patient_profile_id,
    emptyInc,
    emptyExc,
    emptyContradictions,
    emptyPatient,
    protocol
  );

  console.log('--- TEST 3: EMPTY PATIENT ---');
  console.log('Final Decision:', emptyDecision.final_decision);
  if (emptyDecision.final_decision !== 'MORE_INFORMATION_REQUIRED') {
    throw new Error(`TEST 3 FAILED: Expected MORE_INFORMATION_REQUIRED but got ${emptyDecision.final_decision}`);
  }
  console.log('✅ TEST 3 PASSED: synthetic-patient-empty-001 -> MORE_INFORMATION_REQUIRED');

  // 5. Test JSON Extraction with field mismatches and type conversions
  console.log('--- TEST 4: EXTRACT RAW JSON WITH MISMATCHES & TYPE CONVERSIONS ---');
  const rawUploadedJson = {
    patient_id: 'test-upload-001',
    age: 52,
    sex: 'female',
    diagnosis: 'advanced solid tumor',
    ecog_performance_status: '1',
    eGFR: '68 mL/min/1.73m²',
    active_serious_infection: 'false',
    uncontrolled_cardiac_disease: false,
    recent_systemic_anticancer_therapy: 'false',
    investigational_therapy_hypersensitivity: false,
  };

  const extracted = extractPatientFromJson(rawUploadedJson, 'patient_full.json');
  console.log('Extracted fields:', extracted.extractedFields);

  const extInc = evaluateAllInclusionCriteria(protocol.trial_id, extracted.profile.patient_profile_id, protocol.inclusion_criteria, extracted.profile);
  const extExc = evaluateAllExclusionCriteria(protocol.trial_id, extracted.profile.patient_profile_id, protocol.exclusion_criteria, extracted.profile);
  const extContradictions = evaluateContradictions(protocol.trial_id, extracted.profile.patient_profile_id, extracted.profile, protocol, extInc.criteria_results, extExc.criteria_results);

  const extDecision = evaluateFinalEligibility(
    protocol.trial_id,
    extracted.profile.patient_profile_id,
    extInc,
    extExc,
    extContradictions,
    extracted.profile,
    protocol
  );

  console.log('Extracted patient decision:', extDecision.final_decision);
  if (extDecision.final_decision !== 'ELIGIBLE') {
    throw new Error(`TEST 4 FAILED: Expected ELIGIBLE from raw extracted JSON but got ${extDecision.final_decision}`);
  }
  console.log('✅ TEST 4 PASSED: Raw JSON with string types and field variations -> ELIGIBLE');

  // 6. Test 5: synthetic_complete_patient_record_v2 structure with exact 12 fields
  console.log('--- TEST 5: SYNTHETIC COMPLETE PATIENT RECORD V2 WITH 12 FIELDS ---');
  const v2Record = {
    patient_id: 'synthetic-patient-full-v2',
    age: 58,
    sex: 'female',
    conditions: ['advanced solid tumor'],
    clinical_status: {
      ecog_performance_status: 1,
      active_serious_infection: false,
      uncontrolled_cardiac_disease: false,
    },
    labs: {
      anc: '2400 cells/mcL',
      platelets: '185000 cells/mcL',
      egfr: '68 mL/min/1.73m²',
    },
    lab_values: {
      egfr: '68 mL/min/1.73m²',
    },
    vital_signs: {
      blood_pressure: {
        systolic: 125,
        diastolic: 78,
        unit: 'mmHg',
      },
    },
    allergies: [
      {
        substance: 'none documented',
        severity: null,
      },
    ],
    medications: {
      recent_systemic_anticancer_therapy: false,
      investigational_therapy_hypersensitivity: false,
    },
    medication_history: {
      recent_systemic_anticancer_therapy: false,
    },
    safety_history: {
      severe_hypersensitivity_to_investigational_therapy: false,
    },
  };

  const extractedV2 = extractPatientFromJson(v2Record, 'synthetic_complete_patient_record_v2.json');
  console.log('V2 Extracted profile lab values:', extractedV2.profile.lab_values);
  console.log('V2 Extracted profile vitals:', extractedV2.profile.vital_signs);
  console.log('V2 Extracted profile clinical status:', extractedV2.profile.clinical_status);
  console.log('V2 Extracted profile treatment history:', extractedV2.profile.treatment_history);
  console.log('V2 Extracted profile missing info:', extractedV2.profile.missing_information);

  const v2Inc = evaluateAllInclusionCriteria(protocol.trial_id, extractedV2.profile.patient_profile_id, protocol.inclusion_criteria, extractedV2.profile);
  const v2Exc = evaluateAllExclusionCriteria(protocol.trial_id, extractedV2.profile.patient_profile_id, protocol.exclusion_criteria, extractedV2.profile);
  const v2Contradictions = evaluateContradictions(protocol.trial_id, extractedV2.profile.patient_profile_id, extractedV2.profile, protocol, v2Inc.criteria_results, v2Exc.criteria_results);

  const v2Decision = evaluateFinalEligibility(
    protocol.trial_id,
    extractedV2.profile.patient_profile_id,
    v2Inc,
    v2Exc,
    v2Contradictions,
    extractedV2.profile,
    protocol
  );

  console.log('V2 Final Decision:', v2Decision.final_decision);
  if (v2Decision.final_decision !== 'ELIGIBLE') {
    throw new Error(`TEST 5 FAILED: Expected ELIGIBLE from V2 record but got ${v2Decision.final_decision}. Missing info: ${JSON.stringify(v2Decision.missing_information)}`);
  }
  console.log('✅ TEST 5 PASSED: synthetic_complete_patient_record_v2 -> ELIGIBLE');

  // =========================================================================
  // 7. Test 6: End-to-End Persistence & EXC-002 Evaluation Regression Test
  // =========================================================================
  console.log('--- TEST 6: END-TO-END REGRESSION TEST FOR SYNTHETIC COMPLETE PATIENT 002 ---');
  const completePatientV2 = {
    patient_id: 'synthetic-patient-complete-002',
    demographics: {
      age: 52,
      sex: 'female',
      pregnancy_status: 'not_pregnant',
      breastfeeding_status: false,
    },
    conditions: ['advanced solid tumor'],
    clinical_status: {
      ecog_performance_status: 1,
      active_serious_infection: false,
      uncontrolled_cardiac_disease: false,
    },
    labs: {
      anc: '2400 cells/mcL',
      platelets: '185000 cells/mcL',
      egfr: '68 mL/min/1.73m²',
    },
    lab_values: {
      egfr: '68 mL/min/1.73m²',
    },
    vital_signs: {
      blood_pressure: {
        systolic: 125,
        diastolic: 78,
        unit: 'mmHg',
      },
    },
    allergies: [
      {
        substance: 'none documented',
        severity: null,
      },
    ],
    medications: {
      recent_systemic_anticancer_therapy: false,
      investigational_therapy_hypersensitivity: false,
    },
    medication_history: {
      recent_systemic_anticancer_therapy: false,
    },
    safety_history: {
      severe_hypersensitivity_to_investigational_therapy: false,
    },
  };

  // Step 1 & 2: Extract patient
  const ext = extractPatientFromJson(completePatientV2, 'synthetic_complete_patient_record_v2.json');
  if (ext.profile.demographics.pregnancy_status !== 'not_pregnant') {
    throw new Error(`TEST 6 FAILED: Extracted pregnancy_status is ${ext.profile.demographics.pregnancy_status}, expected "not_pregnant"`);
  }
  if (ext.profile.demographics.breastfeeding_status !== false) {
    throw new Error(`TEST 6 FAILED: Extracted breastfeeding_status is ${ext.profile.demographics.breastfeeding_status}, expected false`);
  }

  // Step 3: Save patient
  dataStore.savePatient(ext.profile);

  // Step 4: Reload saved patient from persistence
  const savedDiskPath = path.join(process.cwd(), 'data/patients/synthetic-patient-complete-002.json');
  if (!fs.existsSync(savedDiskPath)) {
    throw new Error(`TEST 6 FAILED: Saved file not found at ${savedDiskPath}`);
  }
  const diskContent = JSON.parse(fs.readFileSync(savedDiskPath, 'utf8'));
  if (diskContent.demographics.pregnancy_status !== 'not_pregnant') {
    throw new Error(`TEST 6 FAILED: Persisted disk file pregnancy_status is ${diskContent.demographics.pregnancy_status}, expected "not_pregnant"`);
  }
  if (diskContent.demographics.breastfeeding_status !== false) {
    throw new Error(`TEST 6 FAILED: Persisted disk file breastfeeding_status is ${diskContent.demographics.breastfeeding_status}, expected false`);
  }

  // Step 5: Retrieve patient through data access layer
  const retrievedPatient = dataStore.getPatient('synthetic-patient-complete-002');
  if (!retrievedPatient) {
    throw new Error('TEST 6 FAILED: Could not retrieve patient from dataStore');
  }
  if (retrievedPatient.demographics.pregnancy_status !== 'not_pregnant') {
    throw new Error(`TEST 6 FAILED: Retrieved pregnancy_status is ${retrievedPatient.demographics.pregnancy_status}, expected "not_pregnant"`);
  }
  if (retrievedPatient.demographics.breastfeeding_status !== false) {
    throw new Error(`TEST 6 FAILED: Retrieved breastfeeding_status is ${retrievedPatient.demographics.breastfeeding_status}, expected false`);
  }

  // Verify all 12 previously fixed fields still survive
  if (retrievedPatient.clinical_status?.ecog_performance_status !== 1) {
    throw new Error(`TEST 6 FAILED: ECOG performance status expected 1, got ${retrievedPatient.clinical_status?.ecog_performance_status}`);
  }
  const anc = retrievedPatient.lab_values.find((l: any) => l.normalized_name === 'anc');
  if (!anc || anc.value !== 2400) {
    throw new Error(`TEST 6 FAILED: ANC expected 2400, got ${anc?.value}`);
  }
  const plt = retrievedPatient.lab_values.find((l: any) => l.normalized_name === 'platelets');
  if (!plt || plt.value !== 185000) {
    throw new Error(`TEST 6 FAILED: platelets expected 185000, got ${plt?.value}`);
  }
  const egfr = retrievedPatient.lab_values.find((l: any) => l.normalized_name === 'egfr');
  if (!egfr || egfr.value !== 68) {
    throw new Error(`TEST 6 FAILED: eGFR expected 68, got ${egfr?.value}`);
  }
  if (retrievedPatient.vital_signs?.systolic_bp !== 125 || retrievedPatient.vital_signs?.diastolic_bp !== 78) {
    throw new Error(`TEST 6 FAILED: BP expected 125/78, got ${retrievedPatient.vital_signs?.systolic_bp}/${retrievedPatient.vital_signs?.diastolic_bp}`);
  }
  if (retrievedPatient.clinical_status?.active_serious_infection !== false) {
    throw new Error('TEST 6 FAILED: active_serious_infection expected false');
  }
  if (retrievedPatient.clinical_status?.uncontrolled_cardiac_disease !== false) {
    throw new Error('TEST 6 FAILED: uncontrolled_cardiac_disease expected false');
  }
  if (retrievedPatient.treatment_history?.recent_systemic_anticancer_therapy !== false) {
    throw new Error('TEST 6 FAILED: recent_systemic_anticancer_therapy expected false');
  }
  if (retrievedPatient.treatment_history?.investigational_therapy_hypersensitivity !== false) {
    throw new Error('TEST 6 FAILED: investigational_therapy_hypersensitivity expected false');
  }
  if (retrievedPatient.treatment_history?.severe_hypersensitivity_to_investigational_therapy !== false) {
    throw new Error('TEST 6 FAILED: severe_hypersensitivity_to_investigational_therapy expected false');
  }

  // Step 6: Run eligibility evaluation against trial with EXC-002: "Pregnant or breastfeeding female patients."
  const demoTrial: ProtocolExtractionResponse = {
    trial_id: 'trial-demo-onc-002',
    trial_title: 'Phase 2 Oncology Protocol with EXC-002',
    trial_identifier: 'NCT-DEMO-ONC-002',
    inclusion_criteria: [
      {
        criterion_id: 'INC-001',
        type: 'inclusion',
        text: 'Patients aged 18 years or older with histologically confirmed solid tumors.',
        source_page: 1,
        trial_id: 'trial-demo-onc-002',
      },
      {
        criterion_id: 'INC-002',
        type: 'inclusion',
        text: 'Absolute neutrophil count (ANC) >= 1,500/mcL and platelets >= 100,000/mcL.',
        source_page: 1,
        trial_id: 'trial-demo-onc-002',
      },
      {
        criterion_id: 'INC-003',
        type: 'inclusion',
        text: 'Eastern Cooperative Oncology Group (ECOG) performance status <= 1.',
        source_page: 1,
        trial_id: 'trial-demo-onc-002',
      },
    ],
    exclusion_criteria: [
      {
        criterion_id: 'EXC-001',
        type: 'exclusion',
        text: 'Patients with severe renal impairment (eGFR < 30 mL/min/1.73m²).',
        source_page: 2,
        trial_id: 'trial-demo-onc-002',
      },
      {
        criterion_id: 'EXC-002',
        type: 'exclusion',
        text: 'Pregnant or breastfeeding female patients.',
        source_page: 2,
        trial_id: 'trial-demo-onc-002',
      },
      {
        criterion_id: 'EXC-003',
        type: 'exclusion',
        text: 'Uncontrolled hypertension with systolic blood pressure > 160 mmHg.',
        source_page: 2,
        trial_id: 'trial-demo-onc-002',
      },
    ],
    other_requirements: ['Written informed consent obtained prior to study procedures.'],
    processing_status: 'completed',
    total_pages_analyzed: 2,
  };

  const incRes = evaluateAllInclusionCriteria(demoTrial.trial_id, retrievedPatient.patient_profile_id, demoTrial.inclusion_criteria, retrievedPatient);
  const excRes = evaluateAllExclusionCriteria(demoTrial.trial_id, retrievedPatient.patient_profile_id, demoTrial.exclusion_criteria, retrievedPatient);
  const contraRes = evaluateContradictions(demoTrial.trial_id, retrievedPatient.patient_profile_id, retrievedPatient, demoTrial, incRes.criteria_results, excRes.criteria_results);
  const finalEval = evaluateFinalEligibility(demoTrial.trial_id, retrievedPatient.patient_profile_id, incRes, excRes, contraRes, retrievedPatient, demoTrial);

  const exc002 = excRes.criteria_results.find((c: any) => c.criterion_id === 'EXC-002');
  if (!exc002) {
    throw new Error('TEST 6 FAILED: EXC-002 not found in evaluation results');
  }
  console.log('EXC-002 evaluation result:', exc002.result, '-', exc002.reason);
  if (exc002.result === 'unknown') {
    throw new Error('TEST 6 FAILED: EXC-002 must not be UNKNOWN');
  }
  if (exc002.result !== 'not_triggered') {
    throw new Error(`TEST 6 FAILED: EXC-002 result is ${exc002.result}, expected "not_triggered"`);
  }
  if (finalEval.missing_information.includes('demographics.pregnancy_status')) {
    throw new Error('TEST 6 FAILED: missing_information contains demographics.pregnancy_status');
  }
  console.log('TEST 6 Final Decision:', finalEval.final_decision);
  if (finalEval.final_decision !== 'ELIGIBLE') {
    throw new Error(`TEST 6 FAILED: Expected ELIGIBLE but got ${finalEval.final_decision}. Missing info: ${JSON.stringify(finalEval.missing_information)}`);
  }
  console.log('✅ TEST 6 PASSED: End-to-end regression test for synthetic-patient-complete-002 -> ELIGIBLE');

  console.log('\n🎉 ALL SYNTHETIC PATIENT TESTS PASSED PERFECTLY!');
}

runTests();
