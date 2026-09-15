import {
  NormalizedLabValue,
  NormalizedCondition,
  NormalizedMedication,
  NormalizedAllergy,
  StructuredPatientProfile,
  MissingInformation,
  PatientDemographics,
} from './types';

// Canonical Lab Test Names mapping
const LAB_NAME_MAP: Record<string, { normalized: string; display: string }> = {
  egfr: { normalized: 'egfr', display: 'eGFR' },
  'estimated gfr': { normalized: 'egfr', display: 'eGFR' },
  'estimated glomerular filtration rate': { normalized: 'egfr', display: 'eGFR' },
  gfr: { normalized: 'egfr', display: 'eGFR' },
  'ckd-epi egfr': { normalized: 'egfr', display: 'eGFR' },
  creatinine: { normalized: 'creatinine', display: 'Serum Creatinine' },
  'serum creatinine': { normalized: 'creatinine', display: 'Serum Creatinine' },
  scr: { normalized: 'creatinine', display: 'Serum Creatinine' },
  creat: { normalized: 'creatinine', display: 'Serum Creatinine' },
  alt: { normalized: 'alt', display: 'ALT' },
  'alanine aminotransferase': { normalized: 'alt', display: 'ALT' },
  sgpt: { normalized: 'alt', display: 'ALT' },
  ast: { normalized: 'ast', display: 'AST' },
  'aspartate aminotransferase': { normalized: 'ast', display: 'AST' },
  sgot: { normalized: 'ast', display: 'AST' },
  'total bilirubin': { normalized: 'total_bilirubin', display: 'Total Bilirubin' },
  bilirubin: { normalized: 'total_bilirubin', display: 'Total Bilirubin' },
  tbil: { normalized: 'total_bilirubin', display: 'Total Bilirubin' },
  platelets: { normalized: 'platelets', display: 'Platelets' },
  'platelet count': { normalized: 'platelets', display: 'Platelets' },
  plt: { normalized: 'platelets', display: 'Platelets' },
  anc: { normalized: 'anc', display: 'ANC' },
  'absolute neutrophil count': { normalized: 'anc', display: 'ANC' },
  neutrophils: { normalized: 'anc', display: 'ANC' },
  wbc: { normalized: 'wbc', display: 'WBC' },
  'white blood cell count': { normalized: 'wbc', display: 'WBC' },
  hemoglobin: { normalized: 'hemoglobin', display: 'Hemoglobin' },
  hgb: { normalized: 'hemoglobin', display: 'Hemoglobin' },
  hb: { normalized: 'hemoglobin', display: 'Hemoglobin' },
  hba1c: { normalized: 'hba1c', display: 'HbA1c' },
  'glycated hemoglobin': { normalized: 'hba1c', display: 'HbA1c' },
  'hemoglobin a1c': { normalized: 'hba1c', display: 'HbA1c' },
  a1c: { normalized: 'hba1c', display: 'HbA1c' },
  potassium: { normalized: 'potassium', display: 'Potassium' },
  sodium: { normalized: 'sodium', display: 'Sodium' },
  inr: { normalized: 'inr', display: 'INR' },
  albumin: { normalized: 'albumin', display: 'Albumin' },
  glucose: { normalized: 'glucose', display: 'Glucose' },
  'fasting glucose': { normalized: 'glucose', display: 'Fasting Glucose' },
  troponin: { normalized: 'troponin', display: 'Troponin' },
};

// Unit normalization map
const UNIT_MAP: Record<string, string> = {
  'ml/min/1.73m2': 'mL/min/1.73m²',
  'ml/min/1.73m^2': 'mL/min/1.73m²',
  'ml/min': 'mL/min',
  'mg/dl': 'mg/dL',
  'mg/l': 'mg/L',
  'g/dl': 'g/dL',
  'u/l': 'U/L',
  'iu/l': 'IU/L',
  '%': '%',
  percent: '%',
  '10*9/l': '10^9/L',
  '10^9/l': '10^9/L',
  '/ul': '/µL',
  '/mcl': '/mcL',
  'cells/ul': 'cells/µL',
  'cells/mcl': 'cells/mcL',
  'mmol/l': 'mmol/L',
  'meq/l': 'mEq/L',
};

export function normalizeLab(input: {
  name: string;
  value: number;
  unit: string;
  reference_range?: string | null;
  source?: string;
  source_document?: string;
  original_field?: string;
}): NormalizedLabValue {
  const cleanName = input.name.trim().toLowerCase();
  const labInfo = LAB_NAME_MAP[cleanName] || {
    normalized: cleanName.replace(/\s+/g, '_'),
    display: input.name.trim(),
  };

  const cleanUnit = input.unit.trim().toLowerCase();
  const normalizedUnit = UNIT_MAP[cleanUnit] || input.unit.trim();

  return {
    name: labInfo.display,
    normalized_name: labInfo.normalized,
    value: input.value,
    unit: normalizedUnit,
    original_unit: input.unit,
    reference_range: input.reference_range || null,
    normalization_status: 'normalized',
    source: input.source || 'patient_input',
    source_document: input.source_document,
    original_field: input.original_field,
  };
}

