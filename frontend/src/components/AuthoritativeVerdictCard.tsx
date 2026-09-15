import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  AlertTriangle,
  Copy,
  Check,
  Clock,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { FinalEvaluationResponse } from '../types';

interface AuthoritativeVerdictCardProps {
  evaluation: FinalEvaluationResponse;
  onCopyJson?: () => void;
  copied?: boolean;
}

export const AuthoritativeVerdictCard: React.FC<AuthoritativeVerdictCardProps> = ({
  evaluation,
  onCopyJson,
  copied = false,
}) => {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState<boolean>(false);

  const getVerdictExplanation = () => {
    switch (evaluation.final_decision) {
      case 'MORE_INFORMATION_REQUIRED':
        if (evaluation.decision_factors?.some((f) => f.criterion_id === 'PROTOCOL-VALIDATION-REQUIRED')) {
          return 'Protocol validation failed: The selected document contains zero identifiable clinical trial eligibility criteria. In accordance with clinical trial protocol safety principles, an assessment requires verified protocol criteria.';
        }
        return 'The system cannot determine eligibility because some information required by the selected clinical trial is missing from the patient record. Please provide the missing details below and run the assessment again.';
      case 'ELIGIBLE':
        return 'The patient meets all evaluated inclusion criteria, triggers no exclusion criteria, and has no unresolved contradictions or missing data elements for this clinical trial.';
      case 'NOT_ELIGIBLE':
        return 'The patient is not eligible for this clinical trial based on documented protocol disqualifications. See the specific failed inclusion criteria or triggered exclusion criteria below.';
      default:
        return evaluation.explanation;
    }
  };

  const getThemeStyles = () => {
    switch (evaluation.final_decision) {
      case 'ELIGIBLE':
        return {
          bg: 'bg-emerald-50/70',
          border: 'border-emerald-200',
          iconBg: 'bg-emerald-100',
          iconColor: 'text-emerald-700',
          titleColor: 'text-emerald-950',
          badgeBg: 'bg-emerald-100',
          badgeText: 'text-emerald-800',
        };
      case 'NOT_ELIGIBLE':
        return {
          bg: 'bg-rose-50/70',
          border: 'border-rose-200',
          iconBg: 'bg-rose-100',
          iconColor: 'text-rose-700',
          titleColor: 'text-rose-950',
          badgeBg: 'bg-rose-100',
          badgeText: 'text-rose-800',
        };
      case 'MORE_INFORMATION_REQUIRED':
      default:
        return {
          bg: 'bg-amber-50/70',
          border: 'border-amber-200',
          iconBg: 'bg-amber-100',
          iconColor: 'text-amber-700',
          titleColor: 'text-amber-950',
          badgeBg: 'bg-amber-100',
          badgeText: 'text-amber-800',
        };
    }
  };

  const theme = getThemeStyles();

  return (
    <div className={`p-6 sm:p-7 rounded-xl border ${theme.border} ${theme.bg} shadow-xs space-y-4`}>
      {/* Top Bar: Icon, Title, Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3.5">
          <div
            className={`w-12 h-12 rounded-xl ${theme.iconBg} flex items-center justify-center ${theme.iconColor} shrink-0 shadow-2xs`}
          >
            {evaluation.final_decision === 'ELIGIBLE' && <ShieldCheck className="w-7 h-7" />}
            {evaluation.final_decision === 'NOT_ELIGIBLE' && <ShieldAlert className="w-7 h-7" />}
            {evaluation.final_decision === 'MORE_INFORMATION_REQUIRED' && (
              <HelpCircle className="w-7 h-7" />
            )}
          </div>

          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
              AUTHORITATIVE VERDICT
            </span>
            <h3 className={`text-xl sm:text-2xl font-bold ${theme.titleColor} flex items-center gap-2`}>
              {evaluation.decision_label}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-center">
          {onCopyJson && (
            <button
              type="button"
              onClick={onCopyJson}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-700">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-slate-500" />
                  <span>Copy Audit JSON</span>
                </>
              )}
            </button>
          )}

          <span className="text-xs text-slate-500 font-mono flex items-center gap-1 px-2.5 py-1 bg-white/80 border border-slate-200 rounded-lg">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            {new Date(evaluation.evaluated_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      </div>

      {/* High-level, Non-Technical Explanation */}
      <div className="p-4 rounded-lg bg-white/90 border border-slate-200/80 shadow-2xs text-slate-800 text-sm leading-relaxed">
        <p className="font-medium text-slate-900">{getVerdictExplanation()}</p>
      </div>

      {/* Collapsible Technical Review Narrative for Auditing */}
      {evaluation.explanation && (
        <div>
          <button
            type="button"
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="text-xs font-semibold text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 cursor-pointer"
          >
            <span>{showTechnicalDetails ? 'Hide' : 'Show'} Technical Adjudication Narrative</span>
            {showTechnicalDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {showTechnicalDetails && (
            <div className="mt-2 p-3 rounded-lg bg-slate-100/70 border border-slate-200 text-xs text-slate-600 font-mono leading-relaxed">
              <span className="font-bold text-slate-700 block mb-1">Backend Narrative:</span>
              {evaluation.explanation}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
