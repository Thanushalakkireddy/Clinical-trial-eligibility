import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AuthoritativeVerdictCard } from '../src/components/AuthoritativeVerdictCard';
import { AssessmentSummarySection } from '../src/components/AssessmentSummarySection';
import { MissingInformationSection } from '../src/components/MissingInformationSection';
import { AssessmentOverviewCards } from '../src/components/AssessmentOverviewCards';
import { VerdictOutcomePresentation } from '../src/components/VerdictOutcomePresentation';
import { TraceableEvidenceSection } from '../src/components/TraceableEvidenceSection';
import { FinalEvaluationResponse } from '../src/types';

// Mock base fixture for MORE_INFORMATION_REQUIRED
const baseMoreInfoEvaluation: FinalEvaluationResponse = {
  trial_id: 'trial_lung_001',
  patient_profile_id: 'pt_102',
  final_decision: 'MORE_INFORMATION_REQUIRED',
  decision_label: 'More Information Required',
  explanation:
    'More information is required to determine eligibility for trial trial_lung_001. Essential protocol criteria remain unknown because documentation (labs.anc, labs.platelets, vital_signs.blood_pressure) is missing.',
  evaluated_at: '2026-09-14T10:00:00Z',
  missing_information: ['labs.anc', 'labs.platelets', 'vital_signs.blood_pressure'],
  summary: {
    final_decision: 'MORE_INFORMATION_REQUIRED',
    inclusion_satisfied_count: 5,
    inclusion_unsatisfied_count: 0,
    inclusion_unknown_count: 2,
    exclusion_triggered_count: 0,
    exclusion_not_triggered_count: 8,
    exclusion_unknown_count: 1,
    contradictions_count: 0,
    silent_exclusions_count: 0,
    disqualifying_factors_count: 0,
    missing_items_count: 3,
  },
  inclusion_summary: {
    total: 7,
    satisfied: 5,
    unsatisfied: 0,
    unknown: 2,
  },
  exclusion_summary: {
    total: 9,
    not_triggered: 8,
    triggered: 0,
    unknown: 1,
  },
  contradiction_summary: {
    total_contradictions: 0,
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    total_silent_exclusions: 0,
    disqualifying_count: 0,
  },
  decision_factors: [
    {
      type: 'inclusion',
      criterion_id: 'INC-006',
      criterion_text: 'Absolute neutrophil count (ANC) >= 1,500/mcL',
      status: 'unknown',
      reason: 'Absolute neutrophil count (ANC) was not documented in lab values.',
      protocol_page: 3,
      patient_field: 'labs.anc',
      protocol_evidence: {
        text: 'ANC must be >= 1,500/mcL',
        source_page: 3,
        trial_id: 'trial_lung_001',
      },
    },
    {
      type: 'inclusion',
      criterion_id: 'INC-007',
      criterion_text: 'Platelets >= 100,000/mcL',
      status: 'unknown',
      reason: 'Platelet count is missing from patient records.',
      protocol_page: 3,
      patient_field: 'labs.platelets',
      protocol_evidence: {
        text: 'Platelets >= 100,000/mcL',
        source_page: 3,
        trial_id: 'trial_lung_001',
      },
    },
    {
      type: 'exclusion',
      criterion_id: 'EXC-003',
      criterion_text: 'Patient must not have uncontrolled hypertension',
      status: 'unknown',
      reason: 'Blood pressure readings are missing.',
      protocol_page: 7,
      patient_field: 'vital_signs.blood_pressure',
      protocol_evidence: {
        text: 'Patient must not have uncontrolled hypertension',
        source_page: 7,
        trial_id: 'trial_lung_001',
      },
    },
    {
      type: 'inclusion',
      criterion_id: 'INC-001',
      criterion_text: 'Age >= 18 years old',
      status: 'satisfied',
      reason: 'Patient age 58 satisfies protocol threshold [18, 130].',
      protocol_page: 1,
      patient_field: 'demographics.age',
      patient_value: 58,
    },
  ],
  protocol_evidence: [
    {
      text: 'ANC must be >= 1,500/mcL',
      source_page: 3,
      trial_id: 'trial_lung_001',
    },
  ],
  patient_evidence: [
    {
      field: 'demographics.age',
      value: 58,
      source: 'patient_demographics',
    },
  ],
};