export function normalizeCondition(name: string, source: string = 'patient_input'): NormalizedCondition {
  const trimmed = name.trim();
  return {
    name: trimmed,
    normalized_name: trimmed.toLowerCase(),
    icd10_code: null,
    status: 'active',
    diagnosed_date: null,
    source,
  };
}

export function normalizeMedication(input: {
  name: string;
  dose?: string | null;
  unit?: string | null;
  frequency?: string | null;
  route?: string | null;
  is_current?: boolean;
  source?: string;
}): NormalizedMedication {
  const trimmed = input.name.trim();
  return {
    name: trimmed,
    normalized_name: trimmed.toLowerCase(),
    dose: input.dose?.trim() || null,
    unit: input.unit?.trim() || null,
    frequency: input.frequency?.trim() || null,
    route: input.route?.trim() || null,
    is_current: input.is_current !== false,
    source: input.source || 'patient_input',
  };
}

export function normalizeAllergy(input: {
  allergen: string;
  reaction?: string | null;
  severity?: string | null;
  source?: string;
  source_document?: string;
  original_field?: string;
  substance?: string;
}): NormalizedAllergy {
  const trimmed = input.allergen.trim();
  return {
    allergen: trimmed,
    normalized_allergen: trimmed.toLowerCase(),
    reaction: input.reaction?.trim() || null,
    severity: input.severity?.trim() || null,
    source: input.source || 'patient_input',
    source_document: input.source_document,
    original_field: input.original_field,
    substance: input.substance || trimmed,
  };
}

