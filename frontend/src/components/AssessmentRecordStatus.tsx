import React from 'react';
import { CheckCircle2, Info } from 'lucide-react';

interface AssessmentRecordStatusProps {
  assessmentId?: string | null;
}

/**
 * Clean, non-technical indicator shown alongside an assessment result.
 * When the backend persisted the run (assessment_id present) it displays a
 * confirmable reference number; when persistence is unavailable (null) it shows
 * a neutral notice instead of a technical error.
 */
export const AssessmentRecordStatus: React.FC<AssessmentRecordStatusProps> = ({
  assessmentId,
}) => {
  if (assessmentId) {
    return (
      <div className="flex items-start gap-2.5 p-3 rounded-lg bg-emerald-50/70 border border-emerald-200 text-xs text-emerald-900">
        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <p className="font-semibold">Assessment recorded successfully</p>
          <p className="text-emerald-800">
            This evaluation was saved to the audit history. Reference ID:{' '}
            <span className="font-mono font-semibold break-all">{assessmentId}</span>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600">
      <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
      <p className="leading-relaxed">
        Evaluation complete. The assessment history service is not configured, so this run was
        not saved to persistent audit history.
      </p>
    </div>
  );
};