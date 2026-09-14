import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssessmentHistoryPage } from '../src/components/AssessmentHistoryPage';
import { AssessmentRecordStatus } from '../src/components/AssessmentRecordStatus';
import { mapWorkflowStateToFinalEvaluation } from '../src/utils/eligibilityAdapter';
import {
  AssessmentDetailResponse,
  AssessmentSummaryResponse,
  WorkflowStateResponse,
} from '../src/types';

vi.mock('../src/services/api', () => ({
  getAssessments: vi.fn(),
  getAssessmentDetail: vi.fn(),
}));

import { getAssessments, getAssessmentDetail } from '../src/services/api';
const mockGetAssessments = vi.mocked(getAssessments);
const mockGetAssessmentDetail = vi.mocked(getAssessmentDetail);

const summaryFixture: AssessmentSummaryResponse[] = [
  {
    assessment_id: 'assess-0001-abc',
    trial_id: 'trial_lung_001',
    patient_profile_id: 'pt_102',
    reference_date: '2026-09-14',
    workflow_status: 'COMPLETED',
    final_decision: 'ELIGIBLE',
    current_step: 'END',
    created_at: '2026-09-14T10:00:00Z',
    completed_at: '2026-09-14T10:00:05Z',
    has_errors: false,
    error_count: 0,
    warning_count: 1,
  },
];

const detailFixture: AssessmentDetailResponse = {
  ...summaryFixture[0],
  warnings: ['RAG index contained stale chunks and was refreshed.'],
  errors: [],
  snapshot: {
    version: '1.0',
    trial_id: 'trial_lung_001',
    patient_profile_id: 'pt_102',
    reference_date: '2026-09-14',
    protocol_evidence: [
      {
        chunk_id: 'CHUNK-1',
        trial_id: 'trial_lung_001',
        criterion_id: 'INC-001',
        criterion_type: 'inclusion',
        text: 'Age >= 18 years old',
        score: 0.95,
        source_page: 1,
        source_document: 'trial_lung_001',
      },
    ],
    inclusion_assessment: {
      trial_id: 'trial_lung_001',
      patient_profile_id: 'pt_102',
      overall_status: 'PASS',
      criteria: [
        {
          criterion_id: 'INC-001',
          trial_id: 'trial_lung_001',
          status: 'PASS',
          criterion_text: 'Age >= 18 years old',
          patient_value: 58,
          expected_requirement: 'Age >= 18',
          rationale: 'Patient age satisfies threshold.',
          source_page: 1,
          source_document: 'trial_lung_001',
        },
      ],
      missing_information: [],
      warnings: [],
    },
    exclusion_assessment: {
      trial_id: 'trial_lung_001',
      patient_profile_id: 'pt_102',
      overall_status: 'CLEAR',
      criteria: [],
      missing_information: [],
      warnings: [],
    },
    contradiction_assessment: {
      trial_id: 'trial_lung_001',
      patient_profile_id: 'pt_102',
      findings: [],
      checked_criteria: ['INC-001'],
      warnings: [],
      has_critical_findings: false,
    },
    decision_assessment: {
      trial_id: 'trial_lung_001',
      patient_profile_id: 'pt_102',
      final_status: 'ELIGIBLE',
      requires_human_review: false,
      primary_reasons: ['All mandatory inclusion criteria confirmed met; no exclusions triggered.'],
      decision_evidence: [
        {
          criterion_id: 'INC-001',
          criterion_text: 'Age >= 18 years old',
          patient_value: 58,
          status: 'PASS',
          source_page: 1,
          source_document: 'trial_lung_001',
          originating_agent: 'InclusionMatchingAgent',
        },
      ],
      unresolved_information: [],
      contradiction_findings: [],
      warnings: [],
      disclaimer: 'Deterministic eligibility adjudication.',
    },
    warnings: ['RAG index contained stale chunks and was refreshed.'],
    errors: [],
    current_step: 'END',
  },
  traces: [
    {
      sequence: 1,
      stage: 'start',
      status: 'RUNNING',
      created_at: '2026-09-14T10:00:00Z',
    },
    {
      sequence: 2,
      stage: 'decision',
      status: 'COMPLETED',
      created_at: '2026-09-14T10:00:05Z',
    },
  ],
};

const workflowWithId: WorkflowStateResponse = {
  assessment_id: 'assess-0009-xyz',
  trial_id: 'trial_lung_001',
  patient_profile_id: 'pt_102',
  protocol_evidence: detailFixture.snapshot!.protocol_evidence as any,
  inclusion_assessment: detailFixture.snapshot!.inclusion_assessment as any,
  exclusion_assessment: detailFixture.snapshot!.exclusion_assessment as any,
  contradiction_assessment: detailFixture.snapshot!.contradiction_assessment as any,
  decision_assessment: detailFixture.snapshot!.decision_assessment as any,
  warnings: [],
  errors: [],
  current_step: 'END',
};

const workflowWithoutId: WorkflowStateResponse = {
  ...workflowWithId,
  assessment_id: null,
};

describe('Assessment persistence (Checkpoint 5) — adapter mapping', () => {
  it('carries assessment_id from the workflow response into the final evaluation', () => {
    const evaluation = mapWorkflowStateToFinalEvaluation(workflowWithId);
    expect(evaluation.assessment_id).toBe('assess-0009-xyz');
  });

  it('handles a missing (null) assessment_id gracefully', () => {
    const evaluation = mapWorkflowStateToFinalEvaluation(workflowWithoutId);
    expect(evaluation.assessment_id).toBeNull();
    expect(evaluation.final_decision).toBe('ELIGIBLE');
  });
});

