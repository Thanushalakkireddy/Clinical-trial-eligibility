/**
 * Utility functions for mapping technical patient field paths to human-readable names,
 * providing domain-specific rationales, and linking missing fields to protocol criteria.
 */

import { DecisionFactor, ProtocolEvidenceItem } from '../types';

/**
 * Standard mapping of technical patient field paths to human-readable clinical labels.
 */
export const FIELD_NAME_MAP: Record<string, string> = {
  // Labs
  'labs.anc': 'Absolute Neutrophil Count (ANC)',
  'labs.platelets': 'Platelet Count',
  'labs.egfr': 'Estimated Glomerular Filtration Rate (eGFR)',
  'labs.hemoglobin': 'Hemoglobin',
  'labs.creatinine': 'Serum Creatinine',
  'labs.ast': 'Aspartate Aminotransferase (AST)',
  'labs.alt': 'Alanine Aminotransferase (ALT)',
  'labs.bilirubin': 'Total Bilirubin',
  'labs.wbc': 'White Blood Cell Count (WBC)',
  'labs.inr': 'International Normalized Ratio (INR)',
  'labs.alkaline_phosphatase': 'Alkaline Phosphatase (ALP)',

  // Vital Signs
  'vital_signs.blood_pressure': 'Blood Pressure',
  'vital_signs.systolic_bp': 'Systolic Blood Pressure',
  'vital_signs.diastolic_bp': 'Diastolic Blood Pressure',
  'vital_signs.heart_rate': 'Heart Rate',
  'vital_signs.height': 'Height',
  'vital_signs.weight': 'Weight',
  'vital_signs.spo2_percent': 'Oxygen Saturation (SpO2)',
  'vital_signs.temperature': 'Body Temperature',

  // Demographics
  'demographics.age': 'Age',
  'demographics.sex': 'Sex',
  'demographics.gender': 'Gender',
  'demographics.pregnancy_status': 'Pregnancy Status',
  'demographics.breastfeeding_status': 'Breastfeeding Status',
  'demographics.bmi': 'Body Mass Index (BMI)',

  // Clinical Status & Conditions
  'clinical_status.ecog': 'ECOG Performance Status',
  'clinical_status.ecog_performance_status': 'ECOG Performance Status',
  'clinical_status.diagnoses': 'Diagnosis / Medical Condition',
  'clinical_status.conditions': 'Documented Medical Conditions',

  // Allergies & Medications
  'allergies': 'Allergy History',
  'allergies.allergen': 'Allergen Information',
  'medications': 'Current Medications',
  'medications.drug_name': 'Prescribed Medications',

  // Treatment History
  'treatment_history': 'Treatment History',
  'treatment_history.recent_systemic_anticancer_therapy': 'Recent Systemic Anticancer Therapy',
  'treatment_history.prior_therapies': 'Prior Therapies',

  // Clinical Flags
  'clinical_flags.active_serious_infection': 'Active Serious Infection Status',
  'clinical_flags.uncontrolled_cardiac_disease': 'Uncontrolled Cardiac Disease Status',
  'clinical_flags.recent_systemic_anticancer_therapy': 'Recent Systemic Anticancer Therapy',
};

/**
 * Known clinical acronyms that should be preserved in uppercase.
 */
const KNOWN_ACRONYMS = new Set([
  'anc',
  'egfr',
  'ecog',
  'bmi',
  'bp',
  'spo2',
  'wbc',
  'rbc',
  'ast',
  'alt',
  'inr',
  'alp',
  'bun',
  'hgb',
  'hiv',
  'hbv',
  'hcv',
]);

/**
 * Formats an unknown technical field path into a clean, human-readable title.
 * Removes underscores, splits nested paths, and applies title casing with acronym preservation.
 *
 * Example: "vital_signs.respiratory_rate" -> "Respiratory Rate"
 * Example: "custom_flags.anc_test" -> "ANC Test"
 */
export function formatFallbackFieldName(field: string): string {
  if (!field || typeof field !== 'string') return 'Unknown Clinical Field';

  // Take the most specific segment (after last dot) unless it's just an index
  const segments = field.trim().split('.');
  const lastSegment = segments[segments.length - 1];
  const target = lastSegment && isNaN(Number(lastSegment)) ? lastSegment : segments[0];

  const words = target.replace(/[-_]+/g, ' ').trim().split(/\s+/);
  const formattedWords = words.map((w) => {
    const lower = w.toLowerCase();
    if (KNOWN_ACRONYMS.has(lower)) {
      return lower.toUpperCase();
    }
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  });

  return formattedWords.join(' ');
}

/**
 * Returns a human-readable name for any technical patient field path.
 */
