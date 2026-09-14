import { StructuredPatientProfile } from './types';
import { buildStructuredProfile } from './normalization';
import path from 'path';

export interface PatientExtractionResult {
  profile: StructuredPatientProfile;
  extractedFields: string[];
  sourceDocument: string;
  sourceType: 'Uploaded PDF' | 'Uploaded JSON';
}

/**
 * Validates and sanitizes patient ID if extracted from document.
 */
function sanitizePatientId(rawId?: string | null): string | null {
  if (!rawId || typeof rawId !== 'string') return null;
  const trimmed = rawId.trim();
  // Disallow forbidden demo IDs
  const forbidden = new Set([
    'patient-demo-01',
    'patient-demo-renal-disqualified',
    'patient-diabetes-demo',
  ]);
  if (forbidden.has(trimmed)) return null;

  // Must be safe characters: alphanumeric, dashes, underscores, 3-64 chars
  if (/^[a-zA-Z0-9_-]{3,64}$/.test(trimmed)) {
    return trimmed;
  }
  return null;
}

/**
 * Generates a clean, unique patient profile ID.
 */
export function generateUniquePatientId(): string {
  return `patient_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 8)}`;
}

/**
 * Helper to parse boolean values (handles booleans, strings "false", "true", "no", "yes")
 */
export function parseBoolField(val: any): boolean | null {
  if (val === undefined || val === null) return null;
  if (typeof val === 'boolean') return val;
  if (typeof val === 'number') {
    if (val === 0) return false;
    if (val === 1) return true;
  }
  if (typeof val === 'string') {
    const s = val.trim().toLowerCase();
    if (s === 'false' || s === 'no' || s === 'none' || s === 'negative' || s === 'denied' || s === '0') return false;
    if (s === 'true' || s === 'yes' || s === 'positive' || s === 'confirmed' || s === '1') return true;
  }
  return null;
}

/**
 * Extracts patient profile from text extracted from a patient PDF.
 * Strict rule: Documented Information Only - zero inference.
 */
