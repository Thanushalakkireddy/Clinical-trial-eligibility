import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileCheck,
  HelpCircle,
  History,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { getAssessmentDetail, getAssessments } from '../services/api';
import type {
  AssessmentDetailResponse,
  AssessmentSummaryResponse,
  FinalEvaluationResponse,
  FinalEligibilityDecision,
  WorkflowStateResponse,
} from '../types';
import { mapWorkflowStateToFinalEvaluation } from '../utils/eligibilityAdapter';
import { AuthoritativeVerdictCard } from './AuthoritativeVerdictCard';
import { AssessmentSummarySection } from './AssessmentSummarySection';
import { MissingInformationSection } from './MissingInformationSection';
import { AssessmentOverviewCards } from './AssessmentOverviewCards';
import { VerdictOutcomePresentation } from './VerdictOutcomePresentation';
import { TraceableEvidenceSection } from './TraceableEvidenceSection';

interface AssessmentHistoryPageProps {
  onRunAssessment?: () => void;
  fetchAssessments?: () => Promise<AssessmentSummaryResponse[]>;
  fetchAssessmentDetail?: (assessmentId: string) => Promise<AssessmentDetailResponse | null>;
}

const DECISION_BADGE_STYLES: Record<string, string> = {
  ELIGIBLE: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  NOT_ELIGIBLE: 'bg-rose-100 text-rose-800 border-rose-300',
  MORE_INFORMATION_REQUIRED: 'bg-amber-100 text-amber-800 border-amber-300',
};

const DECISION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  ELIGIBLE: CheckCircle2,
  NOT_ELIGIBLE: XCircle,
  MORE_INFORMATION_REQUIRED: HelpCircle,
};

/**
 * Rebuild a WorkflowStateResponse from the persisted audit snapshot so the
 * established result components render the stored decision unchanged. Missing
 * sections stay null; the components already render nulls safely.
 */
function snapshotToWorkflow(detail: AssessmentDetailResponse): WorkflowStateResponse {
  const s = detail.snapshot ?? {};
  return {
    assessment_id: detail.assessment_id,
    trial_id: (s.trial_id as string) ?? detail.trial_id,
    patient_profile_id: (s.patient_profile_id as string) ?? detail.patient_profile_id,
    protocol_evidence: (s.protocol_evidence as WorkflowStateResponse['protocol_evidence']) ?? [],
    inclusion_assessment: (s.inclusion_assessment as WorkflowStateResponse['inclusion_assessment']) ?? null,
    exclusion_assessment: (s.exclusion_assessment as WorkflowStateResponse['exclusion_assessment']) ?? null,
    contradiction_assessment:
      (s.contradiction_assessment as WorkflowStateResponse['contradiction_assessment']) ?? null,
    decision_assessment: (s.decision_assessment as WorkflowStateResponse['decision_assessment']) ?? null,
    warnings: (s.warnings as string[]) ?? detail.warnings ?? [],
    errors: (s.errors as string[]) ?? detail.errors ?? [],
    current_step: (s.current_step as string) ?? detail.current_step ?? '',
  };
}