export function buildStructuredProfile(input: {
  patient_profile_id?: string;
  age?: number | null;
  sex?: string | null;
  height?: number | null;
  weight?: number | null;
  pregnancy_status?: string | null;
  breastfeeding_status?: boolean | null;
  demographics?: PatientDemographics;
  conditions?: string[];
  medical_history?: string[];
  medications?: Array<any>;
  lab_values?: Array<any>;
  allergies?: Array<any>;
  vital_signs?: any;
  clinical_notes_raw?: string | null;
  metadata?: Record<string, any>;
}): StructuredPatientProfile {
  const id = input.patient_profile_id || `patient_${Math.random().toString(36).substring(2, 10)}`;

  let bmi: number | null = null;
  if (input.height && input.weight && input.height > 0) {
    const hMeters = input.height / 100;
    bmi = parseFloat((input.weight / (hMeters * hMeters)).toFixed(2));
  }

  // Pregnancy status extraction with explicit null/undefined check
  let pregnancyStatus: string | null = null;
  const rawPreg =
    input.pregnancy_status !== undefined && input.pregnancy_status !== null
      ? input.pregnancy_status
      : input.demographics?.pregnancy_status !== undefined && input.demographics?.pregnancy_status !== null
      ? input.demographics.pregnancy_status
      : input.metadata?.pregnancy_status !== undefined && input.metadata?.pregnancy_status !== null
      ? input.metadata.pregnancy_status
      : null;

  if (rawPreg !== undefined && rawPreg !== null) {
    pregnancyStatus = String(rawPreg).trim().toLowerCase();
  }

  // Breastfeeding status extraction with explicit null/undefined check
  let breastfeedingStatus: boolean | null = null;
  const rawBf =
    input.breastfeeding_status !== undefined && input.breastfeeding_status !== null
      ? input.breastfeeding_status
      : input.demographics?.breastfeeding_status !== undefined && input.demographics?.breastfeeding_status !== null
      ? input.demographics.breastfeeding_status
      : input.metadata?.breastfeeding_status !== undefined && input.metadata?.breastfeeding_status !== null
      ? input.metadata.breastfeeding_status
      : null;

  if (rawBf !== undefined && rawBf !== null) {
    if (typeof rawBf === 'boolean') {
      breastfeedingStatus = rawBf;
    } else if (typeof rawBf === 'string') {
      const s = rawBf.trim().toLowerCase();
      if (['false', 'no', '0', 'none', 'denies', 'negative'].includes(s)) {
        breastfeedingStatus = false;
      } else if (['true', 'yes', '1', 'positive'].includes(s)) {
        breastfeedingStatus = true;
      }
    } else if (typeof rawBf === 'number') {
      breastfeedingStatus = rawBf !== 0;
    }
  }

  const normalizedConditions: NormalizedCondition[] = (input.conditions || []).map((c) =>
    normalizeCondition(c)
  );

  const normalizedHistory: NormalizedCondition[] = (input.medical_history || []).map((h) =>
    normalizeCondition(h)
  );

  const normalizedMeds: NormalizedMedication[] = (input.medications || []).map((m) =>
    normalizeMedication(m)
  );

  const normalizedLabs: NormalizedLabValue[] = (input.lab_values || []).map((l) =>
    normalizeLab(l)
  );

  const normalizedAllergies: NormalizedAllergy[] = (input.allergies || []).map((a) =>
    normalizeAllergy(a)
  );

  // Determine missing information categories
  const missing: MissingInformation[] = [];

  if (input.height === undefined || input.height === null) {
    missing.push({
      field: 'height',
      status: 'unknown',
      category: 'demographics',
      description: 'Patient height was not provided.',
    });
  }
  if (input.weight === undefined || input.weight === null) {
    missing.push({
      field: 'weight',
      status: 'unknown',
      category: 'demographics',
      description: 'Patient weight was not provided.',
    });
  }

  const labNames = new Set(normalizedLabs.map((l) => l.normalized_name));
  const hasHepaticCondition = normalizedConditions.some((c) =>
    /liver|hepatic|cirrhosis|hepatitis/i.test(c.name)
  );
  if (hasHepaticCondition && !labNames.has('alt') && !labNames.has('ast') && !labNames.has('total_bilirubin')) {
    missing.push({
      field: 'liver_disease',
      status: 'unknown',
      category: 'conditions',
      description: 'No hepatic conditions or liver function lab panels (ALT, AST, Bilirubin) reported.',
    });
  }

  const hasCardiac =
    normalizedConditions.some((c) =>
      /heart|cardiac|coronary|hypertension|chf|myocardial/i.test(c.name)
    ) ||
    Boolean(input.vital_signs?.systolic_bp !== undefined && input.vital_signs?.systolic_bp !== null) ||
    input.metadata?.uncontrolled_cardiac_disease !== undefined ||
    input.metadata?.cardiac_disease !== undefined;
  if (!hasCardiac) {
    missing.push({
      field: 'cardiac_history',
      status: 'unknown',
      category: 'conditions',
      description: 'No cardiovascular history or cardiac conditions reported.',
    });
  }

  const hasInfectious =
    normalizedConditions.some((c) => /hiv|hepatitis|hbv|hcv/i.test(c.name)) ||
    input.metadata?.active_serious_infection !== undefined ||
    input.metadata?.infection !== undefined;
  if (!hasInfectious) {
    missing.push({
      field: 'infectious_disease',
      status: 'unknown',
      category: 'conditions',
      description: 'No infectious disease history (HIV, Hepatitis B/C) reported.',
    });
  }

  const hasEcog =
    input.metadata?.ecog_score !== undefined ||
    input.metadata?.ecog_performance_status !== undefined ||
    (input as any).ecog !== undefined ||
    (input as any).ecog_score !== undefined;
  if (!hasEcog) {
    missing.push({
      field: 'ecog_performance_status',
      status: 'unknown',
      category: 'clinical_status',
      description: 'ECOG performance status (0-4) was not documented.',
    });
  }

  const hasHypersensitivity =
    input.metadata?.investigational_therapy_hypersensitivity !== undefined ||
    input.metadata?.severe_hypersensitivity !== undefined ||
    input.metadata?.severe_hypersensitivity_to_investigational_therapy !== undefined;
  if (normalizedAllergies.length === 0 && !hasHypersensitivity) {
    missing.push({
      field: 'allergies',
      status: 'unknown',
      category: 'allergies',
      description: 'No known drug or environmental allergies documented.',
    });
  }

  return {
    patient_profile_id: id,
    profile_status: 'processed',
    created_at: new Date().toISOString(),
    demographics: {
      age: input.age ?? input.demographics?.age ?? null,
      sex: input.sex ?? input.demographics?.sex ?? null,
      height: input.height ?? input.demographics?.height ?? null,
      weight: input.weight ?? input.demographics?.weight ?? null,
      bmi,
      pregnancy_status: pregnancyStatus,
      breastfeeding_status: breastfeedingStatus,
    },
    conditions: normalizedConditions,
    medical_history: normalizedHistory,
    medications: normalizedMeds,
    lab_values: normalizedLabs,
    allergies: normalizedAllergies,
    vital_signs: input.vital_signs || null,
    missing_information: missing,
    clinical_notes_raw: input.clinical_notes_raw || null,
    metadata: input.metadata || {},
    clinical_status: input.metadata?.clinical_status || (input as any).clinical_status || null,
    treatment_history: input.metadata?.treatment_history || (input as any).treatment_history || null,
  };
}