export function formatPatientField(field: string): string {
  if (!field || typeof field !== 'string') return 'Unknown Field';

  const normalized = field.trim().toLowerCase();

  // 1. Direct dictionary match
  if (FIELD_NAME_MAP[normalized]) {
    return FIELD_NAME_MAP[normalized];
  }

  // 2. Try match without dot prefix (e.g. "anc" -> "labs.anc")
  for (const [key, label] of Object.entries(FIELD_NAME_MAP)) {
    if (key.endsWith(`.${normalized}`) || key === normalized) {
      return label;
    }
  }

  // 3. Fallback generic formatter
  return formatFallbackFieldName(field);
}

/**
 * Default domain reason why a specific technical field is clinically required
 * if no specific protocol criterion text is directly linked.
 */
export function getFieldDomainReason(field: string): string {
  const normalized = (field || '').trim().toLowerCase();
  const hasWord = (word: string) => new RegExp(`(^|[._\\s])${word}([._\\s]|$)`, 'i').test(normalized);

  if (hasWord('anc') || normalized.includes('neutrophil')) {
    return 'Required to evaluate blood-count eligibility criteria';
  }
  if (normalized.includes('platelet')) {
    return 'Required to evaluate platelet eligibility criteria';
  }
  if (normalized.includes('blood_pressure') || hasWord('bp') || normalized.includes('hypertension')) {
    return 'Required to evaluate cardiovascular/safety criteria';
  }
  if (normalized.includes('pregnancy')) {
    return 'Required to evaluate pregnancy-related eligibility/exclusion criteria';
  }
  if (normalized.includes('height')) {
    return 'Required where the protocol contains a height/body-measurement criterion';
  }
  if (normalized.includes('weight')) {
    return 'Required where the protocol contains a weight/body-measurement criterion';
  }
  if (hasWord('bmi')) {
    return 'Required to evaluate body mass index eligibility criteria';
  }
  if (normalized.includes('allerg')) {
    return 'Required to evaluate allergy/hypersensitivity exclusion criteria';
  }
  if (normalized.includes('medication')) {
    return 'Required to evaluate prohibited co-medication exclusion criteria';
  }
  if (normalized.includes('treatment') || normalized.includes('therapy')) {
    return 'Required to evaluate prior therapy eligibility criteria';
  }
  if (normalized.includes('infection')) {
    return 'Required to evaluate active infection exclusion criteria';
  }
  if (normalized.includes('cardiac') || normalized.includes('heart')) {
    return 'Required to evaluate cardiac safety criteria';
  }
  if (hasWord('ecog')) {
    return 'Required to evaluate performance status eligibility criteria';
  }
  if (hasWord('age')) {
    return 'Required to evaluate age-range eligibility criteria';
  }
  if (hasWord('sex') || normalized.includes('gender')) {
    return 'Required to evaluate demographic eligibility criteria';
  }
  if (normalized.includes('egfr') || normalized.includes('creatinine')) {
    return 'Required to evaluate renal function eligibility criteria';
  }
  if (normalized.includes('hemoglobin') || hasWord('hgb')) {
    return 'Required to evaluate anemia/hematologic eligibility criteria';
  }

  return 'Required to evaluate protocol eligibility criteria';
}

/**
 * Structured details for a missing clinical data element.
 */
export interface MissingFieldDetail {
  technicalField: string;
  displayName: string;
  status: 'Missing';
  whyRequired: string;
  criterionId: string | null;
  criterionText: string | null;
  protocolPage: number | null;
  sourceDocument: string | null;
  sourceExcerpt: string | null;
  originatingAgent: string;
}

/**
 * Keyword patterns associated with patient fields to link missing items
 * with unresolved protocol criteria factors.
 */
const FIELD_KEYWORD_MAP: Record<string, string[]> = {
  'labs.anc': ['anc', 'neutrophil', 'absolute neutrophil count'],
  'labs.platelets': ['platelet', 'thrombocyte', 'plt'],
  'labs.egfr': ['egfr', 'glomerular', 'creatinine clearance', 'renal'],
  'labs.hemoglobin': ['hemoglobin', 'hgb'],
  'labs.creatinine': ['creatinine', 'serum creatinine'],
  'vital_signs.blood_pressure': ['blood pressure', 'hypertension', 'systolic', 'diastolic', 'bp'],
  'vital_signs.height': ['height'],
  'vital_signs.weight': ['weight'],
  'demographics.age': ['age'],
  'demographics.sex': ['sex', 'gender', 'female', 'male'],
  'demographics.pregnancy_status': ['pregnancy', 'pregnant', 'nursing', 'breastfeeding', 'lactating'],
  'demographics.breastfeeding_status': ['breastfeeding', 'nursing', 'lactating'],
  'demographics.bmi': ['bmi', 'body mass index'],
  'clinical_status.ecog': ['ecog', 'performance status'],
  'clinical_status.diagnoses': ['diagnosis', 'histolog', 'cancer', 'carcinoma', 'melanoma', 'tumor'],
  'allergies': ['allergy', 'hypersensitiv', 'allergic'],
  'medications': ['medication', 'drug', 'concurrent', 'prohibited'],
  'treatment_history': ['prior therapy', 'chemotherapy', 'radiation', 'anticancer', 'treatment history'],
  'clinical_flags.active_serious_infection': ['infection', 'infectious', 'sepsis', 'antimicrobial'],
  'clinical_flags.uncontrolled_cardiac_disease': ['cardiac', 'heart failure', 'myocardial', 'arrhythmia'],
  'clinical_flags.recent_systemic_anticancer_therapy': ['systemic anticancer', 'prior therapy', 'recent therapy'],
};