describe('Eligibility Assessment Results UI', () => {
  // Test 1: MORE_INFORMATION_REQUIRED with 3 missing fields
  describe('1. MORE_INFORMATION_REQUIRED with 3 missing fields', () => {
    it('renders the authoritative verdict with user-friendly text without raw technical paths in main explanation', () => {
      render(<AuthoritativeVerdictCard evaluation={baseMoreInfoEvaluation} />);

      expect(screen.getByText('AUTHORITATIVE VERDICT')).toBeDefined();
      expect(screen.getByText('More Information Required')).toBeDefined();

      // Main explanation should be clean and non-technical
      const explanation = screen.getByText(
        /The system cannot determine eligibility because some information required by the selected clinical trial is missing from the patient record/i
      );
      expect(explanation).toBeDefined();

      // Main explanation paragraph MUST NOT contain raw technical field strings
      expect(explanation.textContent).not.toContain('labs.anc');
      expect(explanation.textContent).not.toContain('labs.platelets');
      expect(explanation.textContent).not.toContain('vital_signs.blood_pressure');
    });

    it('renders the clear summary section with 3 missing items bullet point', () => {
      render(<AssessmentSummarySection evaluation={baseMoreInfoEvaluation} />);

      expect(screen.getByText('SUMMARY')).toBeDefined();
      expect(screen.getByText(/3 required data elements are currently missing/i)).toBeDefined();
      expect(
        screen.getByText(/The system adheres to safety guidelines and does not guess/i)
      ).toBeDefined();
      expect(
        screen.getByText(/Add the missing information to the patient record and run the assessment again/i)
      ).toBeDefined();
    });

    it('renders all 3 missing items with human-readable labels and why-required explanations', () => {
      render(
        <MissingInformationSection
          missingFields={baseMoreInfoEvaluation.missing_information}
          decisionFactors={baseMoreInfoEvaluation.decision_factors}
          protocolEvidence={baseMoreInfoEvaluation.protocol_evidence}
          trialId={baseMoreInfoEvaluation.trial_id}
        />
      );

      // Human-readable labels
      expect(screen.getByText('Absolute Neutrophil Count (ANC)')).toBeDefined();
      expect(screen.getByText('Platelet Count')).toBeDefined();
      expect(screen.getByText('Blood Pressure')).toBeDefined();

      // Secondary technical fields
      expect(screen.getByText(/Technical field: labs.anc/i)).toBeDefined();
      expect(screen.getByText(/Technical field: labs.platelets/i)).toBeDefined();
      expect(screen.getByText(/Technical field: vital_signs.blood_pressure/i)).toBeDefined();

      // Why required linked to criteria
      expect(screen.getByText(/INC-006:/i)).toBeDefined();
      expect(screen.getByText(/Absolute neutrophil count \(ANC\) >= 1,500\/mcL/i)).toBeDefined();
      expect(screen.getByText(/INC-007:/i)).toBeDefined();
      expect(screen.getByText(/EXC-003:/i)).toBeDefined();

      // What should I do next?
      expect(screen.getByText('What should I do next?')).toBeDefined();
      expect(
        screen.getByText(
          'Update the patient record with the missing information and run the eligibility assessment again.'
        )
      ).toBeDefined();
    });
  });

  // Test 2: One missing field
  describe('2. One missing field', () => {
    const singleMissingEvaluation: FinalEvaluationResponse = {
      ...baseMoreInfoEvaluation,
      missing_information: ['demographics.pregnancy_status'],
      summary: {
        ...baseMoreInfoEvaluation.summary,
        missing_items_count: 1,
      },
    };

    it('handles a single missing field with correct singular grammar and count badge', () => {
      render(<AssessmentSummarySection evaluation={singleMissingEvaluation} />);
      expect(screen.getByText(/1 required data element is currently missing/i)).toBeDefined();

      render(
        <MissingInformationSection
          missingFields={singleMissingEvaluation.missing_information}
          decisionFactors={singleMissingEvaluation.decision_factors}
        />
      );

      expect(screen.getByText('Pregnancy Status')).toBeDefined();
      expect(screen.getByText('1 item')).toBeDefined();
    });
  });

  // Test 3: No missing fields
  describe('3. No missing fields', () => {
    const noMissingEvaluation: FinalEvaluationResponse = {
      ...baseMoreInfoEvaluation,
      final_decision: 'ELIGIBLE',
      decision_label: 'Eligible',
      missing_information: [],
      summary: {
        ...baseMoreInfoEvaluation.summary,
        missing_items_count: 0,
      },
    };

    it('does not render MissingInformationSection when missing_information is empty', () => {
      const { container } = render(
        <MissingInformationSection
          missingFields={noMissingEvaluation.missing_information}
          decisionFactors={noMissingEvaluation.decision_factors}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders COMPLETE state on the Missing Information overview card', () => {
      render(<AssessmentOverviewCards evaluation={noMissingEvaluation} />);
      expect(screen.getByText('COMPLETE')).toBeDefined();
      expect(
        screen.getByText('All required patient information is documented in the record.')
      ).toBeDefined();
    });
  });

  // Test 4: ELIGIBLE result
  describe('4. ELIGIBLE result', () => {
    const eligibleEvaluation: FinalEvaluationResponse = {
      ...baseMoreInfoEvaluation,
      final_decision: 'ELIGIBLE',
      decision_label: 'Eligible',
      missing_information: [],
      inclusion_summary: { total: 5, satisfied: 5, unsatisfied: 0, unknown: 0 },
      exclusion_summary: { total: 8, not_triggered: 8, triggered: 0, unknown: 0 },
      decision_factors: [
        {
          type: 'inclusion',
          criterion_id: 'INC-001',
          criterion_text: 'Age >= 18',
          status: 'satisfied',
          reason: 'Patient is 58',
          protocol_page: 1,
        },
      ],
    };

    it('displays positive compliance confirmation and overview states', () => {
      render(<AuthoritativeVerdictCard evaluation={eligibleEvaluation} />);
      expect(screen.getByText('Eligible')).toBeDefined();
      expect(
        screen.getByText(
          /The patient meets all evaluated inclusion criteria, triggers no exclusion criteria, and has no unresolved contradictions/i
        )
      ).toBeDefined();

      render(<VerdictOutcomePresentation evaluation={eligibleEvaluation} />);
      expect(
        screen.getByText('Protocol Compliance & Eligibility Confirmation')
      ).toBeDefined();

      render(<AssessmentOverviewCards evaluation={eligibleEvaluation} />);
      expect(screen.getByText('SATISFIED')).toBeDefined();
      expect(screen.getByText('CLEAR')).toBeDefined();
      expect(screen.getByText('VERIFIED')).toBeDefined();
      expect(screen.getByText('COMPLETE')).toBeDefined();
    });
  });

  // Test 5: NOT_ELIGIBLE result
  describe('5. NOT_ELIGIBLE result', () => {
    const notEligibleEvaluation: FinalEvaluationResponse = {
      ...baseMoreInfoEvaluation,
      final_decision: 'NOT_ELIGIBLE',
      decision_label: 'Not Eligible',
      missing_information: [],
      inclusion_summary: { total: 5, satisfied: 4, unsatisfied: 1, unknown: 0 },
      exclusion_summary: { total: 8, not_triggered: 7, triggered: 1, unknown: 0 },
      decision_factors: [
        {
          type: 'inclusion',
          criterion_id: 'INC-003',
          criterion_text: 'ECOG performance status 0 to 1',
          status: 'unsatisfied',
          reason: 'Patient ECOG performance status 3 exceeds protocol limit of 1.',
          protocol_page: 2,
          patient_field: 'clinical_status.ecog',
          patient_value: 3,
        },
        {
          type: 'exclusion',
          criterion_id: 'EXC-002',
          criterion_text: 'Active untreated CNS metastases',
          status: 'triggered',
          reason: 'Patient has documented active untreated brain metastases.',
          protocol_page: 4,
          patient_field: 'clinical_flags.cns_metastases',
        },
      ],
    };

    it('displays disqualification details with failed inclusion criteria and triggered exclusions', () => {
      const { unmount } = render(<AuthoritativeVerdictCard evaluation={notEligibleEvaluation} />);
      expect(screen.getByText('Not Eligible')).toBeDefined();
      expect(
        screen.getByText(
          /The patient is not eligible for this clinical trial based on documented protocol disqualifications/i
        )
      ).toBeDefined();
      unmount();

      render(<VerdictOutcomePresentation evaluation={notEligibleEvaluation} />);
      expect(screen.getByText('Protocol Disqualification Details')).toBeDefined();
      expect(screen.getByText(/Failed Inclusion Criteria/i)).toBeDefined();
      expect(screen.getByText('INC-003')).toBeDefined();
      expect(
        screen.getByText(/Patient ECOG performance status 3 exceeds protocol limit of 1/i)
      ).toBeDefined();
      expect(screen.getByText(/Triggered Disqualifying Exclusions/i)).toBeDefined();
      expect(screen.getByText('EXC-002')).toBeDefined();
    });
  });

  // Test 6 & 7: Human-readable field mapping and unknown fallback
  describe('6 & 7. Human-readable field mapping & fallback in UI', () => {
    it('renders human-readable names for both known and unknown fields', () => {
      const mixedMissing = [
        'labs.anc',
        'vital_signs.respiratory_rate', // unknown fallback
      ];

      render(<MissingInformationSection missingFields={mixedMissing} />);

      expect(screen.getByText('Absolute Neutrophil Count (ANC)')).toBeDefined();
      expect(screen.getByText('Respiratory Rate')).toBeDefined();
    });
  });

  // Test 8: Criterion and source traceability
  describe('8. Criterion/source traceability', () => {
    it('renders traceable evidence with protocol citations and originating agents', () => {
      render(<TraceableEvidenceSection evaluation={baseMoreInfoEvaluation} />);

      expect(screen.getByText(/Traceable Evidence & Protocol Citations/i)).toBeDefined();
      expect(screen.getByText(/Clinical Decision Support Disclaimer/i)).toBeDefined();

      // Click to expand details
      const expandBtn = screen.getByRole('button', { name: /Expand Details/i });
      fireEvent.click(expandBtn);

      // Verify citations and agent provenance
      expect(screen.getByText('INC-006')).toBeDefined();
      expect(screen.getAllByText('Inclusion Matching Agent')[0]).toBeDefined();
      expect(screen.getAllByText(/Protocol Page: 3/i)[0]).toBeDefined();
      expect(screen.getAllByText(/Source Doc: trial_lung_001/i)[0]).toBeDefined();
    });
  });

  // Test 9: Mobile / responsive card vs table view toggle
  describe('9. Responsive view modes (Cards vs Table)', () => {
    it('allows toggling between Card view and Table view in MissingInformationSection', () => {
      render(
        <MissingInformationSection
          missingFields={['labs.anc', 'labs.platelets']}
          decisionFactors={baseMoreInfoEvaluation.decision_factors}
        />
      );

      // Default is cards
      expect(screen.getByText('Cards')).toBeDefined();
      expect(screen.getByText('Table')).toBeDefined();

      // Click Table view
      const tableBtn = screen.getByRole('button', { name: /Table/i });
      fireEvent.click(tableBtn);

      // Table headers should now be visible
      expect(screen.getByText('Required Information')).toBeDefined();
      expect(screen.getByText('Technical Field')).toBeDefined();
      expect(screen.getByText('Why It Is Required')).toBeDefined();
    });
  });

  // Test 10: Ensure no fabricated missing fields are displayed
  describe('10. Important Safety Rule: No fabricated missing fields', () => {
    it('only renders fields that the backend explicitly marked as missing', () => {
      // Backend only reports labs.anc is missing
      const singleMissing = ['labs.anc'];
      render(
        <MissingInformationSection
          missingFields={singleMissing}
          decisionFactors={baseMoreInfoEvaluation.decision_factors}
        />
      );

      expect(screen.getByText('Absolute Neutrophil Count (ANC)')).toBeDefined();

      // Verify other fields NOT in missingFields are NOT displayed
      expect(screen.queryByText('Platelet Count')).toBeNull();
      expect(screen.queryByText('Blood Pressure')).toBeNull();
      expect(screen.queryByText('Height')).toBeNull();
      expect(screen.queryByText('Weight')).toBeNull();
    });
  });

  // Callback testing: Next action button triggers onNavigateToPatient
  describe('Next action button', () => {
    it('calls onNavigateToPatient when "Update Patient Record" is clicked', () => {
      const mockNavigate = vi.fn();
      render(
        <MissingInformationSection
          missingFields={['labs.anc']}
          onNavigateToPatient={mockNavigate}
        />
      );

      const actionBtn = screen.getByRole('button', { name: /Update Patient Record/i });
      fireEvent.click(actionBtn);
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });
  });
});