export async function extractPatientFromPdfBuffer(
  buffer: Buffer,
  filename: string
): Promise<PatientExtractionResult> {
  // Validate PDF header magic bytes
  if (buffer.length < 4 || buffer.toString('utf8', 0, 4) !== '%PDF') {
    throw new Error('Invalid PDF format: The uploaded file is corrupted or not a valid PDF document.');
  }

  let fullText = '';
  try {
    // Dynamic import / require of pdf-parse
    // pdf-parse v2 exposes { PDFParse }
    const pdfModule = await import('pdf-parse');
    const PDFParseClass = (pdfModule as any).PDFParse || (pdfModule as any).default?.PDFParse || (pdfModule as any).default;

    if (typeof PDFParseClass === 'function' && PDFParseClass.prototype?.getText) {
      const parser = new PDFParseClass({ data: buffer });
      await parser.load();
      const res = await parser.getText();
      fullText = typeof res === 'string' ? res : res?.text || '';
    } else if (typeof (pdfModule as any).default === 'function') {
      const res = await (pdfModule as any).default(buffer);
      fullText = res?.text || '';
    } else {
      // Direct stream text fallback
      fullText = buffer.toString('utf8');
    }
  } catch (err: any) {
    throw new Error(`Failed to extract text from PDF: ${err?.message || 'Corrupted or unreadable PDF'}`);
  }

  // Strip non-printable control chars while preserving newlines & spaces
  let cleanText = fullText.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, ' ').trim();
  // Remove PDF page markers like "-- 1 of 2 --" or "Page 1 of 2"
  cleanText = cleanText.replace(/--\s*\d+\s*of\s*\d+\s*--/gi, ' ');
  cleanText = cleanText.replace(/page\s*\d+\s*(?:of\s*\d+)?/gi, ' ');

  if (!cleanText || cleanText.length < 10) {
    throw new Error(
      'Could not extract patient information from this document. Please verify that the document contains readable patient information or enter the profile manually.'
    );
  }

  const extractedFields: string[] = [];

  // 1. Patient ID
  let extractedId: string | null = null;
  const idMatch = cleanText.match(/(?:patient\s*id|patient\s*#|mrn|subject\s*id|record\s*id)\s*[:#\-]?\s*([a-zA-Z0-9_-]+)/i);
  if (idMatch && idMatch[1]) {
    extractedId = sanitizePatientId(idMatch[1]);
    if (extractedId) extractedFields.push('patient_id');
  }
  const finalId = extractedId || generateUniquePatientId();

  // 2. Demographics: Age
  let age: number | null = null;
  const ageMatch =
    cleanText.match(/(?:age|patient\s*age)\s*[:=]?\s*(\d{1,3})\b/i) ||
    cleanText.match(/\b(\d{1,3})\s*(?:years\s*old|year\s*old|yo|y\/o)\b/i);
  if (ageMatch && ageMatch[1]) {
    const val = parseInt(ageMatch[1], 10);
    if (val >= 0 && val <= 130) {
      age = val;
      extractedFields.push('age');
    }
  }

  // 3. Demographics: Sex
  let sex: string | null = null;
  const sexMatch = cleanText.match(/(?:sex|gender|biological\s*sex)\s*[:=]?\s*(male|female|other)\b/i);
  if (sexMatch && sexMatch[1]) {
    sex = sexMatch[1].toLowerCase();
    extractedFields.push('sex');
  } else {
    // Check standalone mentions if clear
    if (/\b(?:sex|gender)\s*[:=]?\s*m\b/i.test(cleanText)) {
      sex = 'male';
      extractedFields.push('sex');
    } else if (/\b(?:sex|gender)\s*[:=]?\s*f\b/i.test(cleanText)) {
      sex = 'female';
      extractedFields.push('sex');
    }
  }

  // 4. Height & Weight
  let height: number | null = null;
  let weight: number | null = null;

  const heightMatch = cleanText.match(/(?:height|ht)\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(cm|m|in)?\b/i);
  if (heightMatch && heightMatch[1]) {
    let hVal = parseFloat(heightMatch[1]);
    const unit = (heightMatch[2] || 'cm').toLowerCase();
    if (unit === 'm' && hVal < 3) hVal = hVal * 100;
    if (unit === 'in') hVal = hVal * 2.54;
    height = Math.round(hVal);
    extractedFields.push('height');
  }

  const weightMatch = cleanText.match(/(?:weight|wt)\s*[:=]?\s*(\d{2,3}(?:\.\d+)?)\s*(kg|lbs?)\b/i);
  if (weightMatch && weightMatch[1]) {
    let wVal = parseFloat(weightMatch[1]);
    const unit = (weightMatch[2] || 'kg').toLowerCase();
    if (unit.startsWith('lb')) wVal = wVal * 0.453592;
    weight = parseFloat(wVal.toFixed(1));
    extractedFields.push('weight');
  }

  // 5. Clinical Status: ECOG
  let ecogScore: number | null = null;
  const ecogMatch = cleanText.match(/ecog(?:\s*(?:performance\s*status|score|ps))?\s*[:=]?\s*([0-4])\b/i);
  if (ecogMatch && ecogMatch[1]) {
    ecogScore = parseInt(ecogMatch[1], 10);
    extractedFields.push('ecog_performance_status');
  }

  // 6. Vital Signs
  let vitalSigns: any = null;
  const bpMatch = cleanText.match(/(?:blood\s*pressure|bp)\s*[:=]?\s*(\d{2,3})\s*\/\s*(\d{2,3})/i);
  const hrMatch = cleanText.match(/(?:heart\s*rate|hr|pulse)\s*[:=]?\s*(\d{2,3})/i);
  if (bpMatch || hrMatch) {
    vitalSigns = {
      systolic_bp: bpMatch ? parseInt(bpMatch[1], 10) : null,
      diastolic_bp: bpMatch ? parseInt(bpMatch[2], 10) : null,
      heart_rate: hrMatch ? parseInt(hrMatch[1], 10) : null,
      source: 'uploaded_document',
    };
    extractedFields.push('vital_signs');
  }

  // 7. Conditions / Diagnoses
  const conditions: string[] = [];
  const medicalHistory: string[] = [];

  // Match diagnosis / conditions sections or lines
  const diagRegex = /(?:diagnosis|diagnoses|primary\s*diagnosis|conditions?|active\s*conditions?|medical\s*history|history\s*of)\s*[:=]\s*([^\n;.]+)/gi;
  let diagHit: RegExpExecArray | null;
  while ((diagHit = diagRegex.exec(cleanText)) !== null) {
    const rawVal = diagHit[1].trim();
    if (rawVal && rawVal.length > 2) {
      // Split by comma or semicolon if multiple
      const items = rawVal.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
      for (const item of items) {
        if (!/^(none|na|n\/a|unknown|denies|negative)$/i.test(item)) {
          conditions.push(item);
        }
      }
    }
  }

  // Match specific known conditions if mentioned in the document narrative
  const knownConditions = [
    'Renal Cell Carcinoma',
    'Advanced clear cell renal cell carcinoma',
    'Clear Cell RCC',
    'Type 2 Diabetes Mellitus',
    'Advanced Solid Tumor',
    'Solid Tumor',
    'Clear Cell Renal Cell Carcinoma',
    'Renal Cell Carcinoma',
    'Type 2 Diabetes',
    'Hypertension',
    'Chronic Kidney Disease',
    'Severe Chronic Kidney Disease Stage 4',
    'Asthma',
    'Coronary Artery Disease',
    'Diabetic Ketoacidosis',
    'Brain Metastases',
    'Central Nervous System Metastases',
  ];
  for (const kc of knownConditions) {
    const escaped = kc.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rx = new RegExp(`\\b${escaped}\\b`, 'i');
    if (rx.test(cleanText) && !conditions.some((c) => c.toLowerCase() === kc.toLowerCase())) {
      conditions.push(kc);
    }
  }

  if (conditions.length > 0) {
    extractedFields.push('conditions');
  }

  // 8. Laboratory Results
  const labValues: Array<{ name: string; value: number; unit: string; reference_range?: string | null }> = [];

  const labPatterns: Array<{ name: string; defaultUnit: string; pattern: RegExp }> = [
    {
      name: 'eGFR',
      defaultUnit: 'mL/min/1.73m²',
      pattern: /(?:egfr|estimated\s*gfr|ckd-epi\s*egfr)\s*[:=]?\s*([><]?\s*\d+(?:\.\d+)?)\s*(ml\/min\/1\.73m\^?2|ml\/min)?/i,
    },
    {
      name: 'Platelets',
      defaultUnit: '/µL',
      pattern: /(?:platelets?|plt|platelet\s*count)\s*[:=]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(\/mcL|\/ul|cells\/ul|cells\/mcl|10\^9\/l|10\*9\/l)?/i,
    },
    {
      name: 'ANC',
      defaultUnit: 'cells/µL',
      pattern: /(?:anc|absolute\s*neutrophil\s*count|neutrophils?)\s*[:=]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(cells\/ul|cells\/mcl|\/mcl|\/ul|10\^9\/l)?/i,
    },
    {
      name: 'ALT',
      defaultUnit: 'U/L',
      pattern: /(?:alt|alanine\s*aminotransferase|sgpt)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(u\/l|iu\/l)?/i,
    },
    {
      name: 'AST',
      defaultUnit: 'U/L',
      pattern: /(?:ast|aspartate\s*aminotransferase|sgot)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(u\/l|iu\/l)?/i,
    },
    {
      name: 'Total Bilirubin',
      defaultUnit: 'mg/dL',
      pattern: /(?:total\s*bilirubin|bilirubin|tbil)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg\/dl|mg\/l|umol\/l)?/i,
    },
    {
      name: 'Serum Creatinine',
      defaultUnit: 'mg/dL',
      pattern: /(?:serum\s*creatinine|creatinine|scr)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg\/dl|mg\/l|umol\/l)?/i,
    },
    {
      name: 'HbA1c',
      defaultUnit: '%',
      pattern: /(?:hba1c|glycated\s*hemoglobin|hemoglobin\s*a1c|a1c)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(%)?/i,
    },
    {
      name: 'Hemoglobin',
      defaultUnit: 'g/dL',
      pattern: /(?:hemoglobin|hgb|hb)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(g\/dl)?/i,
    },
    {
      name: 'WBC',
      defaultUnit: '10^9/L',
      pattern: /(?:wbc|white\s*blood\s*cell(?:\s*count)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(10\^9\/l|\/ul|k\/ul)?/i,
    },
  ];

  for (const lp of labPatterns) {
    const m = cleanText.match(lp.pattern);
    if (m && m[1]) {
      const rawNum = m[1].replace(/,/g, '').replace(/[><\s]/g, '');
      const num = parseFloat(rawNum);
      if (!isNaN(num)) {
        const foundUnit = m[2] ? m[2].trim() : lp.defaultUnit;
        labValues.push({
          name: lp.name,
          value: num,
          unit: foundUnit,
        });
      }
    }
  }

  if (labValues.length > 0) {
    extractedFields.push('lab_values');
  }

  // 9. Medications
  const medications: Array<{ name: string; dose?: string; unit?: string; frequency?: string }> = [];
  const medSectionMatch = cleanText.match(/(?:medications?|current\s*medications?|rx)\s*[:=]\s*([^\n]+(?:\n\s*[-*•]\s*[^\n]+)*)/i);
  if (medSectionMatch && medSectionMatch[1]) {
    const rawMeds = medSectionMatch[1].split(/[\n,;]/).map((s) => s.replace(/^[-*•]\s*/, '').trim()).filter(Boolean);
    for (const rm of rawMeds) {
      if (/^(none|na|n\/a|denies)$/i.test(rm)) continue;
      const medParse = rm.match(/^([a-zA-Z\s]+?)(?:\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?))?(?:\s+(daily|once\s*daily|twice\s*daily|bid|tid|qid|prn|weekly))?$/i);
      if (medParse) {
        medications.push({
          name: medParse[1].trim(),
          dose: medParse[2] || undefined,
          unit: medParse[3] || undefined,
          frequency: medParse[4] || undefined,
        });
      } else {
        medications.push({ name: rm });
      }
    }
  }

  // Also check common medication names if unextracted
  const commonMeds = ['Lisinopril', 'Metformin', 'Amlodipine', 'Albuterol', 'Atorvastatin', 'Levothyroxine'];
  for (const cm of commonMeds) {
    if (!medications.some((m) => m.name.toLowerCase() === cm.toLowerCase())) {
      const medRegex = new RegExp(`\\b${cm}\\b(?:\\s+(\\d+(?:\\.\\d+)?)\\s*(mg|mcg))?(?:\\s+(daily|bid|twice\\s*daily))?`, 'i');
      const mm = cleanText.match(medRegex);
      if (mm) {
        medications.push({
          name: cm,
          dose: mm[1] || undefined,
          unit: mm[2] || undefined,
          frequency: mm[3] || undefined,
        });
      }
    }
  }

  if (medications.length > 0) {
    extractedFields.push('medications');
  }

  // 10. Allergies
  const allergies: Array<{ allergen: string; reaction?: string; severity?: string }> = [];
  const allergyMatch = cleanText.match(/(?:allergies|allergy)\s*[:=]\s*([^\n;.]+)/i);
  if (allergyMatch && allergyMatch[1]) {
    const rawAllergy = allergyMatch[1].trim();
    if (!/^(none|nkda|no\s*known(?:\s*drug)?\s*allergies|denies)$/i.test(rawAllergy)) {
      const items = rawAllergy.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
      for (const it of items) {
        const parsed = it.match(/^([^(]+)(?:\(([^)]+)\))?$/);
        if (parsed) {
          allergies.push({
            allergen: parsed[1].trim(),
            reaction: parsed[2]?.trim() || undefined,
          });
        } else {
          allergies.push({ allergen: it });
        }
      }
    }
  }

  if (allergies.length > 0) {
    extractedFields.push('allergies');
  }

  // Validate that we found at least some meaningful patient information
  if (extractedFields.length === 0) {
    throw new Error(
      'Could not extract patient information from this document. Please verify that the document contains readable patient information or enter the profile manually.'
    );
  }

  // Build standardized profile via normalization
  const pdfMetadata: Record<string, any> = {
    source: 'Uploaded PDF',
    source_document: path.basename(filename),
    extraction_timestamp: new Date().toISOString(),
    extracted_fields: extractedFields,
    ...(ecogScore !== null ? { ecog_score: ecogScore } : {}),
  };

  const profile = buildStructuredProfile({
    patient_profile_id: finalId,
    age,
    sex,
    height,
    weight,
    conditions,
    medical_history: medicalHistory,
    medications,
    lab_values: labValues,
    allergies,
    vital_signs: vitalSigns,
    clinical_notes_raw: null, // Keep raw document text private
    metadata: pdfMetadata,
  });

  // Attach metadata and provenance
  profile.metadata = pdfMetadata;

  return {
    profile,
    extractedFields,
    sourceDocument: path.basename(filename),
    sourceType: 'Uploaded PDF',
  };
}