/**
 * Links each missing technical field to its unresolved protocol criterion
 * returned by the backend assessment.
 *
 * SAFETY RULE: Never invents or fabricates criteria or thresholds.
 * Only links to actual criteria returned in decision factors.
 */
export function linkMissingFieldsToCriteria(
  missingFields: string[] = [],
  factors: DecisionFactor[] = [],
  protocolEvidence: ProtocolEvidenceItem[] = [],
  defaultTrialId: string = ''
): MissingFieldDetail[] {
  if (!Array.isArray(missingFields) || missingFields.length === 0) {
    return [];
  }

  // Deduplicate missing fields
  const uniqueFields = Array.from(new Set(missingFields.filter(Boolean)));

  // Filter factors that represent unknown/unresolved requirements
  const unresolvedFactors = (factors || []).filter(
    (f) => f.status === 'unknown' || f.status === 'investigation_required'
  );

  return uniqueFields.map((field) => {
    const displayName = formatPatientField(field);
    const domainReason = getFieldDomainReason(field);
    const normalizedField = field.trim().toLowerCase();

    // Strategy 1: Match by explicit factor.patient_field
    let matchedFactor = unresolvedFactors.find(
      (f) => f.patient_field && f.patient_field.trim().toLowerCase() === normalizedField
    );

    // Strategy 2: Match by keywords in criterion_text or reason
    if (!matchedFactor) {
      const keywords = FIELD_KEYWORD_MAP[normalizedField] || [
        field.replace(/^[^.]+\./, '').replace(/_/g, ' ').toLowerCase(),
      ];

      matchedFactor = unresolvedFactors.find((f) => {
        const text = `${f.criterion_text || ''} ${f.reason || ''}`.toLowerCase();
        return keywords.some((kw) => text.includes(kw));
      });
    }

    // Strategy 3: Try matching protocol evidence text if no factor matched
    let matchedEvidence: ProtocolEvidenceItem | undefined;
    if (!matchedFactor && protocolEvidence.length > 0) {
      const keywords = FIELD_KEYWORD_MAP[normalizedField] || [
        field.replace(/^[^.]+\./, '').replace(/_/g, ' ').toLowerCase(),
      ];
      matchedEvidence = protocolEvidence.find((pe) => {
        const text = (pe.text || '').toLowerCase();
        return keywords.some((kw) => text.includes(kw));
      });
    }

    // Build the resolved details without fabricating criteria
    const criterionId = matchedFactor?.criterion_id || null;
    const criterionText = matchedFactor?.criterion_text || matchedEvidence?.text || null;
    const protocolPage =
      matchedFactor?.protocol_page ??
      matchedFactor?.protocol_evidence?.source_page ??
      matchedEvidence?.source_page ??
      null;
    const sourceDocument =
      matchedFactor?.protocol_evidence?.trial_id ||
      matchedEvidence?.trial_id ||
      defaultTrialId ||
      null;
    const sourceExcerpt =
      matchedFactor?.protocol_evidence?.text ||
      matchedFactor?.reason ||
      matchedEvidence?.text ||
      null;

    // Determine clean "Why it is required" explanation
    let whyRequired = domainReason;
    if (criterionText) {
      whyRequired = criterionId
        ? `Required to evaluate: ${criterionId} — ${criterionText}`
        : `Required to evaluate: "${criterionText}"`;
    }

    // Determine originating agent
    let originatingAgent = 'Clinical Protocol Evaluation';
    if (matchedFactor) {
      if (matchedFactor.type === 'inclusion') {
        originatingAgent = 'Inclusion Matching Agent';
      } else if (matchedFactor.type === 'exclusion') {
        originatingAgent = 'Exclusion Detection Agent';
      } else if (matchedFactor.type === 'contradiction' || matchedFactor.type === 'silent_exclusion') {
        originatingAgent = 'Contradiction Agent';
      }
    }

    return {
      technicalField: field,
      displayName,
      status: 'Missing',
      whyRequired,
      criterionId,
      criterionText,
      protocolPage,
      sourceDocument,
      sourceExcerpt,
      originatingAgent,
    };
  });
}
