import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  FileCheck,
  Search,
  User,
  ShieldCheck,
  Info,
  Clock,
  ArrowRight,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { evaluateInclusionCriteria } from '../services/api';
import {
  InclusionEvaluationResponse,
  InclusionCriterionEvaluation,
  InclusionMatchResult,
} from '../types';

interface InclusionMatchingEvaluatorProps {
  initialTrialId?: string | null;
  initialPatientProfileId?: string | null;
}

export const InclusionMatchingEvaluator: React.FC<InclusionMatchingEvaluatorProps> = ({
  initialTrialId = '',
  initialPatientProfileId = '',
}) => {
  const [trialId, setTrialId] = useState<string>(initialTrialId || '');
  const [patientProfileId, setPatientProfileId] = useState<string>(initialPatientProfileId || '');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<InclusionEvaluationResponse | null>(null);
  const [filterResult, setFilterResult] = useState<'all' | InclusionMatchResult>('all');
  const [expandedCriteria, setExpandedCriteria] = useState<Record<string, boolean>>({});

  // Sync if props change
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
      const res = await evaluateInclusionCriteria(trialId.trim(), patientProfileId.trim());
      setEvaluation(res);
      // Auto-expand all criteria
      const initialExpanded: Record<string, boolean> = {};
      res.criteria_results.forEach((c) => {
        initialExpanded[c.criterion_id] = true;
      });
      setExpandedCriteria(initialExpanded);
    } catch (err: any) {
      setError(err.message || 'Failed to evaluate patient against inclusion criteria.');
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

  // Helper to get status badge styling
  const getStatusBadge = (status: InclusionMatchResult) => {
    switch (status) {
      case 'satisfied':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Satisfied
          </span>
        );
      case 'unsatisfied':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            Unsatisfied
          </span>
        );
      case 'unknown':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-900 border border-amber-300">
            <HelpCircle className="w-3.5 h-3.5 text-amber-600" />
            Unknown
          </span>
        );
    }
  };

  const filteredCriteria = evaluation
    ? evaluation.criteria_results.filter((c) => {
        if (filterResult === 'all') return true;
        return c.result === filterResult;
      })
    : [];

  return (
    <section id="inclusion-evaluator" className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      {/* Component Title & Scope Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-sky-700" />
              Inclusion Criteria Evaluation
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic evaluation of trial inclusion criteria against patient profile using 3-state logic (Satisfied, Unsatisfied, Unknown).
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span>Deterministic Priority • Zero Diagnosis Inference</span>
        </div>
      </div>

      {/* Scope Disclaimer Banner */}
      <div className="mt-4 p-3.5 bg-amber-50/80 border border-amber-200 rounded-lg flex items-start gap-2.5">
        <Info className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-amber-900 leading-relaxed">
          <span className="font-semibold text-amber-950">Scope Constraint:</span> This section evaluates{' '}
          <strong className="underline">INCLUSION</strong> criteria prerequisites only.
          Exclusion screening, safety review, and final trial eligibility synthesis are performed in the consolidated assessment.
        </div>
      </div>

      {/* Input Form */}
      <form onSubmit={handleEvaluate} className="mt-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Trial ID (Protocol)
            </label>
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={trialId}
                onChange={(e) => setTrialId(e.target.value)}
                placeholder="e.g. trial-..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Uploaded or extracted trial protocol.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Patient Profile ID
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={patientProfileId}
                onChange={(e) => setPatientProfileId(e.target.value)}
                placeholder="e.g. patient-..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Structured patient profile.
            </p>
          </div>
        </div>

        {/* Action Button */}
        <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
          <button
            type="submit"
            disabled={loading || !trialId.trim() || !patientProfileId.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-sm font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Evaluating Inclusion Criteria...
              </>
            ) : (
              <>
                <FileCheck className="w-4 h-4" />
                Evaluate Inclusion Criteria
              </>
            )}
          </button>
        </div>
      </form>

      {/* Error Message */}
      {error && (
        <div className="mt-4 p-3.5 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Evaluation Error</p>
            <p className="mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Evaluation Results */}
      {evaluation && (
        <div className="mt-8 space-y-6 pt-6 border-t border-slate-200">
          {/* Overall Status Banner */}
          <div
            className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
              evaluation.overall_inclusion_status === 'satisfied'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-950'
                : evaluation.overall_inclusion_status === 'unsatisfied'
                ? 'bg-rose-50 border-rose-200 text-rose-950'
                : 'bg-amber-50 border-amber-200 text-amber-950'
            }`}
          >
            <div className="flex items-center gap-3">
              {evaluation.overall_inclusion_status === 'satisfied' && (
                <div className="w-10 h-10 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700 flex-shrink-0">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
              )}
              {evaluation.overall_inclusion_status === 'unsatisfied' && (
                <div className="w-10 h-10 rounded-full bg-rose-100 border border-rose-300 flex items-center justify-center text-rose-700 flex-shrink-0">
                  <XCircle className="w-6 h-6" />
                </div>
              )}
              {evaluation.overall_inclusion_status === 'unknown' && (
                <div className="w-10 h-10 rounded-full bg-amber-100 border border-amber-300 flex items-center justify-center text-amber-700 flex-shrink-0">
                  <HelpCircle className="w-6 h-6" />
                </div>
              )}

              <div>
                <div className="text-xs uppercase tracking-wider font-bold opacity-80">
                  Overall Inclusion Status
                </div>
                <div className="text-xl font-extrabold capitalize">
                  {evaluation.overall_inclusion_status}
                </div>
                <div className="text-xs mt-0.5 opacity-90">
                  {evaluation.overall_inclusion_status === 'satisfied' &&
                    'All evaluated inclusion criteria are satisfied by patient evidence.'}
                  {evaluation.overall_inclusion_status === 'unsatisfied' &&
                    'At least one inclusion criterion is explicitly unsatisfied.'}
                  {evaluation.overall_inclusion_status === 'unknown' &&
                    'No criteria unsatisfied, but one or more criteria have unknown status due to missing information.'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono opacity-80 self-end sm:self-center">
              <Clock className="w-3.5 h-3.5" />
              <span>{new Date(evaluation.evaluated_at).toLocaleTimeString()}</span>
            </div>
          </div>

          {/* Summary Metric Counters */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
              <div className="text-xs text-slate-500 font-medium">Total Criteria</div>
              <div className="text-2xl font-bold text-slate-800 mt-1">
                {evaluation.summary.total}
              </div>
            </div>

            <div className="bg-emerald-50/70 border border-emerald-200 rounded-lg p-3 text-center">
              <div className="text-xs text-emerald-700 font-semibold">Satisfied</div>
              <div className="text-2xl font-bold text-emerald-700 mt-1">
                {evaluation.summary.satisfied}
              </div>
            </div>

            <div className="bg-rose-50/70 border border-rose-200 rounded-lg p-3 text-center">
              <div className="text-xs text-rose-700 font-semibold">Unsatisfied</div>
              <div className="text-2xl font-bold text-rose-700 mt-1">
                {evaluation.summary.unsatisfied}
              </div>
            </div>

            <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-3 text-center">
              <div className="text-xs text-amber-800 font-semibold">Unknown / Missing</div>
              <div className="text-2xl font-bold text-amber-800 mt-1">
                {evaluation.summary.unknown}
              </div>
            </div>
          </div>

          {/* Criteria Evaluation List Header & Filters */}
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-slate-900">
                Criterion-by-Criterion Traceable Evaluations ({filteredCriteria.length})
              </h3>

              {/* Status Filter Tabs */}
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setFilterResult('all')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    filterResult === 'all'
                      ? 'bg-white text-slate-900 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  All ({evaluation.summary.total})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterResult('satisfied')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    filterResult === 'satisfied'
                      ? 'bg-white text-emerald-700 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Satisfied ({evaluation.summary.satisfied})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterResult('unsatisfied')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    filterResult === 'unsatisfied'
                      ? 'bg-white text-rose-700 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Unsatisfied ({evaluation.summary.unsatisfied})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterResult('unknown')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    filterResult === 'unknown'
                      ? 'bg-white text-amber-800 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Unknown ({evaluation.summary.unknown})
                </button>
              </div>
            </div>

            {/* Criteria Cards */}
            <div className="space-y-3">
              {filteredCriteria.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
                  No criteria match the selected filter ({filterResult}).
                </div>
              ) : (
                filteredCriteria.map((item) => {
                  const isExpanded = !!expandedCriteria[item.criterion_id];
                  return (
                    <div
                      key={item.criterion_id}
                      className="border border-slate-200 rounded-lg overflow-hidden transition-all hover:border-slate-300"
                    >
                      {/* Card Summary Header */}
                      <div
                        onClick={() => toggleExpand(item.criterion_id)}
                        className="p-3.5 bg-slate-50/70 hover:bg-slate-50 cursor-pointer flex items-start justify-between gap-3 select-none"
                      >
                        <div className="flex items-start gap-2.5 flex-1 min-w-0">
                          <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-200 text-slate-700 flex-shrink-0 mt-0.5">
                            {item.criterion_id}
                          </span>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-slate-900 leading-snug">
                              {item.criterion_text}
                            </p>
                            <p className="text-xs text-slate-600 mt-1 line-clamp-1">
                              {item.reason}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2.5 flex-shrink-0">
                          {getStatusBadge(item.result)}
                          <button
                            type="button"
                            className="text-slate-400 hover:text-slate-600 p-1"
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Card Expanded Detail Body */}
                      {isExpanded && (
                        <div className="p-4 bg-white border-t border-slate-200 space-y-3 text-xs">
                          {/* Reason */}
                          <div>
                            <span className="font-semibold text-slate-700">Reasoning & Logic:</span>
                            <p className="mt-0.5 text-slate-800 leading-relaxed bg-slate-50 p-2.5 rounded border border-slate-200 font-mono text-[11px]">
                              {item.reason}
                            </p>
                          </div>

                          {/* Traceable Evidence Grid */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                            {/* Patient Evidence */}
                            <div className="p-2.5 rounded bg-sky-50/50 border border-sky-200">
                              <span className="font-semibold text-sky-900 flex items-center gap-1.5 mb-1.5">
                                <User className="w-3.5 h-3.5 text-sky-700" />
                                Patient Evidence
                              </span>
                              {item.patient_evidence ? (
                                <div className="space-y-1 text-slate-700">
                                  <div>
                                    <span className="text-slate-500">Field:</span>{' '}
                                    <span className="font-medium font-mono text-slate-900">
                                      {item.patient_evidence.field}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-slate-500">Value:</span>{' '}
                                    <span className="font-semibold font-mono text-slate-900">
                                      {typeof item.patient_evidence.value === 'object'
                                        ? JSON.stringify(item.patient_evidence.value)
                                        : String(item.patient_evidence.value)}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-slate-500">Source:</span>{' '}
                                    <span className="italic text-slate-600">
                                      {item.patient_evidence.source}
                                    </span>
                                  </div>
                                </div>
                              ) : (
                                <p className="text-slate-500 italic">
                                  No patient data documented for this criterion.
                                </p>
                              )}
                            </div>

                            {/* Protocol Evidence */}
                            <div className="p-2.5 rounded bg-indigo-50/50 border border-indigo-200">
                              <span className="font-semibold text-indigo-900 flex items-center gap-1.5 mb-1.5">
                                <FileCheck className="w-3.5 h-3.5 text-indigo-700" />
                                Protocol Evidence
                              </span>
                              {item.protocol_evidence ? (
                                <div className="space-y-1 text-slate-700">
                                  {item.protocol_evidence.source_page !== undefined && (
                                    <div>
                                      <span className="text-slate-500">Source Page:</span>{' '}
                                      <span className="font-semibold text-indigo-900">
                                        Page {item.protocol_evidence.source_page}
                                      </span>
                                    </div>
                                  )}
                                  <div>
                                    <span className="text-slate-500">Citation:</span>{' '}
                                    <span className="italic text-slate-800">
                                      "{item.protocol_evidence.text}"
                                    </span>
                                  </div>
                                </div>
                              ) : (
                                <p className="text-slate-500 italic">
                                  Protocol source citation not available.
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Missing Information Callout for Unknown */}
                          {item.result === 'unknown' && item.missing_information && item.missing_information.length > 0 && (
                            <div className="p-2.5 rounded bg-amber-50 border border-amber-200">
                              <span className="font-semibold text-amber-900 flex items-center gap-1.5 mb-1">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
                                Missing Information Required:
                              </span>
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {item.missing_information.map((info, idx) => (
                                  <span
                                    key={idx}
                                    className="px-2 py-0.5 rounded bg-white text-amber-900 border border-amber-300 font-mono text-[11px]"
                                  >
                                    {info}
                                  </span>
                                ))}
                              </div>
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
        </div>
      )}
    </section>
  );
};
