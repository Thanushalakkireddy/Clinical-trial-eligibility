import {
  StructuredPatientProfile,
  ProtocolExtractionResponse,
  InclusionCriterionEvaluation,
  ExclusionCriterionEvaluation,
  ContradictionAlert,
  SilentExclusionTrigger,
  ContradictionEvaluationResponse,
  PatientEvidence,
  ProtocolEvidence,
} from './types';

/**
 * Module 7: Evaluates patient profile, protocol criteria, and prior results
 * to identify internal patient contradictions, protocol conflicts,
 * medication-disease contraindications, and latent silent exclusion hazards.
 */
export function evaluateContradictions(
  trialId: string,
  patientProfileId: string,
  profile: StructuredPatientProfile,
  protocol?: ProtocolExtractionResponse | null,
  inclusionResults?: InclusionCriterionEvaluation[],
  exclusionResults?: ExclusionCriterionEvaluation[]
): ContradictionEvaluationResponse {
  const contradictions: ContradictionAlert[] = [];
  const silentExclusions: SilentExclusionTrigger[] = [];

  const conds = profile.conditions || [];
  const meds = profile.medications || [];
  const labs = profile.lab_values || (profile as any).labs || [];
  const vitals = profile.vital_signs;
  const demos = profile.demographics;

  // 1. Check Male vs Pregnancy
  if (demos?.sex?.toLowerCase() === 'male') {
    const pregCond = conds.find((c) => /pregnan|gestation|intrauterine pregnancy/i.test(c.name));
    if (pregCond) {
      contradictions.push({
        contradiction_id: 'CONT-MALE-PREG',
        category: 'internal_patient_conflict',
        severity: 'critical',
        title: 'Biological Sex vs Pregnancy Status Contradiction',
        description: `Patient documented as biological male, but has active diagnosis '${pregCond.name}'.`,
        conflicting_facts: [
          `Demographics: sex = ${demos.sex}`,
          `Conditions: active diagnosis = ${pregCond.name}`,
        ],
        patient_evidence: [
          { field: 'demographics.sex', value: demos.sex, source: 'demographics' },
          { field: 'conditions', value: pregCond.name, source: 'patient_conditions' },
        ],
        clinical_risk_rationale:
          'Biological impossibility or severe EHR clerical error requiring immediate chart audit before trial enrollment.',
        is_disqualifying: true,
      });
    }
  }

  // 2. Check Beta-Blocker in Asthma
  const hasAsthma = conds.some((c) => /asthma|bronchospasm/i.test(c.name));
  const betaBlocker = meds.find((m) =>
    /propranolol|atenolol|metoprolol|carvedilol|labetalol|bisoprolol/i.test(m.name)
  );
  if (hasAsthma && betaBlocker) {
    contradictions.push({
      contradiction_id: 'CONT-MED-ASTHMA',
      category: 'medication_contraindication',
      severity: 'high',
      title: 'Beta-Blocker Prescribed in Active Asthma',
      description: `Patient with asthma is prescribed beta-blocker '${betaBlocker.name}', risking severe bronchospasm.`,
      conflicting_facts: [
        'Condition: Asthma',
        `Medication: ${betaBlocker.name}`,
      ],
      patient_evidence: [
        { field: 'conditions', value: 'Asthma', source: 'patient_conditions' },
        { field: 'medications', value: betaBlocker.name, source: 'patient_medications' },
      ],
      clinical_risk_rationale:
        'Non-cardioselective or high-dose beta blockade induces airway constriction in reactive airway disease.',
      is_disqualifying: false,
    });
  }

  // 3. Silent Exclusion: Cardiac Pacemaker / Ferromagnetic Implant with Protocol MRI
  const hasPacemaker =
    (profile as any).procedures?.some((p: any) => /pacemaker|defibrillator|icd|implant/i.test(p.name || p)) ||
    conds.some((c) => /pacemaker|implanted defibrillator/i.test(c.name)) ||
    profile.medical_history?.some((c) => /pacemaker|implant/i.test(c.name));

  const protocolRequiresMri =
    protocol?.other_requirements?.some((r) => /mri|magnetic resonance/i.test(r)) ||
    protocol?.inclusion_criteria?.some((c) => /mri|magnetic resonance/i.test(c.text)) ||
    trialId.toLowerCase().includes('mri');

  if (hasPacemaker && protocolRequiresMri) {
    silentExclusions.push({
      trigger_id: 'SILENT-PACEMAKER-MRI',
      name: 'Cardiac Pacemaker vs Protocol MRI Requirement',
      category: 'device_implant',
      clinical_rationale:
        'Patient has an implanted cardiac device that poses a severe safety hazard during protocol-mandated MR imaging procedures.',
      affected_protocol_procedures: ['Contrast Brain MRI', 'Whole Body MR Surveillance'],
      patient_evidence: {
        field: 'procedures',
        value: 'Cardiac pacemaker / implant',
        source: 'patient_procedures',
      },
      severity: 'critical',
      is_hard_disqualification: true,
    });
  }

  // 4. Silent Exclusion: Severe Liver Injury (ALT/AST > 3x ULN with Bilirubin > 2x ULN - Hy's Law Risk)
  const altLab = labs.find((l: any) => /alt|alanine/i.test(l.name));
  const astLab = labs.find((l: any) => /ast|aspartate/i.test(l.name));
  const biliLab = labs.find((l: any) => /bilirubin/i.test(l.name));

  if ((altLab && altLab.value > 150) || (astLab && astLab.value > 150)) {
    if (biliLab && biliLab.value > 2.5) {
      silentExclusions.push({
        trigger_id: 'SILENT-HYS-LAW',
        name: "Acute Severe Hepatic Dysfunction (Hy's Law Indicator)",
        category: 'latent_organ_toxicity',
        clinical_rationale:
          'Concurrent severe transaminase elevation and hyperbilirubinemia indicate high risk of drug-induced liver injury, representing a latent clinical trial hazard.',
        affected_protocol_procedures: ['Investigational Drug Administration'],
        patient_evidence: {
          field: 'labs.liver_panel',
          value: `ALT=${altLab?.value}, AST=${astLab?.value}, Bilirubin=${biliLab?.value}`,
          source: 'patient_labs',
        },
        severity: 'critical',
        is_hard_disqualification: true,
      });
    }
  }

  // Calculate statistics
  let critCount = 0;
  let highCount = 0;
  let medCount = 0;
  let lowCount = 0;
  let disqCount = 0;

  for (const c of contradictions) {
    if (c.severity === 'critical') critCount++;
    else if (c.severity === 'high') highCount++;
    else if (c.severity === 'medium') medCount++;
    else lowCount++;

    if (c.is_disqualifying) disqCount++;
  }

  for (const s of silentExclusions) {
    if (s.is_hard_disqualification) disqCount++;
  }

  let verdict = 'CLEARED_NO_HAZARDS';
  if (silentExclusions.some((s) => s.is_hard_disqualification)) {
    verdict = 'DISQUALIFIED_BY_SILENT_EXCLUSION';
  } else if (contradictions.some((c) => c.is_disqualifying)) {
    verdict = 'DISQUALIFIED_BY_CONTRADICTION';
  } else if (contradictions.length > 0 || silentExclusions.length > 0) {
    verdict = 'WARNING_REQUIRES_INVESTIGATION';
  }

  return {
    trial_id: trialId,
    patient_profile_id: patientProfileId,
    clinical_safety_verdict: verdict,
    has_critical_conflicts: critCount > 0,
    has_silent_exclusions: silentExclusions.length > 0,
    summary: {
      total_contradictions: contradictions.length,
      critical: critCount,
      high: highCount,
      medium: medCount,
      low: lowCount,
      total_silent_exclusions: silentExclusions.length,
      disqualifying_count: disqCount,
    },
    contradictions,
    silent_exclusions: silentExclusions,
    evaluated_at: new Date().toISOString(),
  };
}