export const AssessmentHistoryPage: React.FC<AssessmentHistoryPageProps> = ({
  onRunAssessment,
  fetchAssessments,
  fetchAssessmentDetail,
}) => {
  const [history, setHistory] = useState<AssessmentSummaryResponse[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AssessmentDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const listAssessments = fetchAssessments ?? getAssessments;
  const loadAssessmentDetail = fetchAssessmentDetail ?? getAssessmentDetail;

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    setHistoryError(null);
    try {
      const items = await listAssessments();
      setHistory(items ?? []);
    } catch (err: any) {
      setHistory((current) => (current.length ? current : []));
      setHistoryError(err?.message || 'Unable to load assessment history.');
    } finally {
      setLoadingHistory(false);
    }
  }, [listAssessments]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleSelect = useCallback(
    async (assessmentId: string) => {
      if (selectedId === assessmentId && detail) {
        return;
      }
      setSelectedId(assessmentId);
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      try {
        const item = await loadAssessmentDetail(assessmentId);
        if (item === null) {
          setDetailError("Assessment not found. It may have been cleaned up from the audit store.");
        } else {
          setDetail(item);
        }
      } catch (err: any) {
        setDetailError(err?.message || 'Unable to load the assessment detail.');
      } finally {
        setDetailLoading(false);
      }
    },
    [loadAssessmentDetail, selectedId, detail]
  );

  const getDecisionBadge = (decision?: string | null) => {
    const key = decision as FinalEligibilityDecision;
    const Icon = DECISION_ICONS[key] ?? HelpCircle;
    const styleClass = DECISION_BADGE_STYLES[key] ?? DECISION_BADGE_STYLES.MORE_INFORMATION_REQUIRED;
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${styleClass}`}
      >
        <Icon className="w-3.5 h-3.5" />
        {key === 'ELIGIBLE' ? 'Eligible' : key === 'NOT_ELIGIBLE' ? 'Not Eligible' : 'More Info Required'}
      </span>
    );
  };

  const renderDetailEvaluation = () => {
    if (!detail) return null;
    const workflow = snapshotToWorkflow(detail);
    const evaluation: FinalEvaluationResponse = mapWorkflowStateToFinalEvaluation(workflow);

    return (
      <div className="space-y-6">
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              {getDecisionBadge(detail.final_decision ?? evaluation.final_decision)}
              <span className="font-semibold text-slate-900 font-mono">{detail.assessment_id}</span>
            </div>
            <span className="inline-flex items-center gap-1.5 text-slate-500">
              <Clock className="w-3.5 h-3.5" />
              {detail.created_at ? new Date(detail.created_at).toLocaleString() : '—'}
            </span>
          </div>

          <div className="flex flex-wrap gap-x-6 gap-y-2 pt-2 border-t border-slate-200 text-slate-600">
            <span>
              Trial: <strong className="text-slate-900 font-mono">{detail.trial_id}</strong>
            </span>
            <span>
              Patient: <strong className="text-slate-900 font-mono">{detail.patient_profile_id}</strong>
            </span>
            <span>
              Status: <strong className="text-slate-900 font-mono">{detail.workflow_status}</strong>
            </span>
            {detail.current_step && (
              <span>
                Step: <strong className="text-slate-900 font-mono">{detail.current_step}</strong>
              </span>
            )}
          </div>

          {(detail.warnings.length > 0 || detail.errors.length > 0) && (
            <div className="pt-2 border-t border-slate-200 space-y-2">
              {detail.errors.length > 0 && (
                <p className="text-rose-800 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>{detail.errors.join(' ')}</span>
                </p>
              )}
              {detail.warnings.length > 0 && (
                <p className="text-amber-800 flex items-start gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>{detail.warnings.join(' ')}</span>
                </p>
              )}
            </div>
          )}
        </div>

        <AuthoritativeVerdictCard evaluation={evaluation} />

        <AssessmentSummarySection evaluation={evaluation} />

        {evaluation.missing_information && evaluation.missing_information.length > 0 && (
          <div>
            <MissingInformationSection
              missingFields={evaluation.missing_information}
              decisionFactors={evaluation.decision_factors}
              protocolEvidence={evaluation.protocol_evidence}
              trialId={evaluation.trial_id}
              onNavigateToPatient={undefined}
            />
          </div>
        )}

        <AssessmentOverviewCards evaluation={evaluation} onSelectCard={() => {}} />

        <VerdictOutcomePresentation evaluation={evaluation} />

        <TraceableEvidenceSection evaluation={evaluation} />
      </div>
    );
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Assessment History & Decision Logs</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Persisted audit trail of patient protocol eligibility evaluations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadHistory}
            disabled={loadingHistory}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingHistory ? 'animate-spin text-sky-600' : 'text-slate-500'}`} />
            Refresh
          </button>
          {onRunAssessment && (
            <button
              type="button"
              onClick={onRunAssessment}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
            >
              <FileCheck className="w-3.5 h-3.5" />
              <span>Assess Patient Eligibility</span>
            </button>
          )}
        </div>
      </div>

      {/* Loading history */}
      {loadingHistory && (
        <div className="flex items-center gap-3 py-10 justify-center text-xs text-slate-500">
          <RefreshCw className="w-4 h-4 animate-spin text-sky-600" />
          Loading assessment history...
        </div>
      )}

      {/* History load error */}
      {!loadingHistory && historyError && (
        <div className="p-4 mt-6 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold">Assessment history unavailable</p>
            <p>{historyError}</p>
          </div>
        </div>
      )}

      {/* Empty history */}
      {!loadingHistory && !historyError && history.length === 0 && (
        <div className="p-12 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
            <History className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-900">No assessments yet.</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              No clinical eligibility evaluations have been persisted. Run an assessment to log
              decisions and audit trails here.
            </p>
          </div>
          {onRunAssessment && (
            <button
              type="button"
              onClick={onRunAssessment}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
            >
              <FileCheck className="w-4 h-4" />
              <span>Assess Patient Eligibility</span>
            </button>
          )}
        </div>
      )}

      {/* History list */}
      {!loadingHistory && !historyError && history.length > 0 && (
        <div className="mt-6 space-y-4">
          {history.map((item) => {
            const isSelected = selectedId === item.assessment_id;
            return (
              <div
                key={item.assessment_id}
                className={`rounded-xl border transition-all space-y-3 ${
                  isSelected
                    ? 'border-sky-300 bg-white shadow-xs ring-1 ring-sky-100'
                    : 'border-slate-200 bg-slate-50/50 hover:bg-white hover:border-sky-200'
                }`}
              >
                <button
                  type="button"
                  onClick={() => handleSelect(item.assessment_id)}
                  className="w-full p-4 text-left flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex flex-wrap items-center gap-2.5">
                      {getDecisionBadge(item.final_decision)}
                      <span className="text-xs font-bold text-slate-900 font-mono break-all">
                        {item.assessment_id}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
                      <span>
                        Trial: <strong className="text-slate-900 font-mono">{item.trial_id}</strong>
                      </span>
                      <span>
                        Patient: <strong className="text-slate-900 font-mono">{item.patient_profile_id}</strong>
                      </span>
                      <span>
                        Status: <strong className="text-slate-900 font-mono">{item.workflow_status}</strong>
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
                      </span>
                      {(item.has_errors || item.warning_count > 0) && (
                        <span className="inline-flex items-center gap-1 text-amber-700">
                          <AlertTriangle className="w-3 h-3" />
                          {item.error_count} error{item.error_count === 1 ? '' : 's'} · {item.warning_count} warning
                          {item.warning_count === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1 text-sky-800 font-semibold text-xs shrink-0">
                    <FileCheck className="w-3.5 h-3.5" />
                    <span>View Details</span>
                    <ChevronRight className={`w-3.5 h-3.5 transition-transform ${isSelected ? 'rotate-90' : ''}`} />
                  </span>
                </button>

                {/* Detail panel */}
                {isSelected && (
                  <div className="px-4 pb-4 pt-1 border-t border-slate-100">
                    {detailLoading ? (
                      <div className="flex items-center gap-3 py-8 justify-center text-xs text-slate-500">
                        <RefreshCw className="w-4 h-4 animate-spin text-sky-600" />
                        Loading assessment details...
                      </div>
                    ) : detailError ? (
                      <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
                        <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                        <div className="space-y-1">
                          <p className="font-semibold">Assessment detail unavailable</p>
                          <p>{detailError}</p>
                        </div>
                      </div>
                    ) : detail ? (
                      <div className="space-y-2">
                        <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                          <ShieldCheck className="w-3 h-3 text-sky-600" />
                          Regulated Audit Record
                        </div>
                        {renderDetailEvaluation()}
                        <p className="pt-2 text-[11px] text-slate-500 leading-relaxed">
                          This is an eligibility-support prototype, not an independent medical
                          decision. Decision traceability:{' '}
                          <strong>Patient evidence</strong> + <strong>Protocol criterion</strong> +{' '}
                          <strong>Agent assessment</strong>.
                        </p>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};