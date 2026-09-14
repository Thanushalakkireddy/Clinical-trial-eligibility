import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  CheckCircle2,
  XCircle,
  FileText,
  User,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { FinalEvaluationResponse, DecisionFactor } from '../types';
import { formatPatientField } from '../utils/fieldMapping';

interface VerdictOutcomePresentationProps {
  evaluation: FinalEvaluationResponse;
}

export const VerdictOutcomePresentation: React.FC<VerdictOutcomePresentationProps> = ({
  evaluation,
}) => {
  const { final_decision, decision_factors = [] } = evaluation;

  // Separate factors
  const failedInclusions = decision_factors.filter(
    (f) => f.type === 'inclusion' && f.status === 'unsatisfied'
  );
  const triggeredExclusions = decision_factors.filter(
    (f) => f.type === 'exclusion' && (f.status === 'triggered' || f.status === 'unsatisfied')
  );
  const silentHazards = decision_factors.filter(
    (f) => f.type === 'silent_exclusion' || f.type === 'contradiction'
  );
  const satisfiedInclusions = decision_factors.filter(
    (f) => f.type === 'inclusion' && f.status === 'satisfied'
  );

  const isProtocolValidationRequired =
    final_decision === 'MORE_INFORMATION_REQUIRED' &&
    decision_factors.some((f) => f.criterion_id === 'PROTOCOL-VALIDATION-REQUIRED');

  // 0. Protocol Validation Required Presentation
  if (isProtocolValidationRequired) {
    return (
      <div className="p-6 rounded-xl border border-amber-300 bg-amber-50/70 shadow-xs space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center text-amber-700">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-base font-bold text-amber-950">
              Protocol Document Validation Alert
            </h4>
            <p className="text-xs text-amber-800">
              The uploaded document does not contain verifiable clinical trial eligibility criteria. In accordance with clinical trial protocol safety principles, an assessment requires verified protocol criteria.
            </p>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-amber-200 shadow-2xs space-y-3 text-xs">
          <div className="flex items-start gap-2.5">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold text-slate-800">Why did this occur?</p>
              <p className="text-slate-600 leading-relaxed">
                {evaluation.explanation ||
                  'The uploaded file does not contain identifiable inclusion or exclusion criteria (0 criteria evaluated). Non-protocol documents—such as resumes, curriculum vitae, invoices, or general text—cannot be used as a source of truth for clinical trial eligibility.'}
              </p>
            </div>
          </div>
          <div className="pt-2 border-t border-amber-100 flex items-center justify-between text-[11px] text-amber-800">
            <span>Required: Authentic Clinical Trial Protocol PDF</span>
            <span className="font-mono font-semibold">Criteria Count: 0</span>
          </div>
        </div>
      </div>
    );
  }

  // 1. ELIGIBLE Presentation
  if (final_decision === 'ELIGIBLE') {
    return (
      <div className="p-6 rounded-xl border border-emerald-200 bg-emerald-50/50 shadow-xs space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center text-emerald-700">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-base font-bold text-emerald-950">
              Protocol Compliance & Eligibility Confirmation
            </h4>
            <p className="text-xs text-emerald-800">
              All mandatory protocol requirements are documented and satisfied without exceptions.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="p-3.5 rounded-lg bg-white border border-emerald-200 shadow-2xs space-y-1">
            <div className="flex items-center gap-1.5 font-bold text-emerald-900">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Inclusion Criteria</span>
            </div>
            <p className="text-slate-600">
              {evaluation.inclusion_summary.satisfied} of {evaluation.inclusion_summary.total} criteria satisfied with zero unverified requirements.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-white border border-emerald-200 shadow-2xs space-y-1">
            <div className="flex items-center gap-1.5 font-bold text-emerald-900">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Exclusion Criteria</span>
            </div>
            <p className="text-slate-600">
              Zero exclusion criteria triggered across {evaluation.exclusion_summary.total} evaluated protocol parameters.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-white border border-emerald-200 shadow-2xs space-y-1">
            <div className="flex items-center gap-1.5 font-bold text-emerald-900">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Safety & Consistency</span>
            </div>
            <p className="text-slate-600">
              Zero contradictions and zero latent silent exclusions identified in patient profile.
            </p>
          </div>
        </div>

        {/* Satisfied Criteria Highlights */}
        {satisfiedInclusions.length > 0 && (
          <div className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-900 block">
              Satisfied Protocol Evidence Summary ({satisfiedInclusions.length})
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              {satisfiedInclusions.slice(0, 4).map((f, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-white/80 border border-emerald-100 flex items-start justify-between gap-2"
                >
                  <div>
                    <span className="font-mono font-bold text-emerald-800 mr-1.5">
                      {f.criterion_id}:
                    </span>
                    <span className="text-slate-700">{f.criterion_text}</span>
                  </div>
                  {f.protocol_page && (
                    <span className="font-mono text-[10px] text-slate-400 shrink-0">
                      p.{f.protocol_page}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // 2. NOT_ELIGIBLE Presentation
  if (final_decision === 'NOT_ELIGIBLE') {
    return (
      <div className="p-6 rounded-xl border border-rose-200 bg-rose-50/50 shadow-xs space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center text-rose-700">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-base font-bold text-rose-950">
              Protocol Disqualification Details
            </h4>
            <p className="text-xs text-rose-800">
              The patient does not qualify due to specific unmet inclusion requirements or triggered exclusion criteria.
            </p>
          </div>
        </div>

        {/* Failed Inclusions */}
        {failedInclusions.length > 0 && (
          <div className="space-y-2.5">
            <div className="text-xs font-bold uppercase tracking-wider text-rose-900 flex items-center gap-1.5">
              <XCircle className="w-4 h-4 text-rose-600" />
              <span>Failed Inclusion Criteria ({failedInclusions.length})</span>
            </div>

            <div className="space-y-2">
              {failedInclusions.map((factor, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-white border border-rose-200 shadow-2xs space-y-2 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="font-mono font-bold text-rose-800 text-xs mr-2">
                        {factor.criterion_id}
                      </span>
                      <span className="font-semibold text-slate-900">
                        {factor.criterion_text}
                      </span>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-100 text-rose-800 border border-rose-200 shrink-0">
                      Unsatisfied
                    </span>
                  </div>

                  {/* Patient Evidence */}
                  <div className="p-2.5 rounded-lg bg-rose-50/60 border border-rose-100 text-rose-950 space-y-1">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold">
                      <User className="w-3.5 h-3.5 text-rose-700" />
                      <span>Documented Patient Evidence:</span>
                    </div>
                    <p className="text-slate-800">
                      {factor.reason || 'Clinical value does not meet protocol threshold.'}
                    </p>
                    {factor.patient_value !== undefined && factor.patient_value !== null && (
                      <span className="font-mono text-[11px] text-slate-600 block">
                        Recorded value: {String(factor.patient_value)}
                      </span>
                    )}
                  </div>

                  {/* Protocol citation */}
                  <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono pt-1">
                    <span className="flex items-center gap-1">
                      <FileText className="w-3 h-3 text-slate-400" />
                      Protocol Source: {factor.protocol_page ? `Page ${factor.protocol_page}` : 'Protocol Spec'}
                    </span>
                    {factor.patient_field && (
                      <span>Field: {formatPatientField(factor.patient_field)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Triggered Exclusions */}
        {triggeredExclusions.length > 0 && (
          <div className="space-y-2.5">
            <div className="text-xs font-bold uppercase tracking-wider text-rose-900 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
              <span>Triggered Disqualifying Exclusions ({triggeredExclusions.length})</span>
            </div>

            <div className="space-y-2">
              {triggeredExclusions.map((factor, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-white border border-rose-200 shadow-2xs space-y-2 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="font-mono font-bold text-rose-800 text-xs mr-2">
                        {factor.criterion_id}
                      </span>
                      <span className="font-semibold text-slate-900">
                        {factor.criterion_text}
                      </span>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-100 text-rose-800 border border-rose-200 shrink-0">
                      Triggered
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-rose-50/60 border border-rose-100 text-rose-950 space-y-1">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold">
                      <User className="w-3.5 h-3.5 text-rose-700" />
                      <span>Disqualification Clinical Rationale:</span>
                    </div>
                    <p className="text-slate-800">{factor.reason}</p>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono pt-1">
                    <span className="flex items-center gap-1">
                      <FileText className="w-3 h-3 text-slate-400" />
                      Protocol Source: {factor.protocol_page ? `Page ${factor.protocol_page}` : 'Protocol Spec'}
                    </span>
                    {factor.patient_field && (
                      <span>Field: {formatPatientField(factor.patient_field)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Latent Silent Hazards if any */}
        {silentHazards.length > 0 && (
          <div className="space-y-2.5">
            <div className="text-xs font-bold uppercase tracking-wider text-rose-900 flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-rose-600" />
              <span>Critical Contradictions & Latent Silent Hazards ({silentHazards.length})</span>
            </div>

            <div className="space-y-2">
              {silentHazards.map((factor, idx) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl bg-white border border-rose-200 text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-rose-900">
                      {factor.criterion_id || 'Safety Conflict'}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800">
                      Hazard Detected
                    </span>
                  </div>
                  <p className="text-slate-700">{factor.reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // 3. MORE_INFORMATION_REQUIRED presentation
  // In addition to MissingInformationSection, this shows which criteria cannot be evaluated!
  const unknownFactors = decision_factors.filter((f) => f.status === 'unknown');

  return (
    <div className="p-6 rounded-xl border border-amber-200 bg-amber-50/50 shadow-xs space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center text-amber-700">
          <HelpCircle className="w-6 h-6" />
        </div>
        <div>
          <h4 className="text-base font-bold text-amber-950">
            Unresolved Protocol Criteria
          </h4>
          <p className="text-xs text-amber-800">
            These protocol criteria cannot be evaluated until missing documentation is supplied.
          </p>
        </div>
      </div>

      {unknownFactors.length > 0 ? (
        <div className="space-y-2.5">
          <span className="text-xs font-bold uppercase tracking-wider text-amber-900 block">
            Criteria Awaiting Patient Data ({unknownFactors.length})
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            {unknownFactors.map((factor, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-xl bg-white border border-amber-200 shadow-2xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="font-mono font-bold text-amber-900 mr-1.5">
                      {factor.criterion_id || 'UNKNOWN'}:
                    </span>
                    <span className="font-medium text-slate-900">
                      {factor.criterion_text || factor.reason}
                    </span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-300 shrink-0">
                    Unknown
                  </span>
                </div>

                <p className="text-xs text-slate-600 bg-amber-50/50 p-2 rounded-lg border border-amber-100">
                  {factor.reason}
                </p>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono pt-1">
                  <span>
                    Protocol Source: {factor.protocol_page ? `Page ${factor.protocol_page}` : 'Spec'}
                  </span>
                  {factor.patient_field && (
                    <span className="text-amber-800 font-semibold">
                      Needs: {formatPatientField(factor.patient_field)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="p-4 rounded-lg bg-white border border-amber-200 text-xs text-slate-700 flex items-center gap-2">
          <Info className="w-4 h-4 text-amber-600 shrink-0" />
          <span>Please provide the missing information listed in the section above to complete the evaluation.</span>
        </div>
      )}
    </div>
  );
};
