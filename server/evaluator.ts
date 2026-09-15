import {
  ExtractedCriterion,
  StructuredPatientProfile,
  InclusionCriterionEvaluation,
  InclusionEvaluationResponse,
  InclusionMatchResult,
  ExclusionCriterionEvaluation,
  ExclusionEvaluationResponse,
  ExclusionMatchResult,
  ProtocolEvidence,
  PatientEvidence,
} from './types';

// Helper to normalize strings for comparison
function norm(s: string): string {
  return s.toLowerCase().trim();
}

/**
 * Deterministic Inclusion Evaluator enforcing 3-state logic:
 *   - satisfied
 *   - unsatisfied
 *   - unknown
 */
export function evaluateInclusionCriterion(
  criterion: ExtractedCriterion,
  profile: StructuredPatientProfile
): InclusionCriterionEvaluation {
  const text = criterion.text || criterion.raw_text || '';
  const lower = norm(text);

  const protoEvidence: ProtocolEvidence = {
    text,
    source_page: criterion.source_page || criterion.page_number,
    trial_id: criterion.trial_id,
  };

  // 1. Age check
  const ageMatch = lower.match(/age\s*(?:>=|≥|\b(?:greater than or equal to|at least)\b)\s*(\d+)(?:\s*(?:and|to|-)\s*(?:<=|≤|\b(?:less than or equal to|up to)\b)?\s*(\d+))?/);
  if (ageMatch || lower.includes('age')) {
    const minAge = ageMatch ? parseInt(ageMatch[1], 10) : 18;
    const maxAge = ageMatch && ageMatch[2]
      ? parseInt(ageMatch[2], 10)
      : (lower.match(/(?:<=|≤|\b(?:less than or equal to|up to)\b)\s*(\d+)/)?.[1]
        ? parseInt(lower.match(/(?:<=|≤|\b(?:less than or equal to|up to)\b)\s*(\d+)/)![1], 10)
        : 130);

    const patientAge = profile.demographics.age;
    if (patientAge === undefined || patientAge === null) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'Patient age was not documented in demographics.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['demographics.age'],
        confidence_score: 0.95,
      };
    }

    const satisfies = patientAge >= minAge && patientAge <= maxAge;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: satisfies ? 'satisfied' : 'unsatisfied',
      reason: satisfies
        ? `Patient age ${patientAge} is within the protocol range [${minAge}, ${maxAge}].`
        : `Patient age ${patientAge} is outside the protocol range [${minAge}, ${maxAge}].`,
      patient_evidence: {
        field: 'demographics.age',
        value: patientAge,
        source: 'patient_demographics',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // 2. BMI check
  if (lower.includes('bmi') || lower.includes('body mass index')) {
    const patientBmi = profile.demographics.bmi;
    if (patientBmi === undefined || patientBmi === null) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'Patient BMI was not documented or could not be computed.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['demographics.bmi'],
        confidence_score: 0.95,
      };
    }
    const satisfies = patientBmi >= 18.5 && patientBmi <= 35.0;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: satisfies ? 'satisfied' : 'unsatisfied',
      reason: satisfies
        ? `Patient BMI of ${patientBmi} satisfies the healthy range requirement.`
        : `Patient BMI of ${patientBmi} does not meet protocol range.`,
      patient_evidence: {
        field: 'demographics.bmi',
        value: patientBmi,
        source: 'patient_demographics',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // 3. ECOG Performance Status
  if (lower.includes('ecog') || lower.includes('performance status')) {
    const ecogMatch = lower.match(/ecog.*?<=\s*(\d+)/) || lower.match(/ecog.*?0\s*(?:or|-)\s*(\d+)/) || lower.match(/ecog\s*(?:score\s*)?(?:of\s*)?(\d+)/);
    const maxEcog = ecogMatch ? parseInt(ecogMatch[1] || ecogMatch[2], 10) : 1;

    // Check metadata or clinical status or profile
    const rawEcog =
      (profile.metadata as any)?.ecog_score ??
      (profile.metadata as any)?.ecog_performance_status ??
      profile.clinical_status?.ecog_performance_status ??
      (profile as any).clinical_status?.ecog ??
      (profile as any).ecog;
    if (rawEcog !== undefined && rawEcog !== null) {
      const ecogVal = Number(rawEcog);
      const satisfies = !isNaN(ecogVal) && ecogVal <= maxEcog;
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: satisfies ? 'satisfied' : 'unsatisfied',
        reason: `Patient ECOG performance status of ${ecogVal} (protocol threshold <= ${maxEcog}).`,
        patient_evidence: {
          field: 'clinical_status.ecog',
          value: ecogVal,
          source: 'clinical_notes',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'ECOG performance status is not documented in the patient record.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['clinical_status.ecog_performance_status'],
      confidence_score: 0.9,
    };
  }

  // 4. Lab Values (ANC, Platelets, eGFR, HbA1c, ALT, AST, Bilirubin)
  // Check ANC and Platelets combined or individual
  const hasAnc = /\banc\b/i.test(lower) || lower.includes('neutrophil');
  const hasPlt = lower.includes('platelet');
  if (hasAnc || hasPlt) {
    const ancLab = profile.lab_values.find((l) => l.normalized_name === 'anc');
    const pltLab = profile.lab_values.find((l) => l.normalized_name === 'platelets');

    const missingFields: string[] = [];
    if (!ancLab && hasAnc) missingFields.push('labs.anc');
    if (!pltLab && hasPlt) missingFields.push('labs.platelets');

    if (missingFields.length > 0) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: `Required laboratory panel (${missingFields.join(', ')}) was not documented.`,
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: missingFields,
        confidence_score: 0.9,
      };
    }

    // Evaluate
    let ancPass = true;
    let pltPass = true;
    const reasons: string[] = [];

    if (ancLab) {
      ancPass = ancLab.value >= 1500;
      reasons.push(`ANC: ${ancLab.value} (threshold >= 1,500/mcL, ${ancPass ? 'Pass' : 'Fail'})`);
    }
    if (pltLab) {
      pltPass = pltLab.value >= 100000;
      reasons.push(`Platelets: ${pltLab.value} (threshold >= 100,000/mcL, ${pltPass ? 'Pass' : 'Fail'})`);
    }

    const satisfies = ancPass && pltPass;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: satisfies ? 'satisfied' : 'unsatisfied',
      reason: reasons.join('; '),
      patient_evidence: {
        field: 'labs.hematology',
        value: { anc: ancLab?.value, platelets: pltLab?.value },
        source: 'patient_labs',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // eGFR lab check
  if (lower.includes('egfr') || lower.includes('glomerular filtration')) {
    const egfrLab = profile.lab_values.find((l) => l.normalized_name === 'egfr');
    if (!egfrLab) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'Estimated glomerular filtration rate (eGFR) laboratory panel is not documented.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['labs.egfr'],
        confidence_score: 0.9,
      };
    }

    // Check threshold (e.g. >= 20 or >= 30)
    const thresholdMatch = lower.match(/(?:>=|≥|\b(?:greater than or equal to|at least)\b)\s*(\d+)/);
    const threshold = thresholdMatch ? parseFloat(thresholdMatch[1]) : 20;

    const satisfies = egfrLab.value >= threshold;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: satisfies ? 'satisfied' : 'unsatisfied',
      reason: satisfies
        ? `Patient eGFR of ${egfrLab.value} mL/min/1.73m² satisfies minimum threshold (>= ${threshold}).`
        : `Patient eGFR of ${egfrLab.value} mL/min/1.73m² is below required threshold (>= ${threshold}).`,
      patient_evidence: {
        field: 'labs.egfr',
        value: egfrLab.value,
        source: 'patient_labs',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // HbA1c lab check
  if (lower.includes('hba1c') || lower.includes('hemoglobin a1c') || lower.includes('a1c')) {
    const a1cLab = profile.lab_values.find((l) => l.normalized_name === 'hba1c');
    if (!a1cLab) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'HbA1c laboratory test is not documented in patient record.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['labs.hba1c'],
        confidence_score: 0.9,
      };
    }

    const minMatch = lower.match(/(?:between|>=|≥)\s*(\d+(?:\.\d+)?)/);
    const maxMatch = lower.match(/(?:and|to|<=|≤)\s*(\d+(?:\.\d+)?)/);
    const minVal = minMatch ? parseFloat(minMatch[1]) : 7.0;
    const maxVal = maxMatch ? parseFloat(maxMatch[1]) : 10.5;

    const satisfies = a1cLab.value >= minVal && a1cLab.value <= maxVal;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: satisfies ? 'satisfied' : 'unsatisfied',
      reason: satisfies
        ? `Patient HbA1c ${a1cLab.value}% is within required range [${minVal}%, ${maxVal}%].`
        : `Patient HbA1c ${a1cLab.value}% is outside required range [${minVal}%, ${maxVal}%].`,
      patient_evidence: {
        field: 'labs.hba1c',
        value: a1cLab.value,
        source: 'patient_labs',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // 5. Conditions check (e.g. RCC, clear cell, solid tumor, diabetes)
  if (
    lower.includes('rcc') ||
    lower.includes('renal cell') ||
    lower.includes('carcinoma') ||
    lower.includes('solid tumor') ||
    lower.includes('tumor') ||
    lower.includes('cancer') ||
    lower.includes('malignancy') ||
    lower.includes('neoplasm') ||
    lower.includes('diabetes') ||
    lower.includes('hypertension')
  ) {
    const matchingCond = profile.conditions.find((c) => {
      const cLower = norm(c.name);
      if (lower.includes('diabetes') && cLower.includes('diabetes')) return true;
      if (lower.includes('clear cell') && (cLower.includes('clear cell') || cLower.includes('rcc') || cLower.includes('renal cell'))) return true;
      if (lower.includes('rcc') && (cLower.includes('rcc') || cLower.includes('renal cell'))) return true;
      if (lower.includes('hypertension') && cLower.includes('hypertension')) return true;
      if (lower.includes('solid tumor') && (cLower.includes('solid tumor') || cLower.includes('tumor') || cLower.includes('carcinoma') || cLower.includes('cancer'))) return true;
      if (lower.includes('tumor') && (cLower.includes('tumor') || cLower.includes('cancer') || cLower.includes('carcinoma'))) return true;
      if (lower.includes('cancer') && (cLower.includes('cancer') || cLower.includes('carcinoma') || cLower.includes('tumor'))) return true;
      if (cLower && (lower.includes(cLower) || cLower.includes(lower))) return true;
      return false;
    });

    if (matchingCond) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'satisfied',
        reason: `Documented active diagnosis: "${matchingCond.name}".`,
        patient_evidence: {
          field: 'conditions',
          value: matchingCond.name,
          source: matchingCond.source,
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: `No documented clinical diagnosis matching criterion in active conditions list.`,
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['conditions.diagnosis'],
      confidence_score: 0.85,
    };
  }

  // 6. Medication requirements (e.g. Metformin)
  if (lower.includes('metformin') || lower.includes('lisinopril') || lower.includes('therapy')) {
    const medName = lower.includes('metformin') ? 'metformin' : lower.includes('lisinopril') ? 'lisinopril' : '';
    if (medName) {
      const matchingMed = profile.medications.find((m) => norm(m.name).includes(medName));
      if (matchingMed) {
        return {
          criterion_id: criterion.criterion_id,
          criterion_text: text,
          result: 'satisfied',
          reason: `Documented current therapy: "${matchingMed.name}".`,
          patient_evidence: {
            field: 'medications',
            value: matchingMed.name,
            source: matchingMed.source,
          },
          protocol_evidence: protoEvidence,
          missing_information: [],
          confidence_score: 1.0,
        };
      }
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unsatisfied',
        reason: `Required therapy with ${medName} was not found in patient medications.`,
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 0.9,
      };
    }
  }

  // Default fallback for general criteria
  return {
    criterion_id: criterion.criterion_id,
    criterion_text: text,
    result: 'unknown',
    reason: 'Insufficient documented clinical records to determine criterion satisfaction deterministically.',
    patient_evidence: null,
    protocol_evidence: protoEvidence,
    missing_information: ['clinical_documentation'],
    confidence_score: 0.7,
  };
}

