import React from 'react';
import {
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  ShieldAlert,
  FileCheck2,
  ChevronRight,
} from 'lucide-react';
import { FinalEvaluationResponse } from '../types';

interface AssessmentOverviewCardsProps {
  evaluation: FinalEvaluationResponse;
  onSelectCard?: (category: 'inclusion' | 'exclusion' | 'safety' | 'missing') => void;
}

export const AssessmentOverviewCards: React.FC<AssessmentOverviewCardsProps> = ({
  evaluation,
  onSelectCard,
}) => {
  const missingCount = evaluation.missing_information?.length || 0;
  const isMissingInfo = evaluation.final_decision === 'MORE_INFORMATION_REQUIRED';
  const isEligible = evaluation.final_decision === 'ELIGIBLE';
  const isNotEligible = evaluation.final_decision === 'NOT_ELIGIBLE';

  // 1. Inclusion Card State
  const getInclusionState = () => {
    if (isMissingInfo) {
      return {
        badge: 'UNKNOWN',
        badgeColor: 'bg-amber-100 text-amber-800 border-amber-300',
        icon: <HelpCircle className="w-5 h-5 text-amber-600" />,
        desc: 'Cannot fully evaluate inclusion criteria because required patient information is missing.',
        countText: `${evaluation.inclusion_summary?.satisfied || 0} satisfied, ${evaluation.inclusion_summary?.unknown || 0} unknown`,
      };
    }
    if (isEligible) {
      return {
        badge: 'SATISFIED',
        badgeColor: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        icon: <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
        desc: 'All required protocol inclusion criteria are documented and satisfied.',
        countText: `${evaluation.inclusion_summary?.satisfied || 0} of ${evaluation.inclusion_summary?.total || 0} satisfied`,
      };
    }
    // Not Eligible
    const hasUnsatisfied = (evaluation.inclusion_summary?.unsatisfied || 0) > 0;
    return {
      badge: hasUnsatisfied ? 'UNSATISFIED' : 'EVALUATED',
      badgeColor: hasUnsatisfied
        ? 'bg-rose-100 text-rose-800 border-rose-300'
        : 'bg-slate-100 text-slate-800 border-slate-300',
      icon: hasUnsatisfied ? <AlertCircle className="w-5 h-5 text-rose-600" /> : <FileCheck2 className="w-5 h-5 text-slate-600" />,
      desc: hasUnsatisfied
        ? `${evaluation.inclusion_summary?.unsatisfied} inclusion criterion/criteria failed.`
        : 'Inclusion criteria evaluated; disqualified by protocol criteria.',
      countText: `${evaluation.inclusion_summary?.satisfied || 0} satisfied, ${evaluation.inclusion_summary?.unsatisfied || 0} failed`,
    };
  };

  // 2. Exclusion Card State
  const getExclusionState = () => {
    if (isMissingInfo) {
      const hasUnknown = (evaluation.exclusion_summary?.unknown || 0) > 0;
      return {
        badge: hasUnknown ? 'UNKNOWN' : 'CLEAR',
        badgeColor: hasUnknown
          ? 'bg-amber-100 text-amber-800 border-amber-300'
          : 'bg-emerald-100 text-emerald-800 border-emerald-300',
        icon: hasUnknown ? <HelpCircle className="w-5 h-5 text-amber-600" /> : <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
        desc: hasUnknown
          ? 'Cannot fully evaluate exclusion criteria because required patient information is missing.'
          : 'No disqualifying exclusion criteria triggered so far.',
        countText: `${evaluation.exclusion_summary?.not_triggered || 0} clear, ${evaluation.exclusion_summary?.unknown || 0} unknown`,
      };
    }
    if (isEligible) {
      return {
        badge: 'CLEAR',
        badgeColor: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        icon: <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
        desc: 'No protocol exclusion criteria were triggered.',
        countText: `${evaluation.exclusion_summary?.not_triggered || 0} clear of ${evaluation.exclusion_summary?.total || 0}`,
      };
    }
    // Not Eligible
    const hasTriggered = (evaluation.exclusion_summary?.triggered || 0) > 0;
    return {
      badge: hasTriggered ? 'TRIGGERED' : 'CLEAR',
      badgeColor: hasTriggered
        ? 'bg-rose-100 text-rose-800 border-rose-300'
        : 'bg-emerald-100 text-emerald-800 border-emerald-300',
      icon: hasTriggered ? <AlertCircle className="w-5 h-5 text-rose-600" /> : <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
      desc: hasTriggered
        ? `${evaluation.exclusion_summary?.triggered} disqualifying exclusion criterion/criteria triggered.`
        : 'No standard exclusion criteria triggered.',
      countText: `${evaluation.exclusion_summary?.triggered || 0} triggered`,
    };
  };

  // 3. Safety & Consistency Card State
  const getSafetyState = () => {
    const hasSilentExclusions = (evaluation.summary?.silent_exclusions_count || 0) > 0;
    const hasContradictions = (evaluation.summary?.contradictions_count || 0) > 0;

    if (hasSilentExclusions || hasContradictions) {
      return {
        badge: 'ALERT',
        badgeColor: 'bg-rose-100 text-rose-800 border-rose-300',
        icon: <ShieldAlert className="w-5 h-5 text-rose-600" />,
        desc: `${evaluation.summary.silent_exclusions_count} latent hazard(s) or contradiction(s) detected.`,
        countText: 'Action Required',
      };
    }

    if (isMissingInfo) {
      return {
        badge: 'REVIEWED',
        badgeColor: 'bg-sky-100 text-sky-800 border-sky-300',
        icon: <ShieldCheck className="w-5 h-5 text-sky-600" />,
        desc: 'No critical contradiction detected. Assessment remains limited by missing information.',
        countText: '0 Contradictions',
      };
    }

    return {
      badge: 'VERIFIED',
      badgeColor: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      icon: <ShieldCheck className="w-5 h-5 text-emerald-600" />,
      desc: 'No contradictions or latent silent exclusions detected across records.',
      countText: 'Safety Verified',
    };
  };

  // 4. Missing Information Card State
  const getMissingState = () => {
    if (missingCount > 0) {
      return {
        badge: 'INCOMPLETE',
        badgeColor: 'bg-amber-100 text-amber-800 border-amber-300',
        icon: <HelpCircle className="w-5 h-5 text-amber-600" />,
        desc: `${missingCount} required patient data element${missingCount === 1 ? '' : 's'} must be provided.`,
        countText: `${missingCount} Item${missingCount === 1 ? '' : 's'}`,
      };
    }
    return {
      badge: 'COMPLETE',
      badgeColor: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      icon: <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
      desc: 'All required patient information is documented in the record.',
      countText: '0 Missing',
    };
  };

  const inc = getInclusionState();
  const exc = getExclusionState();
  const safe = getSafetyState();
  const miss = getMissingState();

  const cards = [
    {
      category: 'inclusion' as const,
      title: 'Inclusion Criteria',
      ...inc,
    },
    {
      category: 'exclusion' as const,
      title: 'Exclusion Criteria',
      ...exc,
    },
    {
      category: 'safety' as const,
      title: 'Safety & Consistency',
      ...safe,
    },
    {
      category: 'missing' as const,
      title: 'Missing Information',
      ...miss,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Assessment Overview
        </h4>
        <span className="text-[11px] text-slate-400">
          4 Clinical Pillars Evaluated
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div
            key={c.category}
            className="p-5 rounded-xl border border-slate-200 bg-white shadow-2xs hover:shadow-xs transition-all flex flex-col justify-between space-y-3 group"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 group-hover:bg-slate-100 transition-colors">
                  {c.icon}
                </div>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase border ${c.badgeColor}`}
                >
                  {c.badge}
                </span>
              </div>

              <div>
                <h5 className="text-sm font-bold text-slate-900">{c.title}</h5>
                <span className="text-xs font-semibold text-slate-600 block mt-0.5">
                  {c.countText}
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed min-h-10">
                {c.desc}
              </p>
            </div>

            {onSelectCard && (
              <button
                type="button"
                onClick={() => onSelectCard(c.category)}
                className="w-full pt-2 border-t border-slate-100 inline-flex items-center justify-between text-xs font-semibold text-slate-700 hover:text-sky-800 transition-colors cursor-pointer group-hover:text-sky-900"
              >
                <span>View Details</span>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
