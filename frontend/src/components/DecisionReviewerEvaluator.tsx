import React, { useState, useEffect, useRef } from 'react';
import {
  FileCheck,
  RefreshCw,
  Stethoscope,
  Info,
  FolderPlus,
  UserPlus,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import { runWorkflowEvaluation, getTrials, getPatients } from '../services/api';
import {
  FinalEvaluationResponse,
  ProtocolExtractionResponse,
  StructuredPatientProfile,
} from '../types';
import {
  mapToFastAPIPatientProfile,
  mapWorkflowStateToFinalEvaluation,
} from '../utils/eligibilityAdapter';
import { AssessmentRecordStatus } from './AssessmentRecordStatus';
import { AuthoritativeVerdictCard } from './AuthoritativeVerdictCard';
import { AssessmentSummarySection } from './AssessmentSummarySection';
import { MissingInformationSection } from './MissingInformationSection';
import { AssessmentOverviewCards } from './AssessmentOverviewCards';
import { VerdictOutcomePresentation } from './VerdictOutcomePresentation';
import { TraceableEvidenceSection } from './TraceableEvidenceSection';

interface DecisionReviewerEvaluatorProps {
  initialTrialId?: string | null;
  initialPatientProfileId?: string | null;
  onNavigateToProtocol?: () => void;
  onNavigateToPatient?: () => void;
  onEvaluationSaved?: (result: FinalEvaluationResponse) => void;
}

export const DecisionReviewerEvaluator: React.FC<DecisionReviewerEvaluatorProps> = ({
  initialTrialId = '',
  initialPatientProfileId = '',
  onNavigateToProtocol,
  onNavigateToPatient,
  onEvaluationSaved,
}) => {
  const [trialId, setTrialId] = useState<string>(initialTrialId || '');
  const [patientProfileId, setPatientProfileId] = useState<string>(
    initialPatientProfileId || ''
  );
  const [trials, setTrials] = useState<ProtocolExtractionResponse[]>([]);
  const [patients, setPatients] = useState<StructuredPatientProfile[]>([]);
  const [loadingRecords, setLoadingRecords] = useState<boolean>(true);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<FinalEvaluationResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const resultsRef = useRef<HTMLDivElement | null>(null);
  const missingSectionRef = useRef<HTMLDivElement | null>(null);
  const evidenceSectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (initialTrialId) setTrialId(initialTrialId);
  }, [initialTrialId]);

  useEffect(() => {
    if (initialPatientProfileId) setPatientProfileId(initialPatientProfileId);
  }, [initialPatientProfileId]);

  // Fetch available trials and patients from API on mount
  useEffect(() => {
    loadAvailableData();
  }, []);

  const loadAvailableData = async () => {
    setLoadingRecords(true);
    try {
      const [trialsRes, patientsRes] = await Promise.allSettled([
        getTrials(),
        getPatients(),
      ]);

      if (trialsRes.status === 'fulfilled' && Array.isArray(trialsRes.value)) {
        setTrials(trialsRes.value);
      }
      if (patientsRes.status === 'fulfilled' && Array.isArray(patientsRes.value)) {
        setPatients(patientsRes.value);
      }
    } catch {
      // Backend may be starting up
    } finally {
      setLoadingRecords(false);
    }
  };

  const handleEvaluate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!trialId.trim()) {
      setError('Please select a Clinical Trial.');
      return;
    }
    if (!patientProfileId.trim()) {
      setError('Please select a Patient Profile.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const patient = patients.find((p) => p.patient_profile_id === patientProfileId.trim());
      if (!patient) {
        setError('Selected patient profile was not found in the data store.');
        setEvaluation(null);
        return;
      }

      const workflow = await runWorkflowEvaluation(
        trialId.trim(),
        mapToFastAPIPatientProfile(patient)
      );

      const res = mapWorkflowStateToFinalEvaluation(workflow);
      setEvaluation(res);
      onEvaluationSaved?.(res);

      // Smooth scroll to results
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
    } catch (err: any) {
      setError(err.message || 'Failed to evaluate final eligibility review.');
      setEvaluation(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyJson = () => {
    if (!evaluation) return;
    navigator.clipboard.writeText(JSON.stringify(evaluation, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSelectOverviewCard = (category: 'inclusion' | 'exclusion' | 'safety' | 'missing') => {
    if (category === 'missing' && missingSectionRef.current) {
      missingSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (evidenceSectionRef.current) {
      evidenceSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
      {/* Header Banner */}
      <div className="border-b border-slate-200 p-6 sm:p-8 bg-slate-50/70">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-sky-50 border border-sky-200 text-sky-800 text-xs font-medium mb-2">
              <Stethoscope className="w-3.5 h-3.5 text-sky-600" />
              <span>Eligibility Assessment</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              Assess Patient Eligibility
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-600 max-w-2xl leading-relaxed">
              Evaluate a patient against a clinical trial protocol using documented evidence.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded-md bg-white border border-slate-200 text-slate-600 font-medium shadow-2xs">
              Evidence-Traceable
            </span>
            <span className="px-2.5 py-1 rounded-md bg-white border border-slate-200 text-slate-600 font-medium shadow-2xs">
              Zero Diagnosis Inference
            </span>
            <span className="px-2.5 py-1 rounded-md bg-white border border-slate-200 text-slate-600 font-medium shadow-2xs">
              Deterministic Consensus
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 sm:p-8 space-y-6">
        {/* Trial and Patient Selection Form */}
        <form onSubmit={handleEvaluate} className="space-y-4">
          <p className="text-xs text-slate-600 font-medium">
            Select a clinical trial and patient profile to assess eligibility.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Select Clinical Trial */}
            <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-2xs">
              <label
                htmlFor="eval-trial-id"
                className="block text-xs font-bold text-slate-800 uppercase tracking-wider mb-1.5"
              >
                Select Clinical Trial
              </label>

              {loadingRecords ? (
                <div className="flex items-center gap-2 py-2 text-xs text-slate-500">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Loading clinical trials...</span>
                </div>
              ) : trials.length === 0 ? (
                <div className="p-3 rounded-lg bg-slate-50 border border-dashed border-slate-200 text-center space-y-2">
                  <p className="text-xs text-slate-500">No clinical trials available yet.</p>
                  {onNavigateToProtocol && (
                    <button
                      type="button"
                      onClick={onNavigateToProtocol}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-sky-700 bg-sky-50 hover:bg-sky-100 rounded border border-sky-200 transition-colors cursor-pointer"
                    >
                      <FolderPlus className="w-3.5 h-3.5" />
                      Upload Trial Protocol
                    </button>
                  )}
                </div>
              ) : (
                <div className="relative">
                  <select
                    id="eval-trial-id"
                    value={trialId}
                    onChange={(e) => setTrialId(e.target.value)}
                    className="w-full pl-3 pr-8 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-hidden focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 transition-all font-sans"
                  >
                    <option value="">Search and select a clinical trial...</option>
                    {trials.map((t) => (
                      <option key={t.trial_id} value={t.trial_id}>
                        {t.trial_title && t.trial_title !== (t.trial_identifier || t.trial_id)
                          ? `${t.trial_identifier || t.trial_id} — ${t.trial_title}`
                          : (t.trial_identifier || t.trial_id)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Select Patient */}
            <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-2xs">
              <label
                htmlFor="eval-patient-id"
                className="block text-xs font-bold text-slate-800 uppercase tracking-wider mb-1.5"
              >
                Select Patient
              </label>

              {loadingRecords ? (
                <div className="flex items-center gap-2 py-2 text-xs text-slate-500">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Loading patient profiles...</span>
                </div>
              ) : patients.length === 0 ? (
                <div className="p-3 rounded-lg bg-slate-50 border border-dashed border-slate-200 text-center space-y-2">
                  <p className="text-xs text-slate-500">No patient profiles available yet.</p>
                  {onNavigateToPatient && (
                    <button
                      type="button"
                      onClick={onNavigateToPatient}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-sky-700 bg-sky-50 hover:bg-sky-100 rounded border border-sky-200 transition-colors cursor-pointer"
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                      Create Patient Profile
                    </button>
                  )}
                </div>
              ) : (
                <div className="relative">
                  <select
                    id="eval-patient-id"
                    value={patientProfileId}
                    onChange={(e) => setPatientProfileId(e.target.value)}
                    className="w-full pl-3 pr-8 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-hidden focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 transition-all font-sans"
                  >
                    <option value="">Search and select a patient...</option>
                    {patients.map((p) => (
                      <option key={p.patient_profile_id} value={p.patient_profile_id}>
                        {p.patient_profile_id} — {p.demographics?.age ? `Age ${p.demographics.age}` : 'Age unk'},{' '}
                        {p.demographics?.sex || 'Sex unk'}{' '}
                        {p.conditions && p.conditions.length > 0
                          ? `(${p.conditions.map((c) => c.normalized_name || c.name).slice(0, 2).join(', ')})`
                          : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>

          {/* Clinical Info Panel */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-start gap-2.5">
            <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              The system will evaluate inclusion criteria, exclusion criteria, safety consistency, and missing information using evidence from the trial protocol and patient record.
            </p>
          </div>

          {/* Action Row */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="text-xs text-slate-500">
              {trialId && patientProfileId ? (
                <span className="text-emerald-700 font-medium flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Ready for evaluation
                </span>
              ) : (
                <span>Select both a clinical trial and a patient profile to proceed.</span>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !trialId.trim() || !patientProfileId.trim()}
              className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-sky-900 hover:bg-sky-800 active:bg-sky-950 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Evaluating Clinical Protocol...</span>
                </>
              ) : (
                <>
                  <FileCheck className="w-4 h-4" />
                  <span>Run Eligibility Assessment</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Error Notice */}
        {error && (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">Adjudication Error</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* =========================================================================
            RESULTS VIEW: AUTHORITATIVE VERDICT & MISSING INFORMATION
           ========================================================================= */}
        {evaluation && (
          <div ref={resultsRef} className="space-y-6 pt-6 border-t border-slate-200">
            {/* 0. ASSESSMENT RECORD STATUS (persistence indicator) */}
            <AssessmentRecordStatus assessmentId={evaluation.assessment_id} />

            {/* 1. AUTHORITATIVE VERDICT (Section 1) */}
            <AuthoritativeVerdictCard
              evaluation={evaluation}
              onCopyJson={handleCopyJson}
              copied={copied}
            />

            {/* 2. CLEAR SUMMARY (Section 2) */}
            <AssessmentSummarySection evaluation={evaluation} />

            {/* 3. MISSING INFORMATION SECTION (Section 3, 5, 7) */}
            {evaluation.missing_information && evaluation.missing_information.length > 0 && (
              <div ref={missingSectionRef}>
                <MissingInformationSection
                  missingFields={evaluation.missing_information}
                  decisionFactors={evaluation.decision_factors}
                  protocolEvidence={evaluation.protocol_evidence}
                  trialId={evaluation.trial_id}
                  onNavigateToPatient={onNavigateToPatient}
                />
              </div>
            )}

            {/* 4. ASSESSMENT OVERVIEW CARDS (Section 6) */}
            <AssessmentOverviewCards
              evaluation={evaluation}
              onSelectCard={handleSelectOverviewCard}
            />

            {/* 5. VERDICT-SPECIFIC PRESENTATION (Section 8) */}
            <VerdictOutcomePresentation evaluation={evaluation} />

            {/* 6. TRACEABLE EVIDENCE & CITATIONS (Section 9) */}
            <div ref={evidenceSectionRef}>
              <TraceableEvidenceSection evaluation={evaluation} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
