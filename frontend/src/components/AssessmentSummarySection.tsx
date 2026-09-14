import React from 'react';
import { FinalEvaluationResponse } from '../types';
import { ListChecks } from 'lucide-react';

interface AssessmentSummarySectionProps {
  evaluation: FinalEvaluationResponse;
}

export const AssessmentSummarySection: React.FC<AssessmentSummarySectionProps> = ({
  evaluation,
}) => {
  const missingCount = evaluation.missing_information?.length || 0;

  const renderBulletPoints = () => {
    switch (evaluation.final_decision) {
      case 'MORE_INFORMATION_REQUIRED':
        return (
          <>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
              <span>Some information required to evaluate this clinical trial is missing from the patient record.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
              <span>
                {missingCount} required data element{missingCount === 1 ? '' : 's'} {missingCount === 1 ? 'is' : 'are'} currently missing.
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
              <span>Because these values are unknown, some inclusion and exclusion criteria cannot be safely evaluated.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
              <span>The system adheres to safety guidelines and does not guess, presume, or assume missing clinical information.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
              <span>Add the missing information to the patient record and run the assessment again.</span>
            </li>
          </>
        );

      case 'ELIGIBLE':
        return (
          <>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
              <span>All required protocol inclusion criteria have been documented and satisfied.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
              <span>No protocol exclusion criteria or disqualifying factors were triggered.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
              <span>No critical contradictions or latent silent hazards were detected across clinical records.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
              <span>All essential trial data requirements are verified with complete provenance citations.</span>
            </li>
          </>
        );

      case 'NOT_ELIGIBLE':
      default:
        return (
          <>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-2 shrink-0" />
              <span>One or more protocol eligibility requirements were not satisfied or disqualifying criteria were triggered.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-2 shrink-0" />
              <span>Documented patient evidence directly conflicts with the requirements of this clinical trial.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-2 shrink-0" />
              <span>In accordance with clinical trial rules, confirmed disqualifying criteria override unknown or missing data.</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-2 shrink-0" />
              <span>Review the specific disqualifying factors, patient values, and protocol source citations below.</span>
            </li>
          </>
        );
    }
  };

  return (
    <div className="p-5 sm:p-6 rounded-xl border border-slate-200 bg-white shadow-2xs space-y-3">
      <div className="flex items-center gap-2 text-slate-900">
        <ListChecks className="w-4 h-4 text-sky-700 shrink-0" />
        <h4 className="text-sm font-bold uppercase tracking-wider text-slate-800">SUMMARY</h4>
      </div>

      <ul className="space-y-2.5 text-xs sm:text-sm text-slate-700 leading-relaxed">
        {renderBulletPoints()}
      </ul>
    </div>
  );
};
