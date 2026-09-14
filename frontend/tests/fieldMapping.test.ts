import { describe, it, expect } from 'vitest';
import {
  formatPatientField,
  formatFallbackFieldName,
  getFieldDomainReason,
  linkMissingFieldsToCriteria,
} from '../src/utils/fieldMapping';
import { DecisionFactor, ProtocolEvidenceItem } from '../src/types';

describe('Field Mapping & Formatter Utils', () => {
  describe('Human-Readable Field Mapping (Requirement 6)', () => {
    it('maps standard lab paths to exact human-readable clinical names', () => {
      expect(formatPatientField('labs.anc')).toBe('Absolute Neutrophil Count (ANC)');
      expect(formatPatientField('labs.platelets')).toBe('Platelet Count');
      expect(formatPatientField('labs.egfr')).toBe('Estimated Glomerular Filtration Rate (eGFR)');
      expect(formatPatientField('labs.hemoglobin')).toBe('Hemoglobin');
      expect(formatPatientField('labs.creatinine')).toBe('Serum Creatinine');
      expect(formatPatientField('labs.ast')).toBe('Aspartate Aminotransferase (AST)');
      expect(formatPatientField('labs.alt')).toBe('Alanine Aminotransferase (ALT)');
      expect(formatPatientField('labs.bilirubin')).toBe('Total Bilirubin');
    });

    it('maps vital signs to exact human-readable names', () => {
      expect(formatPatientField('vital_signs.blood_pressure')).toBe('Blood Pressure');
      expect(formatPatientField('vital_signs.height')).toBe('Height');
      expect(formatPatientField('vital_signs.weight')).toBe('Weight');
      expect(formatPatientField('vital_signs.heart_rate')).toBe('Heart Rate');
      expect(formatPatientField('vital_signs.spo2_percent')).toBe('Oxygen Saturation (SpO2)');
    });

    it('maps demographics to exact human-readable names', () => {
      expect(formatPatientField('demographics.age')).toBe('Age');
      expect(formatPatientField('demographics.sex')).toBe('Sex');
      expect(formatPatientField('demographics.pregnancy_status')).toBe('Pregnancy Status');
      expect(formatPatientField('demographics.breastfeeding_status')).toBe('Breastfeeding Status');
      expect(formatPatientField('demographics.bmi')).toBe('Body Mass Index (BMI)');
    });

    it('maps clinical status, history, and flags', () => {
      expect(formatPatientField('clinical_status.ecog')).toBe('ECOG Performance Status');
      expect(formatPatientField('clinical_status.diagnoses')).toBe('Diagnosis / Medical Condition');
      expect(formatPatientField('allergies')).toBe('Allergy History');
      expect(formatPatientField('medications')).toBe('Current Medications');
      expect(formatPatientField('treatment_history')).toBe('Treatment History');
      expect(formatPatientField('clinical_flags.active_serious_infection')).toBe(
        'Active Serious Infection Status'
      );
      expect(formatPatientField('clinical_flags.uncontrolled_cardiac_disease')).toBe(
        'Uncontrolled Cardiac Disease Status'
      );
      expect(formatPatientField('clinical_flags.recent_systemic_anticancer_therapy')).toBe(
        'Recent Systemic Anticancer Therapy'
      );
    });
  });

  describe('Unknown Field-Path Fallback Formatting (Requirement 7)', () => {
    it('formats unknown single words and nested paths cleanly into title case', () => {
      expect(formatFallbackFieldName('respiratory_rate')).toBe('Respiratory Rate');
      expect(formatFallbackFieldName('vital_signs.respiratory_rate')).toBe('Respiratory Rate');
      expect(formatFallbackFieldName('labs.fasting_glucose_level')).toBe('Fasting Glucose Level');
    });

    it('preserves recognized clinical acronyms in uppercase', () => {
      expect(formatFallbackFieldName('labs.wbc_count')).toBe('WBC Count');
      expect(formatFallbackFieldName('custom.hiv_viral_load')).toBe('HIV Viral Load');
      expect(formatFallbackFieldName('demographics.bmi_score')).toBe('BMI Score');
    });

    it('handles edge cases gracefully', () => {
      expect(formatPatientField('')).toBe('Unknown Field');
      expect(formatPatientField(null as unknown as string)).toBe('Unknown Field');
    });
  });

  describe('Domain Reason Fallback', () => {
    it('returns appropriate clinical reasons for different parameters', () => {
      expect(getFieldDomainReason('labs.anc')).toContain('blood-count');
      expect(getFieldDomainReason('labs.platelets')).toContain('platelet');
      expect(getFieldDomainReason('vital_signs.blood_pressure')).toContain('cardiovascular');
      expect(getFieldDomainReason('demographics.pregnancy_status')).toContain('pregnancy');
      expect(getFieldDomainReason('allergies')).toContain('allergy');
      expect(getFieldDomainReason('medications')).toContain('prohibited co-medication');
      expect(getFieldDomainReason('unknown.custom_field')).toContain('protocol eligibility criteria');
    });
  });

  describe('Linking Missing Fields to Protocol Criteria (Requirements 8 & 10)', () => {
    const mockFactors: DecisionFactor[] = [
      {
        type: 'inclusion',
        criterion_id: 'INC-006',
        criterion_text: 'ANC must be ≥ 1,500 cells/µL',
        status: 'unknown',
        reason: 'Absolute Neutrophil Count (ANC) was not documented.',
        protocol_page: 3,
        patient_field: 'labs.anc',
        protocol_evidence: {
          text: 'Absolute neutrophil count (ANC) >= 1500/uL',
          source_page: 3,
          trial_id: 'trial_lung_01',
        },
      },
      {
        type: 'inclusion',
        criterion_id: 'INC-007',
        criterion_text: 'Platelet count must be ≥ 100,000 cells/µL',
        status: 'unknown',
        reason: 'Platelet count is missing from lab panel.',
        protocol_page: 4,
        patient_field: 'labs.platelets',
        protocol_evidence: {
          text: 'Platelets >= 100,000/uL',
          source_page: 4,
          trial_id: 'trial_lung_01',
        },
      },
      {
        type: 'exclusion',
        criterion_id: 'EXC-003',
        criterion_text: 'Patient must not have uncontrolled hypertension',
        status: 'unknown',
        reason: 'Blood pressure readings are not documented.',
        protocol_page: 7,
        patient_field: 'vital_signs.blood_pressure',
        protocol_evidence: {
          text: 'Systolic BP > 160 mmHg or Diastolic BP > 100 mmHg',
          source_page: 7,
          trial_id: 'trial_lung_01',
        },
      },
    ];

    it('correctly associates missing fields with their corresponding criterion ID, text, and page citation', () => {
      const missing = ['labs.anc', 'labs.platelets', 'vital_signs.blood_pressure'];
      const details = linkMissingFieldsToCriteria(missing, mockFactors, [], 'trial_lung_01');

      expect(details).toHaveLength(3);

      // Check ANC
      const anc = details.find((d) => d.technicalField === 'labs.anc')!;
      expect(anc.displayName).toBe('Absolute Neutrophil Count (ANC)');
      expect(anc.criterionId).toBe('INC-006');
      expect(anc.criterionText).toBe('ANC must be ≥ 1,500 cells/µL');
      expect(anc.protocolPage).toBe(3);
      expect(anc.originatingAgent).toBe('Inclusion Matching Agent');
      expect(anc.whyRequired).toContain('INC-006');

      // Check Platelets
      const plt = details.find((d) => d.technicalField === 'labs.platelets')!;
      expect(plt.displayName).toBe('Platelet Count');
      expect(plt.criterionId).toBe('INC-007');
      expect(plt.protocolPage).toBe(4);

      // Check Blood Pressure
      const bp = details.find((d) => d.technicalField === 'vital_signs.blood_pressure')!;
      expect(bp.displayName).toBe('Blood Pressure');
      expect(bp.criterionId).toBe('EXC-003');
      expect(bp.protocolPage).toBe(7);
      expect(bp.originatingAgent).toBe('Exclusion Detection Agent');
    });

    it('NEVER fabricates missing fields not present in missingFields input (Requirement 10)', () => {
      // Even if factors mention other criteria, only what is passed in missingFields is output
      const missing = ['labs.anc'];
      const details = linkMissingFieldsToCriteria(missing, mockFactors, [], 'trial_lung_01');

      expect(details).toHaveLength(1);
      expect(details[0].technicalField).toBe('labs.anc');
      expect(details.some((d) => d.technicalField === 'labs.platelets')).toBe(false);
      expect(details.some((d) => d.technicalField === 'vital_signs.blood_pressure')).toBe(false);
      expect(details.some((d) => d.technicalField === 'vital_signs.height')).toBe(false);
      expect(details.some((d) => d.technicalField === 'vital_signs.weight')).toBe(false);
    });

    it('falls back to domain reason if no specific criterion factor exists, without inventing fake criteria', () => {
      const missing = ['labs.hemoglobin'];
      const details = linkMissingFieldsToCriteria(missing, [], [], 'trial_lung_01');

      expect(details).toHaveLength(1);
      expect(details[0].displayName).toBe('Hemoglobin');
      expect(details[0].criterionId).toBeNull();
      expect(details[0].protocolPage).toBeNull();
      expect(details[0].whyRequired).toBe('Required to evaluate anemia/hematologic eligibility criteria');
    });
  });
});
