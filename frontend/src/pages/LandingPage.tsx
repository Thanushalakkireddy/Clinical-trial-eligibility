import React, { useState, useEffect } from 'react';
import {
  Home,
  FileText,
  Users,
  FileCheck,
  History,
  BarChart3,
  BookOpen,
  Info,
  Stethoscope,
  ShieldCheck,
  ArrowRight,
  FolderPlus,
  UserPlus,
  UploadCloud,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
  Calendar,
  Clock,
  ExternalLink,
  ChevronRight,
  Copy,
  Check,
  Layers,
  Search,
} from 'lucide-react';
import { ArchitectureDiagram } from '../components/ArchitectureDiagram';
import { HealthStatus } from '../components/HealthStatus';
import { ProtocolUploader } from '../components/ProtocolUploader';
import { PatientProfileProcessor } from '../components/PatientProfileProcessor';
import { DecisionReviewerEvaluator } from '../components/DecisionReviewerEvaluator';
import { AssessmentHistoryPage } from '../components/AssessmentHistoryPage';
import { getTrials, getPatients } from '../services/api';
import type {
  FinalEvaluationResponse,
  ProtocolExtractionResponse,
  StructuredPatientProfile,
  FinalEligibilityDecision,
} from '../types';
import { formatPatientField } from '../utils/formatters';

export type WorkflowTab =
  | 'home'
  | 'protocol'
  | 'patient'
  | 'assessment'
  | 'history'
  | 'reports'
  | 'help'
  | 'about';