/**
 * Extracts and maps patient information from a JSON document.
 * Strict rule: Documented Information Only - zero inference.
 */
export function extractPatientFromJson(
  content: string | object,
  filename: string
): PatientExtractionResult {
  let parsed: any;
  if (typeof content === 'string') {
    try {
      parsed = JSON.parse(content);
    } catch (err: any) {
      throw new Error(`Invalid JSON format: ${err?.message || 'The uploaded file is not valid JSON.'}`);
    }
  } else {
    parsed = content;
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Invalid patient JSON: Root element must be a valid JSON object.');
  }

  const extractedFields: string[] = [];

  // Patient ID
  const candidateId = parsed.patient_profile_id || parsed.patient_id || parsed.id || parsed.subject_id;
  const sanitizedId = sanitizePatientId(candidateId);
  if (sanitizedId) extractedFields.push('patient_id');
  const finalId = sanitizedId || generateUniquePatientId();

  // Demographics
  const demographics = parsed.demographics || {};
  let age: number | null = null;
  const rawAge = demographics.age ?? parsed.age;
  if (rawAge !== undefined && rawAge !== null) {
    const parsedAge = parseInt(String(rawAge), 10);
    if (!isNaN(parsedAge) && parsedAge >= 0 && parsedAge <= 130) {
      age = parsedAge;
      extractedFields.push('age');
    }
  }

  let sex: string | null = null;
  const rawSex = demographics.sex ?? parsed.sex ?? parsed.gender;
  if (rawSex && typeof rawSex === 'string') {
    sex = rawSex.trim().toLowerCase();
    extractedFields.push('sex');
  }

  let height: number | null = null;
  const rawHeight = demographics.height ?? parsed.height ?? demographics.height_cm ?? parsed.height_cm;
  if (rawHeight !== undefined && rawHeight !== null) {
    const numH = parseFloat(String(rawHeight));
    if (!isNaN(numH) && numH > 0) {
      height = numH;
      extractedFields.push('height');
    }
  }

  let weight: number | null = null;
  const rawWeight = demographics.weight ?? parsed.weight ?? demographics.weight_kg ?? parsed.weight_kg;
  if (rawWeight !== undefined && rawWeight !== null) {
    const numW = parseFloat(String(rawWeight));
    if (!isNaN(numW) && numW > 0) {
      weight = numW;
      extractedFields.push('weight');
    }
  }

  // Pregnancy Status (documented explicitly)
  let pregnancyStatus: string | null = null;
  const rawPregnancy =
    demographics.pregnancy_status ??
    parsed.pregnancy_status ??
    demographics.pregnancy ??
    parsed.pregnancy ??
    parsed.clinical_status?.pregnancy_status ??
    parsed.clinical_status?.pregnancy ??
    parsed.safety_history?.pregnancy_status;
  if (rawPregnancy !== undefined && rawPregnancy !== null) {
    pregnancyStatus = String(rawPregnancy).trim().toLowerCase();
    extractedFields.push('pregnancy_status');
    extractedFields.push('demographics.pregnancy_status');
  }

  // Breastfeeding Status (documented explicitly)
  let breastfeedingStatus: boolean | null = null;
  const rawBreastfeeding =
    demographics.breastfeeding_status ??
    parsed.breastfeeding_status ??
    demographics.breastfeeding ??
    parsed.breastfeeding ??
    demographics.lactation_status ??
    parsed.lactation_status ??
    demographics.lactating ??
    parsed.lactating ??
    parsed.clinical_status?.breastfeeding_status ??
    parsed.clinical_status?.breastfeeding ??
    parsed.safety_history?.breastfeeding_status;
  if (rawBreastfeeding !== undefined && rawBreastfeeding !== null) {
    breastfeedingStatus = parseBoolField(rawBreastfeeding);
    extractedFields.push('breastfeeding_status');
    extractedFields.push('demographics.breastfeeding_status');
  }

  // Conditions / Diagnoses
  const conditions: string[] = [];
  const rawConditions = parsed.conditions ?? parsed.condition ?? parsed.diagnoses ?? parsed.diagnosis;
  if (Array.isArray(rawConditions)) {
    for (const c of rawConditions) {
      if (typeof c === 'string') conditions.push(c.trim());
      else if (c && typeof c === 'object' && (c.name || c.condition || c.diagnosis)) {
        conditions.push(String(c.name || c.condition || c.diagnosis).trim());
      }
    }
    if (conditions.length > 0) extractedFields.push('conditions');
  } else if (typeof rawConditions === 'string' && rawConditions.trim()) {
    conditions.push(rawConditions.trim());
    extractedFields.push('conditions');
  } else if (rawConditions && typeof rawConditions === 'object' && (rawConditions.name || rawConditions.condition || rawConditions.diagnosis)) {
    conditions.push(String(rawConditions.name || rawConditions.condition || rawConditions.diagnosis).trim());
    extractedFields.push('conditions');
  }

  // Medical History
  const medicalHistory: string[] = [];
  const rawHistory = parsed.medical_history || parsed.history;
  if (Array.isArray(rawHistory)) {
    for (const h of rawHistory) {
      if (typeof h === 'string') medicalHistory.push(h.trim());
      else if (h && typeof h === 'object' && h.name) medicalHistory.push(String(h.name).trim());
    }
    if (medicalHistory.length > 0) extractedFields.push('medical_history');
  }

  // Medications
  const medications: any[] = [];
  const rawMeds = parsed.medications || parsed.meds;
  if (Array.isArray(rawMeds)) {
    for (const m of rawMeds) {
      if (typeof m === 'string') {
        medications.push({ name: m.trim() });
      } else if (m && typeof m === 'object' && m.name) {
        medications.push({
          name: String(m.name).trim(),
          dose: m.dose ? String(m.dose) : null,
          unit: m.unit ? String(m.unit) : null,
          frequency: m.frequency ? String(m.frequency) : null,
          route: m.route ? String(m.route) : null,
          is_current: m.is_current !== false,
          source: 'uploaded JSON',
          source_document: path.basename(filename),
          original_field: 'medications',
        });
      }
    }
    if (medications.length > 0) extractedFields.push('medications');
  }

  // Laboratory values extraction supporting arrays, objects, and both labs and lab_values
  const labValues: any[] = [];
  const seenLabs = new Map<string, any>();

  const processLabEntry = (testName: string, rawVal: any, rawUnit?: string | null, refRange?: string | null, fieldPath: string = 'labs') => {
    if (!testName || rawVal === undefined || rawVal === null) return;
    
    let numVal: number | null = null;
    let unitStr: string = rawUnit || '';
    let refStr: string | null = refRange || null;

    if (typeof rawVal === 'number') {
      numVal = rawVal;
    } else if (typeof rawVal === 'object' && rawVal !== null) {
      const v = rawVal.value ?? rawVal.numeric_value ?? rawVal.result;
      if (typeof v === 'number') {
        numVal = v;
      } else if (v !== undefined && v !== null) {
        const match = String(v).match(/[-+]?[0-9]*\.?[0-9]+/);
        if (match) numVal = parseFloat(match[0]);
      }
      if (rawVal.unit) unitStr = String(rawVal.unit).trim();
      if (rawVal.reference_range) refStr = String(rawVal.reference_range).trim();
    } else {
      const s = String(rawVal).trim();
      const numMatch = s.match(/[-+]?[0-9]*\.?[0-9]+/);
      if (numMatch) {
        numVal = parseFloat(numMatch[0]);
        const trailing = s.replace(numMatch[0], '').trim();
        if (trailing && !unitStr) {
          unitStr = trailing;
        }
      }
    }

    if (numVal === null || isNaN(numVal)) return;

    const normKey = testName.trim().toLowerCase().replace(/[\s\-_]+/g, '');
    const canonicalName =
      normKey === 'anc' ? 'ANC' :
      normKey === 'platelets' || normKey === 'platelet' || normKey === 'plt' ? 'Platelets' :
      normKey === 'egfr' || normKey === 'gfr' ? 'eGFR' :
      normKey === 'creatinine' || normKey === 'scr' ? 'Serum Creatinine' :
      normKey === 'alt' || normKey === 'sgpt' ? 'ALT' :
      normKey === 'ast' || normKey === 'sgot' ? 'AST' :
      testName.trim();

    if (!unitStr) {
      if (normKey === 'anc' || normKey === 'platelets' || normKey === 'platelet') unitStr = 'cells/mcL';
      else if (normKey === 'egfr' || normKey === 'gfr') unitStr = 'mL/min/1.73m²';
    }

    const labObj = {
      name: canonicalName,
      value: numVal,
      unit: unitStr,
      reference_range: refStr,
      source: 'uploaded JSON',
      source_document: path.basename(filename),
      original_field: fieldPath,
    };

    if (!seenLabs.has(normKey)) {
      seenLabs.set(normKey, labObj);
    } else {
      // Merge if incoming has richer unit or details
      const existing = seenLabs.get(normKey);
      if (!existing.unit && unitStr) existing.unit = unitStr;
      if (!existing.reference_range && refStr) existing.reference_range = refStr;
    }
  };

  // Inspect parsed.labs
  if (parsed.labs) {
    if (Array.isArray(parsed.labs)) {
      for (let i = 0; i < parsed.labs.length; i++) {
        const l = parsed.labs[i];
        if (l && typeof l === 'object') {
          const tName = l.name || l.test_name || l.test || l.analyte;
          processLabEntry(tName, l.value, l.unit, l.reference_range, `labs[${i}]`);
        }
      }
    } else if (typeof parsed.labs === 'object') {
      for (const [key, val] of Object.entries(parsed.labs)) {
        processLabEntry(key, val, null, null, `labs.${key}`);
      }
    }
  }

  // Inspect parsed.lab_values
  if (parsed.lab_values) {
    if (Array.isArray(parsed.lab_values)) {
      for (let i = 0; i < parsed.lab_values.length; i++) {
        const l = parsed.lab_values[i];
        if (l && typeof l === 'object') {
          const tName = l.name || l.test_name || l.test || l.analyte;
          processLabEntry(tName, l.value, l.unit, l.reference_range, `lab_values[${i}]`);
        }
      }
    } else if (typeof parsed.lab_values === 'object') {
      for (const [key, val] of Object.entries(parsed.lab_values)) {
        processLabEntry(key, val, null, null, `lab_values.${key}`);
      }
    }
  }

  // Direct top-level lab fields
  if (parsed.anc !== undefined) processLabEntry('anc', parsed.anc, null, null, 'anc');
  if (parsed.platelets !== undefined) processLabEntry('platelets', parsed.platelets, null, null, 'platelets');
  if (parsed.egfr !== undefined) processLabEntry('egfr', parsed.egfr, null, null, 'egfr');
  if (parsed.eGFR !== undefined) processLabEntry('egfr', parsed.eGFR, null, null, 'eGFR');

  for (const item of seenLabs.values()) {
    labValues.push(item);
  }
  if (labValues.length > 0) {
    extractedFields.push('lab_values');
    extractedFields.push('labs');
  }

  // Allergies extraction
  const allergies: any[] = [];
  const rawAllergies = parsed.allergies;
  if (Array.isArray(rawAllergies)) {
    for (const a of rawAllergies) {
      if (typeof a === 'string') {
        allergies.push({
          allergen: a.trim(),
          reaction: null,
          severity: null,
          source: 'uploaded JSON',
          source_document: path.basename(filename),
          original_field: 'allergies',
          substance: a.trim(),
        });
      } else if (a && typeof a === 'object') {
        const allergenName = a.substance || a.allergen || a.name || a.drug || a.agent || a.description;
        if (allergenName) {
          allergies.push({
            allergen: String(allergenName).trim(),
            reaction: a.reaction ? String(a.reaction).trim() : null,
            severity: a.severity ? String(a.severity).trim() : null,
            source: 'uploaded JSON',
            source_document: path.basename(filename),
            original_field: 'allergies',
            substance: String(allergenName).trim(),
          });
        }
      }
    }
    if (allergies.length > 0) extractedFields.push('allergies');
  }

  // Vital signs / Blood pressure extraction
  let vitalSigns: any = null;
  const rawVitals = parsed.vital_signs || parsed.vitals;
  if (rawVitals && typeof rawVitals === 'object') {
    let systolic: number | null = null;
    let diastolic: number | null = null;
    let bpUnit: string = 'mmHg';

    // Check nested blood_pressure object or string
    const bp = rawVitals.blood_pressure || rawVitals.bp;
    if (bp && typeof bp === 'object') {
      if (bp.systolic !== undefined && bp.systolic !== null) systolic = parseInt(String(bp.systolic), 10);
      else if (bp.systolic_bp !== undefined && bp.systolic_bp !== null) systolic = parseInt(String(bp.systolic_bp), 10);

      if (bp.diastolic !== undefined && bp.diastolic !== null) diastolic = parseInt(String(bp.diastolic), 10);
      else if (bp.diastolic_bp !== undefined && bp.diastolic_bp !== null) diastolic = parseInt(String(bp.diastolic_bp), 10);

      if (bp.unit) bpUnit = String(bp.unit).trim();
    } else if (typeof bp === 'string') {
      const match = bp.match(/(\d+)\s*\/\s*(\d+)/);
      if (match) {
        systolic = parseInt(match[1], 10);
        diastolic = parseInt(match[2], 10);
      }
      if (bp.toLowerCase().includes('mmhg')) bpUnit = 'mmHg';
    }

    // Direct vital fields fallback
    if (systolic === null) {
      if (rawVitals.systolic_bp !== undefined && rawVitals.systolic_bp !== null) systolic = parseInt(String(rawVitals.systolic_bp), 10);
      else if (rawVitals.systolic !== undefined && rawVitals.systolic !== null) systolic = parseInt(String(rawVitals.systolic), 10);
    }
    if (diastolic === null) {
      if (rawVitals.diastolic_bp !== undefined && rawVitals.diastolic_bp !== null) diastolic = parseInt(String(rawVitals.diastolic_bp), 10);
      else if (rawVitals.diastolic !== undefined && rawVitals.diastolic !== null) diastolic = parseInt(String(rawVitals.diastolic), 10);
    }

    const hr =
      rawVitals.heart_rate !== undefined && rawVitals.heart_rate !== null ? parseInt(String(rawVitals.heart_rate), 10) :
      rawVitals.pulse !== undefined && rawVitals.pulse !== null ? parseInt(String(rawVitals.pulse), 10) :
      rawVitals.hr !== undefined && rawVitals.hr !== null ? parseInt(String(rawVitals.hr), 10) : null;

    const spo2 =
      rawVitals.spo2_percent !== undefined && rawVitals.spo2_percent !== null ? parseInt(String(rawVitals.spo2_percent), 10) :
      rawVitals.spo2 !== undefined && rawVitals.spo2 !== null ? parseInt(String(rawVitals.spo2), 10) : null;

    vitalSigns = {
      systolic_bp: systolic,
      diastolic_bp: diastolic,
      heart_rate: hr,
      spo2_percent: spo2,
      unit: bpUnit,
      source: 'uploaded_document',
      source_document: path.basename(filename),
      original_field: 'vital_signs.blood_pressure',
    };

    extractedFields.push('vital_signs');
    if (systolic !== null || diastolic !== null) {
      extractedFields.push('blood_pressure');
    }
  }

  // ECOG Performance Status
  let ecogScore: number | null = null;
  const rawEcog =
    parsed.clinical_status?.ecog_performance_status ??
    parsed.clinical_status?.ecog_score ??
    parsed.clinical_status?.ecog ??
    parsed.ecog_performance_status ??
    parsed.ecog_score ??
    parsed.ecog ??
    parsed.performance_status ??
    demographics.ecog ??
    demographics.ecog_score ??
    parsed.metadata?.ecog_score;
  if (rawEcog !== undefined && rawEcog !== null) {
    let parsedEcog: number | null = null;
    if (typeof rawEcog === 'number') {
      parsedEcog = rawEcog;
    } else {
      const match = String(rawEcog).match(/\d+/);
      if (match) parsedEcog = parseInt(match[0], 10);
    }
    if (parsedEcog !== null && !isNaN(parsedEcog) && parsedEcog >= 0 && parsedEcog <= 4) {
      ecogScore = parsedEcog;
      extractedFields.push('ecog_performance_status');
    }
  }

  // Active serious infection
  const rawInfection =
    parsed.clinical_status?.active_serious_infection ??
    parsed.clinical_status?.serious_infection ??
    parsed.clinical_status?.infection ??
    parsed.active_serious_infection ??
    parsed.serious_infection ??
    parsed.infection ??
    parsed.active_infection;
  const activeSeriousInfection = parseBoolField(rawInfection);
  if (activeSeriousInfection !== null) {
    extractedFields.push('active_serious_infection');
    extractedFields.push('clinical_status.active_serious_infection');
  }

  // Uncontrolled cardiac disease
  const rawCardiac =
    parsed.clinical_status?.uncontrolled_cardiac_disease ??
    parsed.clinical_status?.cardiac_disease ??
    parsed.clinical_status?.cardiac ??
    parsed.uncontrolled_cardiac_disease ??
    parsed.cardiac_disease ??
    parsed.cardiac_history ??
    parsed.cardiac ??
    parsed.uncontrolled_cardiac;
  const uncontrolledCardiacDisease = parseBoolField(rawCardiac);
  if (uncontrolledCardiacDisease !== null) {
    extractedFields.push('uncontrolled_cardiac_disease');
    extractedFields.push('clinical_status.uncontrolled_cardiac_disease');
  }

  // Recent systemic anticancer therapy
  const rawTherapy =
    parsed.medications?.recent_systemic_anticancer_therapy ??
    parsed.medication_history?.recent_systemic_anticancer_therapy ??
    parsed.treatment_history?.recent_systemic_anticancer_therapy ??
    parsed.clinical_status?.recent_systemic_anticancer_therapy ??
    parsed.recent_systemic_anticancer_therapy ??
    parsed.recent_therapy ??
    parsed.systemic_anticancer_therapy ??
    parsed.recent_anticancer_therapy;
  const recentSystemicAnticancerTherapy = parseBoolField(rawTherapy);
  if (recentSystemicAnticancerTherapy !== null) {
    extractedFields.push('recent_systemic_anticancer_therapy');
    extractedFields.push('medications.recent_systemic_anticancer_therapy');
  }

  // Investigational therapy hypersensitivity
  const rawHypersensitivity =
    parsed.medications?.investigational_therapy_hypersensitivity ??
    parsed.medication_history?.investigational_therapy_hypersensitivity ??
    parsed.treatment_history?.investigational_therapy_hypersensitivity ??
    parsed.clinical_status?.investigational_therapy_hypersensitivity ??
    parsed.safety_history?.investigational_therapy_hypersensitivity ??
    parsed.investigational_therapy_hypersensitivity ??
    parsed.severe_hypersensitivity ??
    parsed.hypersensitivity;
  const investigationalTherapyHypersensitivity = parseBoolField(rawHypersensitivity);
  if (investigationalTherapyHypersensitivity !== null) {
    extractedFields.push('investigational_therapy_hypersensitivity');
    extractedFields.push('medications.investigational_therapy_hypersensitivity');
  }

  // Severe hypersensitivity to investigational therapy
  const rawSevereHypersensitivity =
    parsed.safety_history?.severe_hypersensitivity_to_investigational_therapy ??
    parsed.safety_history?.severe_hypersensitivity ??
    parsed.medications?.severe_hypersensitivity_to_investigational_therapy ??
    parsed.treatment_history?.severe_hypersensitivity_to_investigational_therapy ??
    parsed.severe_hypersensitivity_to_investigational_therapy;
  let severeHypersensitivityToInvestigationalTherapy = parseBoolField(rawSevereHypersensitivity);
  if (severeHypersensitivityToInvestigationalTherapy === null && investigationalTherapyHypersensitivity !== null) {
    severeHypersensitivityToInvestigationalTherapy = investigationalTherapyHypersensitivity;
  }
  if (severeHypersensitivityToInvestigationalTherapy !== null) {
    extractedFields.push('severe_hypersensitivity_to_investigational_therapy');
    extractedFields.push('safety_history.severe_hypersensitivity_to_investigational_therapy');
  }

  // If no identifiable patient fields exist, reject with clear error
  if (extractedFields.length === 0) {
    throw new Error(
      'Could not extract patient information from this document. Please verify that the document contains readable patient information or enter the profile manually.'
    );
  }

  // Build standard structured profile with metadata
  const metadataObj: Record<string, any> = {
    source: 'Uploaded JSON',
    source_document: path.basename(filename),
    extraction_timestamp: new Date().toISOString(),
    extracted_fields: extractedFields,
    ...(ecogScore !== null && ecogScore !== undefined ? { ecog_score: ecogScore, ecog_performance_status: ecogScore } : {}),
    ...(activeSeriousInfection !== null && activeSeriousInfection !== undefined ? { active_serious_infection: activeSeriousInfection, infection: activeSeriousInfection } : {}),
    ...(uncontrolledCardiacDisease !== null && uncontrolledCardiacDisease !== undefined ? { uncontrolled_cardiac_disease: uncontrolledCardiacDisease, cardiac_disease: uncontrolledCardiacDisease } : {}),
    ...(recentSystemicAnticancerTherapy !== null && recentSystemicAnticancerTherapy !== undefined ? { recent_systemic_anticancer_therapy: recentSystemicAnticancerTherapy, recent_therapy: recentSystemicAnticancerTherapy } : {}),
    ...(investigationalTherapyHypersensitivity !== null && investigationalTherapyHypersensitivity !== undefined ? { investigational_therapy_hypersensitivity: investigationalTherapyHypersensitivity, severe_hypersensitivity: investigationalTherapyHypersensitivity } : {}),
    ...(severeHypersensitivityToInvestigationalTherapy !== null && severeHypersensitivityToInvestigationalTherapy !== undefined ? { severe_hypersensitivity_to_investigational_therapy: severeHypersensitivityToInvestigationalTherapy } : {}),
    ...(pregnancyStatus !== null && pregnancyStatus !== undefined ? { pregnancy_status: pregnancyStatus } : {}),
    ...(breastfeedingStatus !== null && breastfeedingStatus !== undefined ? { breastfeeding_status: breastfeedingStatus } : {}),
    clinical_status: {
      ecog_performance_status: ecogScore,
      active_serious_infection: activeSeriousInfection,
      uncontrolled_cardiac_disease: uncontrolledCardiacDisease,
    },
    treatment_history: {
      recent_systemic_anticancer_therapy: recentSystemicAnticancerTherapy,
      investigational_therapy_hypersensitivity: investigationalTherapyHypersensitivity,
      severe_hypersensitivity_to_investigational_therapy: severeHypersensitivityToInvestigationalTherapy,
    },
  };

  const profile = buildStructuredProfile({
    patient_profile_id: finalId,
    age,
    sex,
    height,
    weight,
    pregnancy_status: pregnancyStatus,
    breastfeeding_status: breastfeedingStatus,
    demographics: {
      age,
      sex,
      height,
      weight,
      pregnancy_status: pregnancyStatus,
      breastfeeding_status: breastfeedingStatus,
    },
    conditions,
    medical_history: medicalHistory,
    medications,
    lab_values: labValues,
    allergies,
    vital_signs: vitalSigns,
    clinical_notes_raw: null,
    metadata: metadataObj,
  });

  profile.metadata = metadataObj;
  profile.demographics.pregnancy_status = pregnancyStatus;
  profile.demographics.breastfeeding_status = breastfeedingStatus;
  profile.clinical_status = metadataObj.clinical_status;
  profile.treatment_history = metadataObj.treatment_history;

  return {
    profile,
    extractedFields,
    sourceDocument: path.basename(filename),
    sourceType: 'Uploaded JSON',
  };
}
