import React, { useState } from 'react';
import {
  FileText,
  User,
  Shield,
  ChevronDown,
  ChevronUp,
  Search,
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  FileSearch,
} from 'lucide-react';
import { FinalEvaluationResponse, DecisionFactor } from '../types';
import { formatPatientField } from '../utils/fieldMapping';

interface TraceableEvidenceSectionProps {
  evaluation: FinalEvaluationResponse;
}

export const TraceableEvidenceSection: React.FC<TraceableEvidenceSectionProps> = ({
  evaluation,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [filterType, setFilterType] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const factors: DecisionFactor[] = evaluation.decision_factors || [];

  // Filter factors
  const filteredFactors = factors.filter((f) => {
    if (filterType !== 'all' && f.type !== filterType) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchText = `${f.criterion_id || ''} ${f.criterion_text || ''} ${f.reason || ''} ${f.patient_field || ''}`.toLowerCase();
      return matchText.includes(q);
    }
    return true;
  });

  const getStatusBadge = (status: string, type: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'satisfied' || s === 'not_triggered' || s === 'pass') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800 border border-emerald-200">
          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
          <span>{status}</span>
        </span>
      );
    }
    if (s === 'unsatisfied' || s === 'triggered' || s === 'fail' || s === 'critical_conflict' || s === 'triggered_hazard') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-100 text-rose-800 border border-rose-200">
          <XCircle className="w-3 h-3 text-rose-600" />
          <span>{status}</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-200">
        <HelpCircle className="w-3 h-3 text-amber-600" />
        <span>{status || 'Unknown'}</span>
      </span>
    );
  };

  const getOriginatingAgent = (type: string): string => {
    switch (type) {
      case 'inclusion':
        return 'Inclusion Matching Agent';
      case 'exclusion':
        return 'Exclusion Detection Agent';
      case 'contradiction':
      case 'silent_exclusion':
        return 'Contradiction Agent';
      default:
        return 'Decision / Reviewer Agent';
    }
  };

  return (
    <div className="space-y-4">
      {/* Toggle Accordion Header */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="w-full p-5 flex items-center justify-between gap-4 text-left hover:bg-slate-50/80 transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-100 text-slate-700">
              <FileSearch className="w-5 h-5 text-sky-800" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <span>Traceable Evidence & Protocol Citations</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                  {factors.length} Citations
                </span>
              </h4>
              <p className="text-xs text-slate-500 mt-0.5">
                Inspect underlying protocol citations, patient values, and originating agent provenance for all evaluated factors.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-sky-900 shrink-0">
            <span>{isOpen ? 'Collapse Evidence' : 'Expand Details'}</span>
            {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>

        {/* Accordion Content */}
        {isOpen && (
          <div className="p-5 border-t border-slate-200 bg-slate-50/50 space-y-4">
            {/* Filter & Search Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                {['all', 'inclusion', 'exclusion', 'contradiction', 'silent_exclusion'].map(
                  (t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setFilterType(t)}
                      className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer capitalize ${
                        filterType === t
                          ? 'bg-sky-900 text-white font-semibold'
                          : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                      }`}
                    >
                      {t === 'all' ? 'All Factors' : t.replace(/_/g, ' ')}
                    </button>
                  )
                )}
              </div>

              <div className="relative w-full sm:w-64">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search criterion or field..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
                />
              </div>
            </div>

            {/* Factor Citations List */}
            {filteredFactors.length === 0 ? (
              <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-xs text-slate-500">
                No decision factors match the current filter.
              </div>
            ) : (
              <div className="space-y-3">
                {filteredFactors.map((factor, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-slate-200 bg-white shadow-2xs space-y-2.5 text-xs"
                  >
                    {/* Header: Type, ID, Status, Agent */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-sky-900 text-xs">
                          {factor.criterion_id || `FACTOR-${idx + 1}`}
                        </span>
                        <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                          {factor.type.replace(/_/g, ' ')}
                        </span>
                        {getStatusBadge(factor.status, factor.type)}
                      </div>

                      <span className="text-[11px] text-slate-500 font-mono">
                        Originating Agent: <strong className="text-slate-700">{getOriginatingAgent(factor.type)}</strong>
                      </span>
                    </div>

                    {/* Criterion Text */}
                    {factor.criterion_text && (
                      <p className="font-medium text-slate-900">
                        {factor.criterion_text}
                      </p>
                    )}

                    {/* Rationale / Reason */}
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-slate-700 leading-relaxed">
                      <span className="font-semibold text-slate-900 mr-1">Evaluation Finding:</span>
                      {factor.reason}
                    </div>

                    {/* Provenance & Citation Metadata */}
                    <div className="pt-2 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-[11px] text-slate-500 font-mono">
                      <div className="flex items-center gap-1">
                        <FileText className="w-3 h-3 text-slate-400 shrink-0" />
                        <span>
                          Source Doc: {factor.protocol_evidence?.trial_id || evaluation.trial_id}
                        </span>
                      </div>

                      <div className="flex items-center gap-1">
                        <FileText className="w-3 h-3 text-slate-400 shrink-0" />
                        <span>
                          Protocol Page: {factor.protocol_page || factor.protocol_evidence?.source_page || 'N/A'}
                        </span>
                      </div>

                      {factor.patient_field && (
                        <div className="flex items-center gap-1">
                          <User className="w-3 h-3 text-slate-400 shrink-0" />
                          <span>Field: {formatPatientField(factor.patient_field)}</span>
                        </div>
                      )}
                    </div>

                    {/* Direct Protocol Excerpt Citation if present */}
                    {factor.protocol_evidence?.text && (
                      <div className="mt-1 p-2 rounded bg-sky-50/50 border border-sky-100 text-[11px] text-sky-950 italic">
                        <span className="font-bold not-italic text-sky-900 mr-1">Protocol Citation Excerpt:</span>
                        "{factor.protocol_evidence.text}"
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Mandatory Clinical Decision Support Disclaimer */}
      <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/80 text-xs text-slate-600 flex items-start gap-3">
        <Shield className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <span className="font-bold text-slate-800 block text-[11px] uppercase tracking-wider">
            Clinical Decision Support Disclaimer
          </span>
          <p className="leading-relaxed">
            This assessment is intended strictly for clinical trial matching and research screening assistance. It does not constitute an independent medical diagnosis, treatment advice, or final clinical enrollment determination. All protocol requirements, patient laboratory values, and exclusion criteria must be verified by the principal investigator and qualified clinical research staff.
          </p>
        </div>
      </div>
    </div>
  );
};