describe('Assessment persistence (Checkpoint 5) — result UI record status', () => {
  it('displays a recorded assessment reference ID in a clean, non-technical way', () => {
    render(<AssessmentRecordStatus assessmentId="assess-0009-xyz" />);
    expect(screen.getByText(/Assessment recorded successfully/i)).toBeDefined();
    expect(screen.getByText(/assess-0009-xyz/i)).toBeDefined();
    expect(screen.queryByText(/not configured/i)).toBeNull();
  });

  it('handles a null assessment_id gracefully without a technical error', () => {
    render(<AssessmentRecordStatus assessmentId={null} />);
    expect(screen.queryByText(/Recorded successfully/i)).toBeNull();
    expect(screen.getByText(/assessment history service is not configured/i)).toBeDefined();
  });
});

describe('Assessment persistence (Checkpoint 5) — history page', () => {
  beforeEach(() => {
    mockGetAssessments.mockReset();
    mockGetAssessmentDetail.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading state while history is being fetched', () => {
    let resolve!: (v: AssessmentSummaryResponse[]) => void;
    mockGetAssessments.mockReturnValue(new Promise((r) => (resolve = r)));

    render(<AssessmentHistoryPage />);
    expect(screen.getByText(/Loading assessment history/i)).toBeDefined();

    resolve([]);
  });

  it('renders persisted history rows with assessment ID, trial, patient, decision, status, and date/time', async () => {
    mockGetAssessments.mockResolvedValue(summaryFixture);

    render(<AssessmentHistoryPage />);

    await screen.findByText('assess-0001-abc');
    expect(screen.getByText(/trial_lung_001/i)).toBeDefined();
    expect(screen.getByText(/pt_102/i)).toBeDefined();
    expect(screen.getByText('COMPLETED')).toBeDefined();
    expect(screen.getByText('Eligible')).toBeDefined();
    expect(screen.queryByText(/No assessments yet/i)).toBeNull();
    expect(mockGetAssessments).toHaveBeenCalledTimes(1);
  });

  it('shows an empty-history state instead of fabricated records when none exist', async () => {
    mockGetAssessments.mockResolvedValue([]);

    render(<AssessmentHistoryPage />);

    const emptyText = await screen.findByText(/No assessments yet/i);
    expect(emptyText).toBeDefined();
    expect(screen.queryByText(/assess-/i)).toBeNull();
  });

  it('shows a clear API error when the backend is unavailable', async () => {
    mockGetAssessments.mockRejectedValue(new Error('Failed to connect to backend'));

    render(<AssessmentHistoryPage />);

    const err = await screen.findByText(/Assessment history unavailable/i);
    expect(err).toBeDefined();
    expect(screen.getByText(/Failed to connect to backend/i)).toBeDefined();
  });

  it('loads and renders the detail when a history row is selected', async () => {
    mockGetAssessments.mockResolvedValue(summaryFixture);
    mockGetAssessmentDetail.mockResolvedValue(detailFixture);

    render(<AssessmentHistoryPage />);

    const rowButton = await screen.findByRole('button', { name: /View Details/i });
    fireEvent.click(rowButton);

    await waitFor(() => {
      expect(mockGetAssessmentDetail).toHaveBeenCalledWith('assess-0001-abc');
    });

    expect(await screen.findByText('Eligible for Clinical Trial')).toBeDefined();
    expect(screen.getAllByText(/trial_lung_001/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/RAG index contained stale chunks/i)).toBeDefined();
    expect(
      screen.getByText(/This is an eligibility-support prototype, not an independent medical decision/i)
    ).toBeDefined();
  });

  it('shows a not-found message when the assessment detail returns null (404)', async () => {
    mockGetAssessments.mockResolvedValue(summaryFixture);
    mockGetAssessmentDetail.mockResolvedValue(null);

    render(<AssessmentHistoryPage />);

    const rowButton = await screen.findByRole('button', { name: /View Details/i });
    fireEvent.click(rowButton);

    expect(
      await screen.findByText(/Assessment not found/i)
    ).toBeDefined();
  });

  it('shows a clear detail-loading indicator while fetching a record', async () => {
    mockGetAssessments.mockResolvedValue(summaryFixture);
    let resolveDetail!: (v: AssessmentDetailResponse | null) => void;
    mockGetAssessmentDetail.mockReturnValue(new Promise((r) => (resolveDetail = r)));

    render(<AssessmentHistoryPage />);

    const rowButton = await screen.findByRole('button', { name: /View Details/i });
    fireEvent.click(rowButton);

    expect(await screen.findByText(/Loading assessment details/i)).toBeDefined();
    resolveDetail(detailFixture);
  });

  it('shows the persisted decision provenance (patient evidence + protocol criterion)', async () => {
    mockGetAssessments.mockResolvedValue(summaryFixture);
    mockGetAssessmentDetail.mockResolvedValue(detailFixture);

    render(<AssessmentHistoryPage />);

    const rowButton = await screen.findByRole('button', { name: /View Details/i });
    fireEvent.click(rowButton);

    await screen.findByText('Eligible for Clinical Trial');
    expect(screen.getByText(/Age >= 18 years old/i)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /Expand Details/i }));
    expect(await screen.findByText('Protocol Page: 1')).toBeDefined();
  });
});