/**
 * Deterministic Exclusion Evaluator enforcing 3-state logic:
 *   - triggered (patient meets exclusion condition -> disqualified!)
 *   - not_triggered (patient explicitly does not meet exclusion condition)
 *   - unknown (insufficient data)
 */
export function evaluateExclusionCriterion(
  criterion: ExtractedCriterion,
  profile: StructuredPatientProfile
): ExclusionCriterionEvaluation {
  const text = criterion.text || criterion.raw_text || '';
  const lower = norm(text);

  const protoEvidence: ProtocolEvidence = {
    text,
    source_page: criterion.source_page || criterion.page_number,
    trial_id: criterion.trial_id,
  };

  // 1. Pregnancy / Breastfeeding check (sex-specific)
  if (
    lower.includes('pregnant') ||
    lower.includes('pregnancy') ||
    lower.includes('breastfeeding') ||
    lower.includes('lactating')
  ) {
    const sex = profile.demographics.sex?.toLowerCase();
    if (sex === 'male') {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'not_triggered',
        reason: 'Patient biological sex is documented as Male; pregnancy/lactation exclusion is non-applicable.',
        patient_evidence: {
          field: 'demographics.sex',
          value: profile.demographics.sex,
          source: 'patient_demographics',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    if (sex === 'female') {
      const rawPreg =
        profile.demographics?.pregnancy_status !== undefined && profile.demographics?.pregnancy_status !== null
          ? profile.demographics.pregnancy_status
          : (profile.metadata as any)?.pregnancy_status !== undefined && (profile.metadata as any)?.pregnancy_status !== null
          ? (profile.metadata as any).pregnancy_status
          : (profile as any).pregnancy_status !== undefined && (profile as any).pregnancy_status !== null
          ? (profile as any).pregnancy_status
          : null;

      const rawBf =
        profile.demographics?.breastfeeding_status !== undefined && profile.demographics?.breastfeeding_status !== null
          ? profile.demographics.breastfeeding_status
          : (profile.metadata as any)?.breastfeeding_status !== undefined && (profile.metadata as any)?.breastfeeding_status !== null
          ? (profile.metadata as any).breastfeeding_status
          : (profile as any).breastfeeding_status !== undefined && (profile as any).breastfeeding_status !== null
          ? (profile as any).breastfeeding_status
          : null;

      const isPositivePreg =
        rawPreg === true ||
        (typeof rawPreg === 'string' && ['positive', 'pregnant', 'yes', 'true'].includes(rawPreg.trim().toLowerCase()));

      const isPositiveBf =
        rawBf === true ||
        (typeof rawBf === 'string' && ['positive', 'breastfeeding', 'lactating', 'yes', 'true'].includes(rawBf.trim().toLowerCase()));

      if (isPositivePreg || isPositiveBf) {
        return {
          criterion_id: criterion.criterion_id,
          criterion_text: text,
          result: 'triggered',
          reason: `Patient is documented as ${isPositivePreg ? 'pregnant' : 'breastfeeding'}.`,
          patient_evidence: {
            field: isPositivePreg ? 'demographics.pregnancy_status' : 'demographics.breastfeeding_status',
            value: isPositivePreg ? String(rawPreg) : String(rawBf),
            source: 'patient_demographics',
          },
          protocol_evidence: protoEvidence,
          missing_information: [],
          confidence_score: 1.0,
        };
      }

      const isNegativePreg =
        rawPreg === false ||
        (typeof rawPreg === 'string' &&
          ['not_pregnant', 'not pregnant', 'negative', 'false', 'no', 'non-pregnant', 'denies'].includes(rawPreg.trim().toLowerCase()));

      if (isNegativePreg && !isPositiveBf) {
        return {
          criterion_id: criterion.criterion_id,
          criterion_text: text,
          result: 'not_triggered',
          reason: `Patient biological sex is Female; documented non-pregnant status ("${rawPreg}")${rawBf !== null && rawBf !== undefined ? ` and breastfeeding status (${String(rawBf)})` : ''}. Exclusion condition not met.`,
          patient_evidence: {
            field: 'demographics.pregnancy_status',
            value: String(rawPreg),
            source: 'patient_demographics',
          },
          protocol_evidence: protoEvidence,
          missing_information: [],
          confidence_score: 1.0,
        };
      }

      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'Patient is female; pregnancy test/lactation status is not documented.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['demographics.pregnancy_status'],
        confidence_score: 0.9,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Patient biological sex and pregnancy status are not documented.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['demographics.sex', 'demographics.pregnancy_status'],
      confidence_score: 0.8,
    };
  }

  // 2. Renal Impairment / eGFR lab threshold
  if (
    lower.includes('renal impairment') ||
    lower.includes('egfr') ||
    lower.includes('creatinine') ||
    lower.includes('kidney')
  ) {
    const egfrLab = profile.lab_values.find((l) => l.normalized_name === 'egfr');
    const thresholdMatch = lower.match(/(?:<|less than)\s*(\d+)/);
    const threshold = thresholdMatch ? parseFloat(thresholdMatch[1]) : 30;

    if (!egfrLab) {
      // Check if severe renal impairment condition is documented
      const hasCkd = profile.conditions.some((c) =>
        /severe renal|end-stage renal|esrd|dialysis/i.test(c.name)
      );
      if (hasCkd) {
        return {
          criterion_id: criterion.criterion_id,
          criterion_text: text,
          result: 'triggered',
          reason: 'Documented diagnosis of severe renal disease / impairment.',
          patient_evidence: {
            field: 'conditions',
            value: 'Severe Renal Impairment',
            source: 'medical_history',
          },
          protocol_evidence: protoEvidence,
          missing_information: [],
          confidence_score: 1.0,
        };
      }
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'unknown',
        reason: 'Renal panel (eGFR) is not documented to determine renal impairment exclusion.',
        patient_evidence: null,
        protocol_evidence: protoEvidence,
        missing_information: ['labs.egfr'],
        confidence_score: 0.9,
      };
    }

    // Triggered if eGFR < threshold (e.g. 28 < 30 -> triggered!)
    const triggered = egfrLab.value < threshold;
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: triggered ? 'triggered' : 'not_triggered',
      reason: triggered
        ? `Patient eGFR of ${egfrLab.value} mL/min/1.73m² is below threshold (< ${threshold}), triggering renal impairment exclusion.`
        : `Patient eGFR of ${egfrLab.value} mL/min/1.73m² is >= ${threshold}; exclusion condition not met.`,
      patient_evidence: {
        field: 'labs.egfr',
        value: egfrLab.value,
        source: 'patient_labs',
      },
      protocol_evidence: protoEvidence,
      missing_information: [],
      confidence_score: 1.0,
    };
  }

  // 3. Central Nervous System (CNS) / Brain Metastases
  if (lower.includes('cns') || lower.includes('brain') || lower.includes('metastases')) {
    const hasCns = profile.conditions.some((c) =>
      /brain|cns|central nervous/i.test(c.name)
    );
    if (hasCns) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented central nervous system or brain metastatic condition.',
        patient_evidence: {
          field: 'conditions',
          value: 'CNS / Brain involvement',
          source: 'patient_conditions',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    // In medical records, absence of CNS notes without brain MRI is technically unknown or not reported
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'No brain imaging (MRI/CT) or neurology notes documented to confirm absence of CNS metastases.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['clinical_status.cns_metastases'],
      confidence_score: 0.85,
    };
  }

  // 4. Prior Therapy (anti-PD-1, anti-CTLA-4, immunotherapy)
  if (
    lower.includes('pd-1') ||
    lower.includes('ctla-4') ||
    lower.includes('checkpoint') ||
    lower.includes('immunotherapy') ||
    lower.includes('pembrolizumab') ||
    lower.includes('nivolumab') ||
    lower.includes('ipilimumab')
  ) {
    const hasPriorMeds = profile.medications.some((m) =>
      /pd-1|ctla-4|checkpoint|pembrolizumab|nivolumab|ipilimumab/i.test(m.name)
    );
    if (hasPriorMeds) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented prior/current therapy with prohibited checkpoint inhibitor medication.',
        patient_evidence: {
          field: 'medications',
          value: 'Checkpoint inhibitor therapy',
          source: 'patient_medications',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Prior oncologic treatment history is not fully documented in medication log.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['medications.prior_oncology_therapy'],
      confidence_score: 0.85,
    };
  }

  // 5. Uncontrolled Hypertension (Systolic BP > 160)
  if (lower.includes('hypertension') || lower.includes('blood pressure') || lower.includes('systolic')) {
    const vitals = profile.vital_signs;
    if (vitals && vitals.systolic_bp !== undefined && vitals.systolic_bp !== null) {
      const bpMatch = lower.match(/(?:>|greater than)\s*(\d+)/);
      const bpThreshold = bpMatch ? parseFloat(bpMatch[1]) : 160;

      const triggered = vitals.systolic_bp > bpThreshold;
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: triggered ? 'triggered' : 'not_triggered',
        reason: triggered
          ? `Patient systolic blood pressure is ${vitals.systolic_bp} mmHg (> ${bpThreshold}), triggering exclusion.`
          : `Patient systolic blood pressure is ${vitals.systolic_bp} mmHg (<= ${bpThreshold}); within acceptable limits.`,
        patient_evidence: {
          field: 'vital_signs.systolic_bp',
          value: vitals.systolic_bp,
          source: vitals.source || 'patient_vitals',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Blood pressure vitals were not documented.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['vital_signs.blood_pressure'],
      confidence_score: 0.85,
    };
  }

  // 6. Diabetic Ketoacidosis
  if (lower.includes('ketoacidosis') || lower.includes('dka')) {
    const hasDka = profile.conditions.some((c) => /ketoacidosis|dka/i.test(c.name));
    if (hasDka) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented history of diabetic ketoacidosis.',
        patient_evidence: {
          field: 'conditions',
          value: 'Diabetic Ketoacidosis',
          source: 'medical_history',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }
    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'No emergency medical history regarding diabetic ketoacidosis documented.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['medical_history.ketoacidosis'],
      confidence_score: 0.8,
    };
  }

  // 7. Active Serious Infection
  if (
    lower.includes('serious infection') ||
    lower.includes('active serious infection') ||
    lower.includes('active infection') ||
    (lower.includes('infection') && !lower.includes('hiv') && !lower.includes('hepatitis'))
  ) {
    const hasActiveInfection = profile.conditions.some((c) =>
      /active serious infection|sepsis|severe infection|pneumonia|bacteremia|systemic infection/i.test(c.name) && c.status === 'active'
    );
    if (hasActiveInfection) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented diagnosis of active serious infection.',
        patient_evidence: {
          field: 'conditions',
          value: 'Active Serious Infection',
          source: 'patient_conditions',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    const infectionStatus =
      profile.clinical_status?.active_serious_infection ??
      (profile.metadata as any)?.active_serious_infection ??
      (profile.metadata as any)?.infection;
    if (infectionStatus === false) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'not_triggered',
        reason: 'Patient record explicitly documents no active serious infection.',
        patient_evidence: {
          field: 'clinical_status.active_serious_infection',
          value: false,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }
    if (infectionStatus === true) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Patient has documented active serious infection.',
        patient_evidence: {
          field: 'clinical_status.active_serious_infection',
          value: true,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Active serious infection status is not documented in patient record.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['clinical_status.active_serious_infection'],
      confidence_score: 0.85,
    };
  }

  // 8. Uncontrolled Cardiac Disease
  if (
    lower.includes('cardiac disease') ||
    lower.includes('uncontrolled cardiac') ||
    lower.includes('heart failure') ||
    lower.includes('cardiovascular disease') ||
    (lower.includes('cardiac') && !lower.includes('pacemaker'))
  ) {
    const hasCardiacCond = profile.conditions.some((c) =>
      /uncontrolled cardiac|congestive heart failure|severe cardiac|myocardial infarction|unstable angina|class iii|class iv/i.test(c.name) && c.status === 'active'
    );
    if (hasCardiacCond) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented diagnosis of uncontrolled/severe cardiac disease.',
        patient_evidence: {
          field: 'conditions',
          value: 'Uncontrolled Cardiac Disease',
          source: 'patient_conditions',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    const cardiacStatus =
      profile.clinical_status?.uncontrolled_cardiac_disease ??
      (profile.metadata as any)?.uncontrolled_cardiac_disease ??
      (profile.metadata as any)?.cardiac_disease;
    if (cardiacStatus === false) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'not_triggered',
        reason: 'Patient record explicitly documents no uncontrolled cardiac disease.',
        patient_evidence: {
          field: 'clinical_status.uncontrolled_cardiac_disease',
          value: false,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }
    if (cardiacStatus === true) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Patient has documented uncontrolled cardiac disease.',
        patient_evidence: {
          field: 'clinical_status.uncontrolled_cardiac_disease',
          value: true,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Cardiac disease status is not documented in patient record.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['clinical_status.uncontrolled_cardiac_disease'],
      confidence_score: 0.85,
    };
  }

  // 9. Severe Hypersensitivity
  if (
    lower.includes('hypersensitivity') ||
    lower.includes('severe allergy') ||
    lower.includes('anaphylaxis')
  ) {
    const hasSevereAllergy = profile.allergies.some((a) =>
      /severe|anaphylaxis|life-threatening/i.test(a.severity || '') ||
      /anaphylaxis|shock|angioedema/i.test(a.reaction || '') ||
      /investigational|study drug|antibody/i.test(a.allergen)
    );
    if (hasSevereAllergy) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Documented history of severe hypersensitivity or anaphylaxis.',
        patient_evidence: {
          field: 'allergies',
          value: 'Severe Hypersensitivity',
          source: 'patient_allergies',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    const hyperStatus =
      (profile.treatment_history as any)?.investigational_therapy_hypersensitivity ??
      (profile.treatment_history as any)?.severe_hypersensitivity_to_investigational_therapy ??
      (profile.metadata as any)?.investigational_therapy_hypersensitivity ??
      (profile.metadata as any)?.severe_hypersensitivity;
    if (hyperStatus === false) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'not_triggered',
        reason: 'Patient record explicitly documents no severe hypersensitivity or investigational therapy contraindications.',
        patient_evidence: {
          field: 'allergies.severe_hypersensitivity',
          value: false,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }
    if (hyperStatus === true) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Patient has documented severe hypersensitivity to study/investigational therapy.',
        patient_evidence: {
          field: 'allergies.severe_hypersensitivity',
          value: true,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Hypersensitivity history is not documented in patient record.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['allergies.severe_hypersensitivity'],
      confidence_score: 0.85,
    };
  }

  // 10. Recent Systemic Anticancer Therapy (within 14 days)
  if (
    lower.includes('anticancer') ||
    lower.includes('systemic anticancer') ||
    lower.includes('recent therapy') ||
    lower.includes('chemotherapy')
  ) {
    const hasActiveAnticancer = profile.medications.some((m) =>
      /chemotherapy|cytotoxic|cisplatin|carboplatin|paclitaxel|doxorubicin|pembrolizumab|nivolumab|ipilimumab|anticancer/i.test(m.name) && m.is_current
    );
    if (hasActiveAnticancer) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Patient has current documented systemic anticancer therapy.',
        patient_evidence: {
          field: 'medications',
          value: 'Current systemic anticancer therapy',
          source: 'patient_medications',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    const recentTherapyStatus =
      profile.treatment_history?.recent_systemic_anticancer_therapy ??
      (profile.metadata as any)?.recent_systemic_anticancer_therapy ??
      (profile.metadata as any)?.recent_therapy;
    if (recentTherapyStatus === false) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'not_triggered',
        reason: 'Patient record explicitly documents no recent systemic anticancer therapy within prohibited window.',
        patient_evidence: {
          field: 'medications.recent_systemic_anticancer_therapy',
          value: false,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }
    if (recentTherapyStatus === true) {
      return {
        criterion_id: criterion.criterion_id,
        criterion_text: text,
        result: 'triggered',
        reason: 'Patient has documented recent systemic anticancer therapy within prohibited window.',
        patient_evidence: {
          field: 'medications.recent_systemic_anticancer_therapy',
          value: true,
          source: 'patient_record',
        },
        protocol_evidence: protoEvidence,
        missing_information: [],
        confidence_score: 1.0,
      };
    }

    return {
      criterion_id: criterion.criterion_id,
      criterion_text: text,
      result: 'unknown',
      reason: 'Recent systemic anticancer therapy history is not documented in patient record.',
      patient_evidence: null,
      protocol_evidence: protoEvidence,
      missing_information: ['medications.recent_systemic_anticancer_therapy'],
      confidence_score: 0.85,
    };
  }

  // Default fallback for other exclusion criteria
  return {
    criterion_id: criterion.criterion_id,
    criterion_text: text,
    result: 'unknown',
    reason: 'Insufficient documented clinical records to determine exclusion criterion deterministically.',
    patient_evidence: null,
    protocol_evidence: protoEvidence,
    missing_information: ['clinical_documentation'],
    confidence_score: 0.7,
  };
}

/**
 * Evaluates all inclusion criteria for a trial against a patient profile.
 */
export function evaluateAllInclusionCriteria(
  trialId: string,
  patientProfileId: string,
  criteria: ExtractedCriterion[],
  profile: StructuredPatientProfile
): InclusionEvaluationResponse {
  const safeCriteria = Array.isArray(criteria) ? criteria : [];
  const results: InclusionCriterionEvaluation[] = safeCriteria.map((c) =>
    evaluateInclusionCriterion(c, profile)
  );

  let satisfiedCount = 0;
  let unsatisfiedCount = 0;
  let unknownCount = 0;

  for (const r of results) {
    if (r.result === 'satisfied') satisfiedCount++;
    else if (r.result === 'unsatisfied') unsatisfiedCount++;
    else unknownCount++;
  }

  let overall: InclusionMatchResult;
  if (results.length === 0) {
    overall = 'unsatisfied';
  } else if (unsatisfiedCount > 0) {
    overall = 'unsatisfied';
  } else if (unknownCount > 0) {
    overall = 'unknown';
  } else {
    overall = 'satisfied';
  }

  return {
    trial_id: trialId,
    patient_profile_id: patientProfileId,
    overall_inclusion_status: overall,
    criteria_results: results,
    summary: {
      total: results.length,
      satisfied: satisfiedCount,
      unsatisfied: unsatisfiedCount,
      unknown: unknownCount,
    },
    evaluated_at: new Date().toISOString(),
  };
}

/**
 * Evaluates all exclusion criteria for a trial against a patient profile.
 */
export function evaluateAllExclusionCriteria(
  trialId: string,
  patientProfileId: string,
  criteria: ExtractedCriterion[],
  profile: StructuredPatientProfile
): ExclusionEvaluationResponse {
  const safeCriteria = Array.isArray(criteria) ? criteria : [];
  const results: ExclusionCriterionEvaluation[] = safeCriteria.map((c) =>
    evaluateExclusionCriterion(c, profile)
  );

  let triggeredCount = 0;
  let notTriggeredCount = 0;
  let unknownCount = 0;

  for (const r of results) {
    if (r.result === 'triggered') triggeredCount++;
    else if (r.result === 'not_triggered') notTriggeredCount++;
    else unknownCount++;
  }

  let overall: ExclusionMatchResult;
  if (results.length === 0) {
    overall = 'unknown';
  } else if (triggeredCount > 0) {
    overall = 'triggered';
  } else if (unknownCount > 0) {
    overall = 'unknown';
  } else {
    overall = 'not_triggered';
  }

  return {
    trial_id: trialId,
    patient_profile_id: patientProfileId,
    overall_exclusion_status: overall,
    criteria_results: results,
    summary: {
      total: results.length,
      triggered: triggeredCount,
      not_triggered: notTriggeredCount,
      unknown: unknownCount,
    },
    evaluated_at: new Date().toISOString(),
  };
}
