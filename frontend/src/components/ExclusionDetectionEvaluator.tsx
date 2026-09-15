import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  FileCheck,
  Search,
  User,
  ShieldAlert,
  ShieldCheck,
  Info,
  Clock,
  ArrowRight,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { evaluateExclusionCriteria } from '../services/api';
import {
  ExclusionEvaluationResponse,
  ExclusionCriterionEvaluation,
  ExclusionMatchResult,
} from '../types';

interface ExclusionDetectionEvaluatorProps {
  initialTrialId?: string | null;
  initialPatientProfileId?: string | null;
}

export const ExclusionDetectionEvaluator: React.FC<ExclusionDetectionEvaluatorProps> = ({
  initialTrialId = '',
  initialPatientProfileId = '',
}) => {
  const [trialId, setTrialId] = useState<string>(initialTrialId || '');
  const [patientProfileId, setPatientProfileId] = useState<string>(initialPatientProfileId || '');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<ExclusionEvaluationResponse | null>(null);
  const [filterResult, setFilterResult] = useState<'all' | ExclusionMatchResult>('all');
  const [expandedCriteria, setExpandedCriteria] = useState<Record<string, boolean>>({});

  React.useEffect(() => {
    if (initialTrialId) setTrialId(initialTrialId);
  }, [initialTrialId]);

  React.useEffect(() => {
    if (initialPatientProfileId) setPatientProfileId(initialPatientProfileId);
  }, [initialPatientProfileId]);

  const handleEvaluate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!trialId.trim()) {
      setError('Please enter or select a Clinical Trial ID.');
      return;
    }
    if (!patientProfileId.trim()) {
      setError('Please enter or select a Patient Profile ID.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await evaluateExclusionCriteria(trialId.trim(), patientProfileId.trim());
      setEvaluation(res);
      const initialExpanded: Record<string, boolean> = {};
      res.criteria_results.forEach((c) => {
        initialExpanded[c.criterion_id] = true;
      });
      setExpandedCriteria(initialExpanded);
    } catch (err: any) {
      setError(err.message || 'Failed to evaluate patient against exclusion criteria.');
      setEvaluation(null);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (criterionId: string) => {
    setExpandedCriteria((prev) => ({
      ...prev,
      [criterionId]: !prev[criterionId],
    }));
  };

  const toggleAll = (expand: boolean) => {
    if (!evaluation) return;
    const nextState: Record<string, boolean> = {};
    evaluation.criteria_results.forEach((c) => {
      nextState[c.criterion_id] = expand;
    });
    setExpandedCriteria(nextState);
  };

  const getStatusBadge = (status: ExclusionMatchResult) => {
    switch (status) {
      case 'triggered':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            Triggered
          </span>
        );
      case 'not_triggered':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Not Triggered
          </span>
        );
      case 'unknown':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            <HelpCircle className="w-3.5 h-3.5 text-amber-600" />
            Unknown
          </span>
        );
      default:
        return null;
    }
  };

  const filteredCriteria = evaluation
    ? evaluation.criteria_results.filter((c) => {
        if (filterResult === 'all') return true;
        return c.result === filterResult;
      })
    : [];

  return (
    <div id="exclusion-detection" className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header Banner */}
      <div className="border-b border-slate-200 p-6 bg-slate-50/70">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-md bg-rose-50 text-rose-800 text-xs font-semibold tracking-wide border border-rose-200">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
              <span>Exclusion Criteria Screening</span>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
              Trial Exclusion Evaluation
            </h2>
            <p className="text-xs sm:text-sm text-slate-600 max-w-2xl">
              Compares the clinical trial's exclusion clauses against structured patient records using rigorous
              3-state logic: <span className="font-semibold text-rose-700">Triggered</span>,{' '}
              <span className="font-semibold text-emerald-700">Not Triggered</span>, or{' '}
              <span className="font-semibold text-amber-700">Unknown</span>.
            </p>
          </div>

          <div className="text-xs bg-white border border-slate-200 rounded-lg p-3 max-w-xs space-y-1 text-slate-600 shadow-2xs">
            <div className="font-medium text-slate-900 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-rose-600" /> Clinical Safety Guardrails
            </div>
            <div>&bull; Unknown data NEVER assumes absent or normal</div>
            <div>&bull; Zero diagnosis inferences from lab values</div>
            <div>&bull; Clear provenance for all disqualifiers</div>
          </div>
        </div>
      </div>

      {/* Input Selection Bar */}
      <div className="p-6 border-b border-slate-200 bg-slate-50/70">
        <form onSubmit={handleEvaluate} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="exclusion-trial-id-input" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Clinical Trial ID <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  id="exclusion-trial-id-input"
                  type="text"
                  value={trialId}
                  onChange={(e) => setTrialId(e.target.value)}
                  placeholder="Enter or select Trial ID"
                  className="w-full pl-9 pr-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 transition-all font-mono"
                />
              </div>
            </div>

            <div>
              <label htmlFor="exclusion-patient-profile-id-input" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Structured Patient Profile ID <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  id="exclusion-patient-profile-id-input"
                  type="text"
                  value={patientProfileId}
                  onChange={(e) => setPatientProfileId(e.target.value)}
                  placeholder="Enter or select Patient Profile ID"
                  className="w-full pl-9 pr-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 transition-all font-mono"
                />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-3 pt-1">
            <button
              type="submit"
              id="btn-run-exclusion-evaluation"
              disabled={loading || !trialId.trim() || !patientProfileId.trim()}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-700 active:bg-rose-800 disabled:opacity-50 text-white font-medium text-sm transition-all shadow-sm cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-white" />
                  Evaluating Exclusion Criteria...
                </>
              ) : (
                <>
                  <FileCheck className="w-4 h-4 text-white" />
                  Evaluate Exclusion Criteria
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="m-6 p-4 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-sm text-rose-800">
            <span className="font-semibold">Evaluation Error: </span>
            {error}
          </div>
        </div>
      )}

      {/* Evaluation Results Section */}
      {evaluation && (
        <div className="p-6 space-y-6">
          {/* Overall Exclusion Status Banner */}
          <div
            id="overall-exclusion-status-banner"
            className={`p-5 rounded-xl border transition-all ${
              evaluation.overall_exclusion_status === 'triggered'
                ? 'bg-rose-50 border-rose-300 text-rose-950'
                : evaluation.overall_exclusion_status === 'not_triggered'
                ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
                : 'bg-amber-50 border-amber-300 text-amber-950'
            }`}
          >
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-start gap-3.5">
                <div className="mt-0.5 shrink-0">
                  {evaluation.overall_exclusion_status === 'triggered' && (
                    <div className="w-10 h-10 rounded-full bg-rose-600 text-white flex items-center justify-center shadow-sm">
                      <AlertTriangle className="w-5 h-5" />
                    </div>
                  )}
                  {evaluation.overall_exclusion_status === 'not_triggered' && (
                    <div className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center shadow-sm">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                  )}
                  {evaluation.overall_exclusion_status === 'unknown' && (
                    <div className="w-10 h-10 rounded-full bg-amber-500 text-white flex items-center justify-center shadow-sm">
                      <HelpCircle className="w-5 h-5" />
                    </div>
                  )}
                </div>

                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                      Overall Exclusion Status
                    </span>
                    <span
                      id="overall-exclusion-status-badge"
                      className={`text-xs font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wide ${
                        evaluation.overall_exclusion_status === 'triggered'
                          ? 'bg-rose-200 text-rose-900 border border-rose-400'
                          : evaluation.overall_exclusion_status === 'not_triggered'
                          ? 'bg-emerald-200 text-emerald-900 border border-emerald-400'
                          : 'bg-amber-200 text-amber-900 border border-amber-400'
                      }`}
                    >
                      {evaluation.overall_exclusion_status.replace('_', ' ')}
                    </span>
                  </div>

                  <h3 className="text-lg font-bold text-slate-900 mt-1">
                    {evaluation.overall_exclusion_status === 'triggered' && (
                      <span className="text-rose-700">Patient Triggers Exclusion Criteria</span>
                    )}
                    {evaluation.overall_exclusion_status === 'not_triggered' && (
                      <span className="text-emerald-700">No Exclusion Criteria Triggered</span>
                    )}
                    {evaluation.overall_exclusion_status === 'unknown' && (
                      <span className="text-amber-700">Exclusion Status Incomplete (Missing Data)</span>
                    )}
                  </h3>

                  <p className="text-xs text-slate-700 mt-1 max-w-2xl">
                    {evaluation.overall_exclusion_status === 'triggered' &&
                      'One or more protocol exclusion criteria have been triggered by the patient profile. This introduces potential trial disqualification.'}
                    {evaluation.overall_exclusion_status === 'not_triggered' &&
                      'All evaluated exclusion criteria were determined as not triggered based on the documented clinical profile.'}
                    {evaluation.overall_exclusion_status === 'unknown' &&
                      'No criteria are confirmed triggered, but one or more exclusion clauses lack sufficient clinical data to evaluate. Cannot assume normal or absent.'}
                  </p>
                </div>
              </div>

              {/* Timestamp and Traceability Metadata */}
              <div className="text-right text-xs text-slate-500 space-y-1">
                <div className="flex items-center justify-end gap-1 font-mono">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  {new Date(evaluation.evaluated_at).toLocaleTimeString()}
                </div>
                <div>Trial: <span className="font-mono text-slate-700 font-medium">{evaluation.trial_id}</span></div>
                <div>Patient: <span className="font-mono text-slate-700 font-medium">{evaluation.patient_profile_id}</span></div>
              </div>
            </div>
          </div>

          {/* Metric Summary Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-slate-800">{evaluation.summary.total}</div>
              <div className="text-xs text-slate-600 font-medium mt-0.5">Total Criteria</div>
            </div>
            <div className="bg-rose-50/70 border border-rose-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-rose-700">{evaluation.summary.triggered}</div>
              <div className="text-xs text-rose-700 font-medium mt-0.5">Triggered</div>
            </div>
            <div className="bg-emerald-50/70 border border-emerald-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-emerald-700">{evaluation.summary.not_triggered}</div>
              <div className="text-xs text-emerald-700 font-medium mt-0.5">Not Triggered</div>
            </div>
            <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-amber-700">{evaluation.summary.unknown}</div>
              <div className="text-xs text-amber-700 font-medium mt-0.5">Unknown (Missing)</div>
            </div>
          </div>

          {/* Filter Tabs & Expand/Collapse Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
            <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg text-xs font-medium">
              <button
                type="button"
                id="filter-all-exclusion"
                onClick={() => setFilterResult('all')}
                className={`px-3 py-1.5 rounded-md transition-all ${
                  filterResult === 'all'
                    ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                All ({evaluation.summary.total})
              </button>
              <button
                type="button"
                id="filter-triggered"
                onClick={() => setFilterResult('triggered')}
                className={`px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 ${
                  filterResult === 'triggered'
                    ? 'bg-rose-600 text-white shadow-2xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Triggered ({evaluation.summary.triggered})
              </button>
              <button
                type="button"
                id="filter-not-triggered"
                onClick={() => setFilterResult('not_triggered')}
                className={`px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 ${
                  filterResult === 'not_triggered'
                    ? 'bg-emerald-600 text-white shadow-2xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Not Triggered ({evaluation.summary.not_triggered})
              </button>
              <button
                type="button"
                id="filter-unknown-exclusion"
                onClick={() => setFilterResult('unknown')}
                className={`px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 ${
                  filterResult === 'unknown'
                    ? 'bg-amber-600 text-white shadow-2xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Unknown ({evaluation.summary.unknown})
              </button>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={() => toggleAll(true)}
                className="px-2.5 py-1 text-slate-600 hover:text-slate-900 font-medium hover:bg-slate-100 rounded"
              >
                Expand All
              </button>
              <span className="text-slate-300">&bull;</span>
              <button
                type="button"
                onClick={() => toggleAll(false)}
                className="px-2.5 py-1 text-slate-600 hover:text-slate-900 font-medium hover:bg-slate-100 rounded"
              >
                Collapse All
              </button>
            </div>
          </div>

          {/* Criteria Evaluation Cards List */}
          <div className="space-y-3.5">
            {filteredCriteria.length === 0 ? (
              <div className="p-8 text-center text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
                No criteria match the selected filter.
              </div>
            ) : (
              filteredCriteria.map((item: ExclusionCriterionEvaluation) => {
                const isExpanded = expandedCriteria[item.criterion_id] ?? true;
                const isTriggered = item.result === 'triggered';
                const isNotTriggered = item.result === 'not_triggered';
                const isUnknown = item.result === 'unknown';

                return (
                  <div
                    key={item.criterion_id}
                    id={`criterion-card-${item.criterion_id}`}
                    className={`rounded-lg border transition-all ${
                      isTriggered
                        ? 'border-rose-300 bg-rose-50/20'
                        : isNotTriggered
                        ? 'border-emerald-200 bg-emerald-50/15'
                        : 'border-amber-200 bg-amber-50/15'
                    }`}
                  >
                    {/* Header Row */}
                    <div
                      onClick={() => toggleExpand(item.criterion_id)}
                      className="p-4 flex items-start justify-between gap-4 cursor-pointer hover:bg-slate-50/60 transition-colors select-none"
                    >
                      <div className="flex items-start gap-3">
                        <span className="font-mono text-xs font-bold px-2 py-1 rounded bg-slate-100 text-slate-700 border border-slate-200 shrink-0">
                          {item.criterion_id}
                        </span>
                        <div>
                          <p className="text-sm font-semibold text-slate-900 leading-snug">
                            {item.criterion_text}
                          </p>
                          {item.protocol_evidence?.source_page && (
                            <span className="text-xs text-slate-600 font-mono mt-0.5 block">
                              Source Page: {item.protocol_evidence.source_page}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        {getStatusBadge(item.result)}
                        <button
                          type="button"
                          className="text-slate-400 hover:text-slate-600 p-1"
                          aria-label="Toggle details"
                        >
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    {/* Expandable Body */}
                    {isExpanded && (
                      <div className="px-4 pb-4 pt-1 border-t border-slate-100 space-y-3 text-xs">
                        {/* Clinical Rationale */}
                        <div className="bg-white/80 p-3 rounded-md border border-slate-200/70">
                          <span className="font-semibold text-slate-700 block mb-1">
                            Clinical Evaluation Reason:
                          </span>
                          <p className="text-slate-800 leading-relaxed">{item.reason}</p>
                        </div>

                        {/* Patient Evidence & Protocol Traceability Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {/* Patient Evidence */}
                          <div className="bg-white/90 p-3 rounded-md border border-slate-200/70 space-y-1.5">
                            <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                              <User className="w-3.5 h-3.5 text-slate-500" /> Patient Fact Evidence:
                            </span>
                            {item.patient_evidence ? (
                              <div className="space-y-1 text-slate-800">
                                <div>
                                  <span className="text-slate-600 font-medium">Field: </span>
                                  <span className="font-mono text-slate-900">{item.patient_evidence.field}</span>
                                </div>
                                <div>
                                  <span className="text-slate-600 font-medium">Value: </span>
                                  <span className="font-semibold text-slate-900">
                                    {String(item.patient_evidence.value)}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-slate-600 font-medium">Provenance: </span>
                                  <span className="text-slate-700 font-mono text-[11px] bg-slate-100 px-1.5 py-0.5 rounded">
                                    {item.patient_evidence.source}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="text-slate-600 italic">
                                No matching record or documented fact found in patient profile.
                              </p>
                            )}
                          </div>

                          {/* Protocol Citation */}
                          <div className="bg-white/90 p-3 rounded-md border border-slate-200/70 space-y-1.5">
                            <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                              <FileCheck className="w-3.5 h-3.5 text-slate-500" /> Protocol Citation:
                            </span>
                            <div className="space-y-1 text-slate-800">
                              <div>
                                <span className="text-slate-600 font-medium">Protocol Clause: </span>
                                <span className="text-slate-900 italic">"{item.criterion_text}"</span>
                              </div>
                              {item.protocol_evidence?.source_page && (
                                <div>
                                  <span className="text-slate-600 font-medium">Document Page: </span>
                                  <span className="font-mono text-slate-900">
                                    Page {item.protocol_evidence.source_page}
                                  </span>
                                </div>
                              )}
                              <div>
                                <span className="text-slate-600 font-medium">Trial ID: </span>
                                <span className="font-mono text-slate-900">
                                  {item.protocol_evidence?.trial_id || evaluation.trial_id}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Missing Information Checklist */}
                        {item.missing_information && item.missing_information.length > 0 && (
                          <div className="bg-amber-50/80 border border-amber-200 p-3 rounded-md text-amber-900 space-y-1">
                            <span className="font-semibold flex items-center gap-1.5 text-amber-800">
                              <HelpCircle className="w-3.5 h-3.5 text-amber-600" /> Missing Patient Information Required:
                            </span>
                            <ul className="list-disc list-inside space-y-0.5 text-amber-950 font-medium pl-1">
                              {item.missing_information.map((info, idx) => (
                                <li key={idx}>{info}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
