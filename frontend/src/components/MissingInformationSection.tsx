import React, { useState } from 'react';
import {
  AlertTriangle,
  FileText,
  Activity,
  ArrowRight,
  HelpCircle,
  LayoutGrid,
  Table as TableIcon,
  UserCheck,
} from 'lucide-react';
import {
  MissingFieldDetail,
  linkMissingFieldsToCriteria,
} from '../utils/fieldMapping';
import { DecisionFactor, ProtocolEvidenceItem } from '../types';

interface MissingInformationSectionProps {
  missingFields: string[];
  decisionFactors?: DecisionFactor[];
  protocolEvidence?: ProtocolEvidenceItem[];
  trialId?: string;
  onNavigateToPatient?: () => void;
}

export const MissingInformationSection: React.FC<MissingInformationSectionProps> = ({
  missingFields = [],
  decisionFactors = [],
  protocolEvidence = [],
  trialId = '',
  onNavigateToPatient,
}) => {
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  // SAFETY: Strictly compute details ONLY for fields identified by the backend
  const missingDetails: MissingFieldDetail[] = React.useMemo(() => {
    return linkMissingFieldsToCriteria(
      missingFields,
      decisionFactors,
      protocolEvidence,
      trialId
    );
  }, [missingFields, decisionFactors, protocolEvidence, trialId]);

  if (missingDetails.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="missing-info-title" className="p-6 sm:p-7 rounded-xl border border-amber-200 bg-amber-50/40 shadow-xs space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-amber-200/80">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-amber-100 border border-amber-300 text-amber-900 text-xs font-semibold mb-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
            <span>Action Required — Clinical Information Gaps</span>
          </div>
          <h3 id="missing-info-title" className="text-lg sm:text-xl font-bold text-slate-900 flex items-center gap-2">
            <span>Missing Information</span>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-200 text-amber-900">
              {missingDetails.length} {missingDetails.length === 1 ? 'item' : 'items'}
            </span>
          </h3>
          <p className="mt-1 text-xs sm:text-sm text-slate-700 leading-relaxed max-w-3xl">
            The following patient information is required to complete the eligibility assessment but is not available in the current patient record.
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center gap-1 self-start sm:self-auto bg-white/80 p-1 rounded-lg border border-amber-200 text-xs">
          <button
            type="button"
            onClick={() => setViewMode('cards')}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
              viewMode === 'cards'
                ? 'bg-amber-100 text-amber-900 font-semibold shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            <span>Cards</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
              viewMode === 'table'
                ? 'bg-amber-100 text-amber-900 font-semibold shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>Table</span>
          </button>
        </div>
      </div>

      {/* Cards View */}
      {viewMode === 'cards' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {missingDetails.map((item, index) => (
            <div
              key={item.technicalField || index}
              className="p-5 rounded-xl border border-amber-200/90 bg-white shadow-2xs space-y-3 hover:border-amber-300 transition-all flex flex-col justify-between"
            >
              <div className="space-y-2.5">
                {/* Header: Number, Display Name, Status */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5">
                    <span className="w-6 h-6 rounded-full bg-amber-100 text-amber-900 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                      {index + 1}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 leading-snug">
                        {item.displayName}
                      </h4>
                      <span className="font-mono text-[11px] text-slate-500 block mt-0.5">
                        Technical field: {item.technicalField}
                      </span>
                    </div>
                  </div>

                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider bg-amber-100 border border-amber-300 text-amber-800 shrink-0">
                    <HelpCircle className="w-3 h-3 text-amber-600" />
                    <span>Missing</span>
                  </span>
                </div>

                {/* Why Required Box */}
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/90 text-xs text-slate-700 space-y-1.5">
                  <span className="font-bold text-slate-900 block text-[11px] uppercase tracking-wider">
                    Why It Is Required:
                  </span>
                  {item.criterionText ? (
                    <div>
                      {item.criterionId && (
                        <span className="font-mono font-bold text-sky-800 mr-1.5">
                          {item.criterionId}:
                        </span>
                      )}
                      <span className="italic text-slate-800">
                        "{item.criterionText}"
                      </span>
                    </div>
                  ) : (
                    <p>{item.whyRequired}</p>
                  )}
                </div>
              </div>

              {/* Protocol Source & Agent Provenance */}
              <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 font-mono">
                    <FileText className="w-3 h-3 text-slate-400" />
                    Protocol Source: {item.protocolPage ? `Page ${item.protocolPage}` : 'Trial Protocol'}
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                  {item.originatingAgent}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table View */
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-2xs">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-700 font-bold uppercase text-[10px] tracking-wider">
                <th className="py-3 px-4">#</th>
                <th className="py-3 px-4">Required Information</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Technical Field</th>
                <th className="py-3 px-4">Why It Is Required</th>
                <th className="py-3 px-4">Protocol Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {missingDetails.map((item, index) => (
                <tr key={item.technicalField || index} className="hover:bg-slate-50/70 transition-colors">
                  <td className="py-3 px-4 font-bold text-slate-500">{index + 1}</td>
                  <td className="py-3 px-4 font-semibold text-slate-900">{item.displayName}</td>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-200">
                      Missing
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                    {item.technicalField}
                  </td>
                  <td className="py-3 px-4 text-slate-700 max-w-xs">
                    {item.criterionText ? (
                      <span>
                        {item.criterionId && <strong>{item.criterionId} — </strong>}
                        "{item.criterionText}"
                      </span>
                    ) : (
                      item.whyRequired
                    )}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-500 whitespace-nowrap">
                    {item.protocolPage ? `Page ${item.protocolPage}` : 'Protocol Spec'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* "What should I do next?" Guidance Box */}
      <div className="p-4 sm:p-5 rounded-xl border border-sky-200 bg-sky-50/70 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <h4 className="text-sm font-bold text-sky-950 flex items-center gap-1.5">
            <UserCheck className="w-4 h-4 text-sky-700" />
            <span>What should I do next?</span>
          </h4>
          <p className="text-xs text-sky-900 leading-relaxed max-w-2xl">
            Update the patient record with the missing information and run the eligibility assessment again.
          </p>
        </div>

        {onNavigateToPatient && (
          <button
            type="button"
            onClick={onNavigateToPatient}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer shadow-2xs shrink-0"
          >
            <span>Update Patient Record</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </section>
  );
};