interface LandingPageProps {
  activeTab?: WorkflowTab;
  setActiveTab?: (tab: WorkflowTab) => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  activeTab: externalActiveTab,
  setActiveTab: externalSetActiveTab,
}) => {
  const [internalTab, setInternalTab] = useState<WorkflowTab>('home');
  const [activeTrialId, setActiveTrialId] = useState<string | null>(null);
  const [activePatientProfileId, setActivePatientProfileId] = useState<string | null>(null);
  const [patientEntryMode, setPatientEntryMode] = useState<'upload' | 'manual'>('upload');

  // Live records fetched from backend API
  const [trials, setTrials] = useState<ProtocolExtractionResponse[]>([]);
  const [patients, setPatients] = useState<StructuredPatientProfile[]>([]);
  const [loadingRecords, setLoadingRecords] = useState<boolean>(true);

  // Session assessments history (persisted in localStorage)
  const [assessmentHistory, setAssessmentHistory] = useState<FinalEvaluationResponse[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [copiedJson, setCopiedJson] = useState<boolean>(false);

  const currentTab = externalActiveTab || internalTab;
  const setTab = externalSetActiveTab || setInternalTab;

  // Load live data from API
  const refreshRecords = async () => {
    setLoadingRecords(true);
    try {
      const [trialsRes, patientsRes] = await Promise.allSettled([
        getTrials(),
        getPatients(),
      ]);

      if (trialsRes.status === 'fulfilled' && Array.isArray(trialsRes.value)) {
        setTrials(trialsRes.value);
      } else {
        setTrials([]);
      }

      if (patientsRes.status === 'fulfilled' && Array.isArray(patientsRes.value)) {
        setPatients(patientsRes.value);
      } else {
        setPatients([]);
      }
    } catch {
      setTrials([]);
      setPatients([]);
    } finally {
      setLoadingRecords(false);
    }
  };

  useEffect(() => {
    refreshRecords();

    // Load persisted session history if any
    try {
      const saved = localStorage.getItem('clinical_evaluations_history');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          setAssessmentHistory(parsed);
          if (parsed.length > 0) {
            setSelectedReportId(`${parsed[0].trial_id}_${parsed[0].patient_profile_id}_${parsed[0].evaluated_at}`);
          }
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  const handleEvaluationSaved = (result: FinalEvaluationResponse) => {
    setAssessmentHistory((prev) => {
      const uniqueId = `${result.trial_id}_${result.patient_profile_id}_${result.evaluated_at}`;
      const filtered = prev.filter(
        (item) => `${item.trial_id}_${item.patient_profile_id}_${item.evaluated_at}` !== uniqueId
      );
      const updated = [result, ...filtered].slice(0, 50);
      try {
        localStorage.setItem('clinical_evaluations_history', JSON.stringify(updated));
      } catch {
        // Storage quota exceeded or disabled
      }
      return updated;
    });
    setSelectedReportId(`${result.trial_id}_${result.patient_profile_id}_${result.evaluated_at}`);
  };

  const navItems: { id: WorkflowTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'protocol', label: 'Protocol Management', icon: FileText },
    { id: 'patient', label: 'Patient Records', icon: Users },
    { id: 'assessment', label: 'Eligibility Assessment', icon: FileCheck },
    { id: 'history', label: 'Assessment History', icon: History },
    { id: 'reports', label: 'Reports', icon: BarChart3 },
    { id: 'help', label: 'Help & Documentation', icon: BookOpen },
    { id: 'about', label: 'About', icon: Info },
  ];

  const getDecisionBadge = (decision: FinalEligibilityDecision | string) => {
    switch (decision) {
      case 'ELIGIBLE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Eligible
          </span>
        );
      case 'NOT_ELIGIBLE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            Not Eligible
          </span>
        );
      case 'MORE_INFORMATION_REQUIRED':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            <HelpCircle className="w-3.5 h-3.5 text-amber-600" />
            More Info Required
          </span>
        );
    }
  };

  const activeReport = assessmentHistory.find(
    (item) => `${item.trial_id}_${item.patient_profile_id}_${item.evaluated_at}` === selectedReportId
  ) || assessmentHistory[0] || null;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      {/* Primary Workflow Navigation Bar */}
      <nav aria-label="Workflow Navigation" className="bg-white border-b border-slate-200 sticky top-16 z-10 shadow-2xs">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-1 overflow-x-auto py-2 scrollbar-none">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  id={`nav-tab-${item.id}`}
                  onClick={() => setTab(item.id)}
                  className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                    isActive
                      ? 'bg-sky-900 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main View Area */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 mt-6">
        {/* =========================================================================
            TAB 1: HOME
           ========================================================================= */}
        {currentTab === 'home' && (
          <div className="space-y-8">
            {/* Clinical Welcome & Status */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-sky-50 border border-sky-200 text-sky-800 text-xs font-semibold mb-2">
                    <Stethoscope className="w-3.5 h-3.5 text-sky-600" />
                    <span>Clinical Research Decision Support</span>
                  </div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                    Clinical Trial Eligibility Assessment Platform
                  </h1>
                  <p className="mt-1 text-xs sm:text-sm text-slate-600 max-w-2xl leading-relaxed">
                    Evaluate patient clinical records against complex trial protocols using verified evidence citations,
                    standardized laboratory normalization, and deterministic consensus.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={refreshRecords}
                    disabled={loadingRecords}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors cursor-pointer"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingRecords ? 'animate-spin text-sky-600' : 'text-slate-500'}`} />
                    <span>Refresh Records</span>
                  </button>
                </div>
              </div>

              {/* Dynamic Metrics Row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100">
                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Available Protocols
                  </span>
                  <span className="text-2xl font-bold text-slate-900 mt-1 block">
                    {loadingRecords ? '...' : trials.length}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Patient Profiles
                  </span>
                  <span className="text-2xl font-bold text-slate-900 mt-1 block">
                    {loadingRecords ? '...' : patients.length}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Completed Assessments
                  </span>
                  <span className="text-2xl font-bold text-slate-900 mt-1 block">
                    {assessmentHistory.length}
                  </span>
                </div>

                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    System Health
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 mt-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    Operational
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Actions Grid */}
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-3">
                Core Clinical Workflows
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-5 rounded-xl border border-slate-200 bg-white shadow-2xs hover:shadow-sm transition-shadow flex flex-col justify-between">
                  <div>
                    <div className="w-9 h-9 rounded-lg bg-sky-50 text-sky-700 flex items-center justify-center mb-3">
                      <FileCheck className="w-5 h-5" />
                    </div>
                    <h3 className="text-sm font-bold text-slate-900">Assess Patient Eligibility</h3>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      Evaluate a patient against a clinical trial protocol using documented evidence and deterministic safety screening.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTab('assessment')}
                    className="mt-4 inline-flex items-center justify-between px-3 py-2 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <span>Run Assessment</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="p-5 rounded-xl border border-slate-200 bg-white shadow-2xs hover:shadow-sm transition-shadow flex flex-col justify-between">
                  <div>
                    <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center mb-3">
                      <FileText className="w-5 h-5" />
                    </div>
                    <h3 className="text-sm font-bold text-slate-900">Protocol Management</h3>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      Upload trial PDF protocols, extract structured inclusion and exclusion criteria with verified page citations.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTab('protocol')}
                    className="mt-4 inline-flex items-center justify-between px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <span>Upload Protocol</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="p-5 rounded-xl border border-slate-200 bg-white shadow-2xs hover:shadow-sm transition-shadow flex flex-col justify-between">
                  <div>
                    <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center mb-3">
                      <Users className="w-5 h-5" />
                    </div>
                    <h3 className="text-sm font-bold text-slate-900">Patient Records</h3>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      Create, normalize, and inspect structured patient health records, laboratory units, and medical histories.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTab('patient')}
                    className="mt-4 inline-flex items-center justify-between px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <span>Create Profile</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>

            {/* Recent Assessments Section */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                  Recent Assessments
                </h2>
                {assessmentHistory.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setTab('history')}
                    className="text-xs font-semibold text-sky-800 hover:text-sky-950 flex items-center gap-1 cursor-pointer"
                  >
                    <span>View All History</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {assessmentHistory.length === 0 ? (
                <div className="p-8 text-center bg-white border border-slate-200 rounded-xl space-y-3">
                  <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
                    <FileCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">No assessments yet.</p>
                    <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                      Run an eligibility assessment to see recent evaluations, decision records, and audit logs here.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTab('assessment')}
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <FileCheck className="w-3.5 h-3.5" />
                    <span>Assess Patient Eligibility</span>
                  </button>
                </div>
              ) : (
                <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100 overflow-hidden shadow-2xs">
                  {assessmentHistory.slice(0, 4).map((evalItem, idx) => (
                    <div
                      key={idx}
                      className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/70 transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          {getDecisionBadge(evalItem.final_decision)}
                          <span className="font-semibold text-xs text-slate-900">
                            {evalItem.trial_id}
                          </span>
                          <span className="text-slate-400">•</span>
                          <span className="text-xs text-slate-600 font-mono">
                            {evalItem.patient_profile_id}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 line-clamp-1 max-w-xl">
                          {evalItem.explanation}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-center">
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedReportId(`${evalItem.trial_id}_${evalItem.patient_profile_id}_${evalItem.evaluated_at}`);
                            setTab('reports');
                          }}
                          className="px-3 py-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 transition-colors cursor-pointer"
                        >
                          View Report
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setActiveTrialId(evalItem.trial_id);
                            setActivePatientProfileId(evalItem.patient_profile_id);
                            setTab('assessment');
                          }}
                          className="px-3 py-1.5 rounded-md bg-sky-900 hover:bg-sky-800 text-white text-xs font-medium transition-colors cursor-pointer"
                        >
                          Re-evaluate
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Available Records Split View */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Clinical Trials */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                    Clinical Trials ({trials.length})
                  </h2>
                  <button
                    type="button"
                    onClick={() => setTab('protocol')}
                    className="text-xs font-semibold text-sky-800 hover:text-sky-950 flex items-center gap-1 cursor-pointer"
                  >
                    <span>Manage Protocols</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {trials.length === 0 ? (
                  <div className="p-6 text-center bg-white border border-dashed border-slate-200 rounded-xl space-y-2">
                    <p className="text-xs text-slate-500">No clinical trials have been added yet.</p>
                    <button
                      type="button"
                      onClick={() => setTab('protocol')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-50 text-sky-800 hover:bg-sky-100 border border-sky-200 rounded-md text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <FolderPlus className="w-3.5 h-3.5" />
                      <span>Upload Trial Protocol</span>
                    </button>
                  </div>
                ) : (
                  <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100 overflow-hidden shadow-2xs max-h-64 overflow-y-auto">
                    {trials.map((t) => (
                      <div key={t.trial_id} className="p-3.5 flex items-center justify-between hover:bg-slate-50 text-xs">
                        <div>
                          <p className="font-semibold text-slate-900 line-clamp-1">
                            {t.trial_title || t.trial_id}
                          </p>
                          <p className="text-slate-500 font-mono text-[11px] mt-0.5">
                            {t.trial_id} {t.trial_identifier ? `• ${t.trial_identifier}` : ''}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setActiveTrialId(t.trial_id);
                            setTab('assessment');
                          }}
                          className="text-sky-800 hover:text-sky-950 font-semibold text-xs ml-3 shrink-0 cursor-pointer"
                        >
                          Select
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Patient Profiles */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                    Patient Records ({patients.length})
                  </h2>
                  <button
                    type="button"
                    onClick={() => setTab('patient')}
                    className="text-xs font-semibold text-sky-800 hover:text-sky-950 flex items-center gap-1 cursor-pointer"
                  >
                    <span>Manage Patients</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {patients.length === 0 ? (
                  <div className="p-6 text-center bg-white border border-dashed border-slate-200 rounded-xl space-y-3">
                    <p className="text-xs text-slate-500">No patient profiles have been created yet.</p>
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setPatientEntryMode('upload');
                          setTab('patient');
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 text-white hover:bg-sky-700 rounded-md text-xs font-semibold transition-colors cursor-pointer shadow-2xs"
                      >
                        <UploadCloud className="w-3.5 h-3.5" />
                        <span>Upload Patient Record</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setPatientEntryMode('manual');
                          setTab('patient');
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white text-slate-700 hover:bg-slate-50 border border-slate-300 rounded-md text-xs font-semibold transition-colors cursor-pointer"
                      >
                        <UserPlus className="w-3.5 h-3.5 text-slate-500" />
                        <span>Enter Patient Manually</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100 overflow-hidden shadow-2xs max-h-64 overflow-y-auto">
                    {patients.map((p) => (
                      <div key={p.patient_profile_id} className="p-3.5 flex items-center justify-between hover:bg-slate-50 text-xs">
                        <div>
                          <p className="font-semibold text-slate-900 font-mono">
                            {p.patient_profile_id}
                          </p>
                          <p className="text-slate-500 text-[11px] mt-0.5">
                            {p.demographics?.age ? `Age ${p.demographics.age}` : 'Age unk'}, {p.demographics?.sex || 'Sex unk'}{' '}
                            {p.conditions && p.conditions.length > 0
                              ? `• ${p.conditions.map((c) => c.normalized_name || c.name).slice(0, 1).join('')}`
                              : ''}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setActivePatientProfileId(p.patient_profile_id);
                            setTab('assessment');
                          }}
                          className="text-sky-800 hover:text-sky-950 font-semibold text-xs ml-3 shrink-0 cursor-pointer"
                        >
                          Select
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 2: PROTOCOL MANAGEMENT
           ========================================================================= */}
        {currentTab === 'protocol' && (
          <div className="space-y-6">
            <ProtocolUploader
              onTrialActive={(id) => {
                setActiveTrialId(id);
                refreshRecords();
              }}
            />
          </div>
        )}

        {/* =========================================================================
            TAB 3: PATIENT RECORDS
           ========================================================================= */}
        {currentTab === 'patient' && (
          <div className="space-y-6">
            <PatientProfileProcessor
              selectedProfileId={activePatientProfileId}
              initialMode={patientEntryMode}
              onProfileSaved={(profile) => {
                setActivePatientProfileId(profile.patient_profile_id);
                refreshRecords();
              }}
            />
          </div>
        )}

        {/* =========================================================================
            TAB 4: ELIGIBILITY ASSESSMENT
           ========================================================================= */}
        {currentTab === 'assessment' && (
          <div className="space-y-6">
            <DecisionReviewerEvaluator
              initialTrialId={activeTrialId}
              initialPatientProfileId={activePatientProfileId}
              onNavigateToProtocol={() => setTab('protocol')}
              onNavigateToPatient={() => setTab('patient')}
              onEvaluationSaved={handleEvaluationSaved}
            />
          </div>
        )}

        {/* =========================================================================
            TAB 5: ASSESSMENT HISTORY
           ========================================================================= */}
        {currentTab === 'history' && (
          <div className="space-y-6">
            <AssessmentHistoryPage onRunAssessment={() => setTab('assessment')} />
          </div>
        )}

        {/* =========================================================================
            TAB 6: REPORTS
           ========================================================================= */}
        {currentTab === 'reports' && (
          <div className="space-y-6">
            {assessmentHistory.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-xl p-12 text-center space-y-3 shadow-xs">
                <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
                  <BarChart3 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-900">No evaluation reports generated yet.</h3>
                  <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                    Complete an eligibility assessment to view compliance and audit reports with protocol provenance citations.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setTab('assessment')}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-sky-900 hover:bg-sky-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                >
                  <FileCheck className="w-4 h-4" />
                  <span>Run Eligibility Assessment</span>
                </button>
              </div>
            ) : activeReport ? (
              <div className="space-y-6">
                {/* Report Header and Selector */}
                <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-4">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                    <div>
                      <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200 mb-1">
                        <ShieldCheck className="w-3.5 h-3.5 text-sky-600" />
                        <span>Regulatory & Provenance Audit Report</span>
                      </div>
                      <h2 className="text-lg font-bold text-slate-900">
                        Protocol Eligibility Audit Summary
                      </h2>
                    </div>

                    <div className="flex items-center gap-2">
                      <select
                        aria-label="Select Evaluation Report"
                        value={selectedReportId || ''}
                        onChange={(e) => setSelectedReportId(e.target.value)}
                        className="text-xs border border-slate-300 rounded-lg px-3 py-1.5 bg-white text-slate-700 font-sans focus:ring-2 focus:ring-sky-500 focus:outline-hidden"
                      >
                        {assessmentHistory.map((h, i) => (
                          <option
                            key={i}
                            value={`${h.trial_id}_${h.patient_profile_id}_${h.evaluated_at}`}
                          >
                            {h.trial_id} / {h.patient_profile_id} ({h.final_decision})
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(activeReport, null, 2));
                          setCopiedJson(true);
                          setTimeout(() => setCopiedJson(false), 2000);
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 rounded-lg transition-colors cursor-pointer"
                      >
                        {copiedJson ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                            <span>Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5 text-slate-500" />
                            <span>Copy Audit JSON</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Executive Decision Banner */}
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                        Adjudicated Eligibility Outcome
                      </span>
                      <div className="mt-1 flex items-center gap-3">
                        {getDecisionBadge(activeReport.final_decision)}
                        <span className="text-xs text-slate-500">
                          Evaluated at {new Date(activeReport.evaluated_at).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-xs">
                      <div>
                        <span className="text-slate-500 block">Trial ID:</span>
                        <span className="font-mono font-bold text-slate-900">{activeReport.trial_id}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Patient Profile:</span>
                        <span className="font-mono font-bold text-slate-900">{activeReport.patient_profile_id}</span>
                      </div>
                    </div>
                  </div>

                  {/* Explanation Narrative */}
                  <div className="p-4 rounded-lg bg-sky-50/50 border border-sky-200/70 text-xs text-sky-950 leading-relaxed">
                    <p className="font-semibold text-sky-900 mb-1">Clinical Adjudication Rationale:</p>
                    <p>{activeReport.explanation}</p>
                  </div>
                </div>

                {/* Evidence & Decision Factors Matrix */}
                <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-6">
                  <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                    Protocol Citations & Decision Evidence Breakdown
                  </h3>

                  {/* Inclusion Criteria Provenance */}
                  {(() => {
                    const inclusionFactors = activeReport.decision_factors?.filter((f) => f.type === 'inclusion') || [];
                    if (inclusionFactors.length === 0) return null;
                    return (
                      <div className="space-y-3">
                        <h4 className="text-xs font-bold text-slate-800">
                          Inclusion Criteria Verification ({inclusionFactors.length})
                        </h4>
                        <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                          {inclusionFactors.map((inc, i) => (
                            <div key={i} className="p-3.5 bg-white text-xs space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="font-mono font-bold text-slate-800 text-[11px]">
                                  {inc.criterion_id || `INC-${i + 1}`}
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                    inc.status === 'MET' || inc.status === 'SATISFIED'
                                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                      : inc.status === 'UNMET' || inc.status === 'NOT_MET'
                                      ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                      : 'bg-amber-50 text-amber-700 border border-amber-200'
                                  }`}
                                >
                                  {inc.status}
                                </span>
                              </div>
                              <p className="text-slate-700 font-medium">{inc.criterion_text}</p>
                              <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 pt-1">
                                {inc.protocol_page && (
                                  <span className="px-2 py-0.5 bg-slate-100 rounded text-slate-700">
                                    Protocol Page {inc.protocol_page}
                                  </span>
                                )}
                                {inc.reason && (
                                  <span className="text-slate-600">
                                    Evidence: <em>{inc.reason}</em>
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Exclusion Criteria Provenance */}
                  {(() => {
                    const exclusionFactors = activeReport.decision_factors?.filter((f) => f.type === 'exclusion') || [];
                    if (exclusionFactors.length === 0) return null;
                    return (
                      <div className="space-y-3">
                        <h4 className="text-xs font-bold text-slate-800">
                          Exclusion Contraindications Screening ({exclusionFactors.length})
                        </h4>
                        <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                          {exclusionFactors.map((exc, i) => {
                            const isDisqualified =
                              exc.status === 'TRIGGERED' ||
                              exc.status === 'DISQUALIFIED' ||
                              exc.status === 'UNSATISFIED';
                            return (
                              <div key={i} className="p-3.5 bg-white text-xs space-y-1.5">
                                <div className="flex items-center justify-between">
                                  <span className="font-mono font-bold text-slate-800 text-[11px]">
                                    {exc.criterion_id || `EXC-${i + 1}`}
                                  </span>
                                  <span
                                    className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                      isDisqualified
                                        ? 'bg-rose-100 text-rose-800 border border-rose-300 font-bold'
                                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    }`}
                                  >
                                    {isDisqualified ? 'TRIGGERED DISQUALIFIER' : 'NOT TRIGGERED'}
                                  </span>
                                </div>
                                <p className="text-slate-700 font-medium">{exc.criterion_text}</p>
                                {exc.reason && (
                                  <p className="text-slate-600 text-[11px] bg-slate-50 p-2 rounded border border-slate-200">
                                    Finding: {exc.reason}
                                  </p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Missing Information Items */}
                  {activeReport.missing_information && activeReport.missing_information.length > 0 && (
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-amber-800">
                        Required Clinical Information Gaps ({activeReport.missing_information.length})
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {activeReport.missing_information.map((item, i) => (
                          <div
                            key={i}
                            className="p-2.5 rounded-lg bg-amber-50/60 border border-amber-200 text-xs flex items-start justify-between gap-2"
                          >
                            <div>
                              <span className="font-semibold text-slate-900 block">
                                {formatPatientField(item)}
                              </span>
                              <span className="font-mono text-[10px] text-slate-500">
                                {item}
                              </span>
                            </div>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-200 shrink-0">
                              Missing
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        )}

        {/* =========================================================================
            TAB 7: HELP & DOCUMENTATION
           ========================================================================= */}
        {currentTab === 'help' && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-6">
              <div className="pb-4 border-b border-slate-100">
                <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200 mb-1">
                  <BookOpen className="w-3.5 h-3.5 text-sky-600" />
                  <span>Clinical Documentation</span>
                </div>
                <h2 className="text-lg font-bold text-slate-900">
                  Eligibility Evaluation Methodology & System Guidelines
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Standard operating procedures, adjudication rules, and deterministic consensus criteria
                </p>
              </div>

              {/* Guide Sections */}
              <div className="space-y-6 text-xs text-slate-700 leading-relaxed">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 mb-2">
                    1. End-to-End Evaluation Workflow
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="font-bold text-slate-900 block mb-1">Protocol Ingestion</span>
                      Protocol PDF documents are segmented into clean inclusion and exclusion rules. Each criterion maintains exact page anchors for regulatory auditability.
                    </div>
                    <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="font-bold text-slate-900 block mb-1">Clinical Normalization</span>
                      Patient EHR records are normalized: laboratory values are converted to standard reference units, conditions mapped to clinical taxonomies, and medications tagged.
                    </div>
                    <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="font-bold text-slate-900 block mb-1">Deterministic Adjudication</span>
                      Autonomous multi-factor evaluation matches patient evidence against protocol prerequisites without diagnostic speculation.
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-100">
                  <h3 className="text-sm font-bold text-slate-900 mb-2">
                    2. Adjudication Decision Logic
                  </h3>
                  <ul className="space-y-2">
                    <li className="p-3 bg-emerald-50/50 rounded-lg border border-emerald-200">
                      <strong className="text-emerald-900">ELIGIBLE:</strong> Assigned only when ALL mandatory inclusion criteria are confirmed MET, ZERO exclusion criteria are triggered, no safety contraindications exist, and no critical information is missing.
                    </li>
                    <li className="p-3 bg-rose-50/50 rounded-lg border border-rose-200">
                      <strong className="text-rose-900">NOT ELIGIBLE:</strong> Assigned immediately if any exclusion criterion is triggered (e.g. renal failure, prohibited concurrent therapy, active infection) or any mandatory prerequisite is definitively UNMET.
                    </li>
                    <li className="p-3 bg-amber-50/50 rounded-lg border border-amber-200">
                      <strong className="text-amber-900">MORE INFORMATION REQUIRED:</strong> Assigned when essential laboratory values, histologic confirmations, or wash-out dates are missing from the patient health record, preventing safe adjudication.
                    </li>
                  </ul>
                </div>

                <div className="pt-4 border-t border-slate-100">
                  <h3 className="text-sm font-bold text-slate-900 mb-2">
                    3. Zero Diagnostic Inference Policy
                  </h3>
                  <p>
                    The system operates under a strict deterministic standard: it will never infer or guess an unstated diagnosis. If a patient record does not contain specific required documentation (e.g., genetic mutation status, organ function test within required days), the criterion is categorized as <strong>UNKNOWN</strong>, prompting human clinical follow-up.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 8: ABOUT
           ========================================================================= */}
        {currentTab === 'about' && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">About Clinical Trial Eligibility Platform</h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Production Version 1.0.0 • Clinical Decision Support System
                  </p>
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  Ready for Production Review
                </span>
              </div>

              <div className="text-xs text-slate-600 space-y-3 leading-relaxed">
                <p>
                  This system facilitates autonomous, evidence-grounded clinical trial candidate screening. By parsing protocol documents and standardizing structured patient health records, it provides clinical research coordinators and principal investigators with deterministic, transparent, and auditable matching decisions.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800 block">Traceable Page Citations</span>
                    Every criterion links directly to protocol page numbers and exact patient EHR lab records.
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800 block">Deterministic Safety Screening</span>
                    Comprehensive screening for organ dysfunction, contraindications, and therapy wash-out windows.
                  </div>
                </div>
              </div>
            </div>

            {/* Architecture Diagram (Moved here as authorized in Requirement 11) */}
            <ArchitectureDiagram />

            {/* Service Health & Diagnostics */}
            <HealthStatus />
          </div>
        )}

        {/* Regulatory Disclaimer */}
        <footer className="mt-12 pt-6 border-t border-slate-200 text-center">
          <p className="text-xs text-slate-500 max-w-xl mx-auto leading-relaxed">
            <span className="font-medium text-slate-700">Notice:</span> This software serves as an eligibility-support tool for clinical research teams. Final protocol eligibility determination and patient enrollment decisions must be confirmed by qualified medical professionals.
          </p>
        </footer>
      </main>
    </div>
  );
};
