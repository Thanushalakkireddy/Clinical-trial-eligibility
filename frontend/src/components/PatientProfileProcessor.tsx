import React, { useState, useEffect } from 'react';
import {
  User,
  Activity,
  Pill,
  FlaskConical,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  RefreshCw,
  Plus,
  Trash2,
  FileText,
  ShieldCheck,
  Sparkles,
  Info,
  Code,
  Layers,
  UploadCloud,
  UserPlus,
} from 'lucide-react';
import { PatientDocumentUploader } from './PatientDocumentUploader';

interface LabValueItem {
  id: string;
  name: string;
  value: string;
  unit: string;
  reference_range?: string;
  source?: string;
}

interface MedicationItem {
  id: string;
  name: string;
  dose?: string;
  unit?: string;
  frequency?: string;
  route?: string;
}

interface AllergyItem {
  id: string;
  allergen: string;
  reaction?: string;
  severity?: string;
}

interface NormalizedLab {
  name: string;
  normalized_name: string;
  value: number;
  unit: string;
  original_unit: string;
  reference_range?: string | null;
  normalization_status: string;
  source: string;
}

interface NormalizedCondition {
  name: string;
  normalized_name: string;
  icd10_code?: string | null;
  status: string;
  diagnosed_date?: string | null;
  source: string;
}

interface NormalizedMed {
  name: string;
  normalized_name: string;
  dose?: string | null;
  unit?: string | null;
  frequency?: string | null;
  route?: string | null;
  is_current: boolean;
  source: string;
}

interface MissingInfoItem {
  field: string;
  status: string;
  category: string;
  description: string;
}

interface StructuredProfile {
  patient_profile_id: string;
  profile_status: string;
  created_at?: string;
  demographics: {
    age?: number | null;
    sex?: string | null;
    height?: number | null;
    weight?: number | null;
    bmi?: number | null;
  };
  conditions: NormalizedCondition[];
  medical_history: NormalizedCondition[];
  medications: NormalizedMed[];
  lab_values: NormalizedLab[];
  allergies: Array<{
    allergen: string;
    normalized_allergen: string;
    reaction?: string | null;
    severity?: string | null;
    source: string;
  }>;
  vital_signs?: {
    systolic_bp?: number | null;
    diastolic_bp?: number | null;
    heart_rate?: number | null;
    spo2_percent?: number | null;
    source: string;
  } | null;
  missing_information: MissingInfoItem[];
  clinical_notes_raw?: string | null;
}

export interface PatientProfileProcessorProps {
  onProfileSaved?: (profile: StructuredProfile) => void;
  selectedProfileId?: string | null;
  initialMode?: 'upload' | 'manual';
}

export const PatientProfileProcessor: React.FC<PatientProfileProcessorProps> = ({
  onProfileSaved,
  selectedProfileId,
  initialMode,
}) => {
  const [mode, setMode] = useState<'upload' | 'manual'>(initialMode || 'upload');
  const [savedSuccessMsg, setSavedSuccessMsg] = useState<string | null>(null);

  // Form Inputs (Empty initial state - API-first)
  const [age, setAge] = useState<string>('');
  const [sex, setSex] = useState<string>('');
  const [height, setHeight] = useState<string>('');
  const [weight, setWeight] = useState<string>('');
  const [conditionsText, setConditionsText] = useState<string>('');
  const [historyText, setHistoryText] = useState<string>('');
  const [notes, setNotes] = useState<string>('');

  const [medications, setMedications] = useState<MedicationItem[]>([]);
  const [labValues, setLabValues] = useState<LabValueItem[]>([]);
  const [allergies, setAllergies] = useState<AllergyItem[]>([]);

  // Processing State
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentProfile, setCurrentProfile] = useState<StructuredProfile | null>(null);
  const [savedProfiles, setSavedProfiles] = useState<StructuredProfile[]>([]);
  const [activeTab, setActiveTab] = useState<'structured' | 'missing' | 'json'>('structured');
  const [copied, setCopied] = useState<boolean>(false);

  // Sync props
  useEffect(() => {
    if (initialMode) setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    if (selectedProfileId && savedProfiles.length > 0) {
      const found = savedProfiles.find((p) => p.patient_profile_id === selectedProfileId);
      if (found) setCurrentProfile(found);
    }
  }, [selectedProfileId, savedProfiles]);

  // Load existing profiles on mount
  useEffect(() => {
    fetchProfiles();
  }, []);

  const fetchProfiles = async () => {
    try {
      const res = await fetch('/api/v1/patients');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setSavedProfiles(data);
          // Do NOT automatically select data[0] - respect API-first empty selection
        }
      }
    } catch {
      // Backend may still be initializing
    }
  };

  const clearForm = () => {
    setAge('');
    setSex('');
    setHeight('');
    setWeight('');
    setConditionsText('');
    setHistoryText('');
    setNotes('');
    setMedications([]);
    setLabValues([]);
    setAllergies([]);
    setError(null);
  };

  // Add/Remove dynamic rows
  const addMedication = () => {
    setMedications([
      ...medications,
      { id: Date.now().toString(), name: '', dose: '', unit: 'mg', frequency: '', route: 'oral' },
    ]);
  };

  const removeMedication = (id: string) => {
    setMedications(medications.filter((m) => m.id !== id));
  };

  const updateMedication = (id: string, field: keyof MedicationItem, val: string) => {
    setMedications(medications.map((m) => (m.id === id ? { ...m, [field]: val } : m)));
  };

  const addLabValue = () => {
    setLabValues([
      ...labValues,
      { id: Date.now().toString(), name: '', value: '', unit: '', reference_range: '' },
    ]);
  };

  const removeLabValue = (id: string) => {
    setLabValues(labValues.filter((l) => l.id !== id));
  };

  const updateLabValue = (id: string, field: keyof LabValueItem, val: string) => {
    setLabValues(labValues.map((l) => (l.id === id ? { ...l, [field]: val } : l)));
  };

  // Submit Handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProcessing(true);
    setError(null);

    try {
      // Parse conditions and history lists
      const conditionsList = conditionsText
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const historyList = historyText
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      // Validate & clean lab values
      const parsedLabs = labValues
        .filter((l) => l.name.trim() && l.value.trim() && l.unit.trim())
        .map((l) => {
          const num = parseFloat(l.value.trim());
          if (isNaN(num)) {
            throw new Error(`Lab value for "${l.name}" must be a valid number.`);
          }
          return {
            name: l.name.trim(),
            value: num,
            unit: l.unit.trim(),
            reference_range: l.reference_range?.trim() || null,
            source: 'patient_input',
          };
        });

      // Format medications
      const parsedMeds = medications
        .filter((m) => m.name.trim())
        .map((m) => ({
          name: m.name.trim(),
          dose: m.dose?.trim() || null,
          unit: m.unit?.trim() || null,
          frequency: m.frequency?.trim() || null,
          route: m.route?.trim() || null,
          is_current: true,
          source: 'patient_input',
        }));

      // Format allergies
      const parsedAllergies = allergies
        .filter((a) => a.allergen.trim())
        .map((a) => ({
          allergen: a.allergen.trim(),
          reaction: a.reaction?.trim() || null,
          severity: a.severity?.trim() || null,
          source: 'patient_input',
        }));

      const payload = {
        age: age.trim() ? parseInt(age.trim(), 10) : null,
        sex: sex.trim() || null,
        height: height.trim() ? parseFloat(height.trim()) : null,
        weight: weight.trim() ? parseFloat(weight.trim()) : null,
        conditions: conditionsList,
        medical_history: historyList,
        medications: parsedMeds,
        lab_values: parsedLabs,
        allergies: parsedAllergies,
        clinical_notes_raw: notes.trim() || null,
        other_attributes: {},
      };

      const response = await fetch('/api/v1/patients/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned HTTP ${response.status}`);
      }

      const createdProfile: StructuredProfile = await response.json();
      setCurrentProfile(createdProfile);
      setSavedProfiles((prev) => [
        createdProfile,
        ...prev.filter((p) => p.patient_profile_id !== createdProfile.patient_profile_id),
      ]);
      setActiveTab('structured');
      setSavedSuccessMsg(`Patient profile '${createdProfile.patient_profile_id}' saved successfully.`);
      if (onProfileSaved) {
        onProfileSaved(createdProfile);
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred processing the patient profile.');
    } finally {
      setIsProcessing(false);
    }
  };

  const copyJson = () => {
    if (currentProfile) {
      navigator.clipboard.writeText(JSON.stringify(currentProfile, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Estimated BMI calculation for display
  const numHeight = parseFloat(height);
  const numWeight = parseFloat(weight);
  const liveBmi =
    numHeight > 0 && numWeight > 0 ? (numWeight / ((numHeight / 100) * (numHeight / 100))).toFixed(1) : null;

  const renderStructuredProfileCard = () => {
    if (!currentProfile) {
      return (
        <div className="border border-dashed border-slate-300 rounded-xl p-8 text-center bg-slate-50/50 flex flex-col items-center justify-center min-h-[400px]">
          <div className="w-12 h-12 rounded-full bg-sky-100 text-sky-600 flex items-center justify-center mb-3">
            <User className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-800">No Patient Profile Selected</h3>
          <p className="mt-1 text-xs text-slate-500 max-w-sm">
            Select an existing patient profile from the records above, or complete and submit the clinical
            entry form on the left to normalize and register a patient profile.
          </p>
        </div>
      );
    }

    return (
      <div className="border border-slate-200 rounded-xl bg-white shadow-xs overflow-hidden">
        {/* Profile Header Status */}
        <div className="bg-slate-900 text-white px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold text-xs tracking-tight">
              Structured Profile: <span className="font-mono text-sky-300">{currentProfile.patient_profile_id}</span>
            </span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-700 font-medium">
            Status: {currentProfile.profile_status}
          </span>
        </div>

        {/* View Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600 px-4 pt-2 gap-4">
          <button
            type="button"
            onClick={() => setActiveTab('structured')}
            className={`pb-2 border-b-2 transition flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'structured'
                ? 'border-sky-600 text-sky-800 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Normalized View</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('missing')}
            className={`pb-2 border-b-2 transition flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'missing'
                ? 'border-amber-600 text-amber-800 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>Missing Information ({currentProfile.missing_information.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('json')}
            className={`pb-2 border-b-2 transition flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'json'
                ? 'border-sky-600 text-sky-800 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            <Code className="w-3.5 h-3.5" />
            <span>Audit JSON</span>
          </button>
        </div>

        <div className="p-5 max-h-[720px] overflow-y-auto space-y-5">
          {activeTab === 'structured' && (
            <>
              {/* Demographics Card */}
              <div className="border border-slate-200 rounded-lg p-3.5 bg-slate-50">
                <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-sky-600" />
                  <span>Demographics &amp; Biometrics</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <span className="text-slate-400 block text-[10px]">Age</span>
                    <span className="font-semibold text-slate-900 font-mono">
                      {currentProfile.demographics.age !== null ? `${currentProfile.demographics.age} years` : 'Unknown'}
                    </span>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <span className="text-slate-400 block text-[10px]">Sex</span>
                    <span className="font-semibold text-slate-900 capitalize">
                      {currentProfile.demographics.sex || 'Unknown'}
                    </span>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <span className="text-slate-400 block text-[10px]">Height / Weight</span>
                    <span className="font-semibold text-slate-900 font-mono">
                      {currentProfile.demographics.height || '?'} cm / {currentProfile.demographics.weight || '?'} kg
                    </span>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <span className="text-slate-400 block text-[10px]">BMI (Calculated)</span>
                    <span className="font-semibold text-sky-700 font-mono">
                      {currentProfile.demographics.bmi !== null
                        ? `${currentProfile.demographics.bmi} kg/m²`
                        : 'Not calculable'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Normalized Conditions & History */}
              <div>
                <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-sky-600" />
                  <span>Conditions &amp; Medical History</span>
                </div>
                {currentProfile.conditions.length === 0 && currentProfile.medical_history.length === 0 ? (
                  <div className="p-3 text-xs text-slate-400 bg-slate-50 rounded border border-slate-200 italic">
                    No conditions documented.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {currentProfile.conditions.map((c, i) => (
                      <div
                        key={i}
                        className="p-2.5 bg-white border border-slate-200 rounded-lg flex items-center justify-between text-xs"
                      >
                        <div>
                          <div className="font-semibold text-slate-900">{c.name}</div>
                          <div className="text-[11px] text-sky-700 font-mono">
                            canonical: {c.normalized_name}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium capitalize">
                            {c.status}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">[{c.source}]</span>
                        </div>
                      </div>
                    ))}
                    {currentProfile.medical_history.map((h, i) => (
                      <div
                        key={`h-${i}`}
                        className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between text-xs"
                      >
                        <div>
                          <div className="font-medium text-slate-700">{h.name}</div>
                          <div className="text-[11px] text-slate-500 font-mono">
                            canonical: {h.normalized_name}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 border border-slate-300 font-medium">
                            historic
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">[{h.source}]</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Normalized Laboratory Tests */}
              <div>
                <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <FlaskConical className="w-3.5 h-3.5 text-sky-600" />
                  <span>Standardized Laboratory Values ({currentProfile.lab_values.length})</span>
                </div>
                {currentProfile.lab_values.length === 0 ? (
                  <div className="p-3 text-xs text-slate-400 bg-slate-50 rounded border border-slate-200 italic">
                    No laboratory tests supplied.
                  </div>
                ) : (
                  <div className="border border-slate-200 rounded-lg overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-100 text-slate-600 border-b border-slate-200 text-[11px]">
                        <tr>
                          <th className="p-2.5 font-semibold">Test Name</th>
                          <th className="p-2.5 font-semibold">Canonical ID</th>
                          <th className="p-2.5 font-semibold">Value &amp; Unit</th>
                          <th className="p-2.5 font-semibold">Status</th>
                          <th className="p-2.5 font-semibold">Source</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {currentProfile.lab_values.map((lab, i) => (
                          <tr key={i} className="hover:bg-slate-50">
                            <td className="p-2.5 font-semibold text-slate-900">{lab.name}</td>
                            <td className="p-2.5 font-mono text-sky-700">{lab.normalized_name}</td>
                            <td className="p-2.5">
                              <span className="font-mono font-bold text-slate-900">{lab.value}</span>{' '}
                              <span className="text-slate-600">{lab.unit}</span>
                              {lab.unit !== lab.original_unit && (
                                <span className="block text-[10px] text-slate-400 italic">
                                  from "{lab.original_unit}"
                                </span>
                              )}
                            </td>
                            <td className="p-2.5">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                                  lab.normalization_status === 'normalized'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : 'bg-amber-50 text-amber-700 border border-amber-200'
                                }`}
                              >
                                {lab.normalization_status}
                              </span>
                            </td>
                            <td className="p-2.5 text-slate-400 font-mono text-[10px]">{lab.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Normalized Medications */}
              <div>
                <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Pill className="w-3.5 h-3.5 text-sky-600" />
                  <span>Medications ({currentProfile.medications.length})</span>
                </div>
                {currentProfile.medications.length === 0 ? (
                  <div className="p-3 text-xs text-slate-400 bg-slate-50 rounded border border-slate-200 italic">
                    No medications recorded.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {currentProfile.medications.map((m, i) => (
                      <div key={i} className="p-2.5 border border-slate-200 rounded-lg bg-white text-xs">
                        <div className="font-semibold text-slate-900">{m.name}</div>
                        <div className="text-[11px] text-sky-700 font-mono">
                          canonical: {m.normalized_name}
                        </div>
                        <div className="mt-1 text-[11px] text-slate-600 flex flex-wrap gap-x-2">
                          <span>
                            Dose: {m.dose || '?'} {m.unit || ''}
                          </span>
                          {m.frequency && <span>• {m.frequency}</span>}
                          {m.route && <span>• {m.route}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'missing' && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs">
                <div className="font-semibold flex items-center gap-1.5 text-amber-800 mb-1">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span>Explicit Missing Information Audit</span>
                </div>
                <p className="text-amber-700 leading-relaxed text-[11px]">
                  The Patient Profile Agent never converts missing fields to "false" or assumes "no disease".
                  All unsupplied clinical domains are marked as <span className="font-mono font-bold">unknown</span>{' '}
                  for safe subsequent evaluation during trial eligibility matching.
                </p>
              </div>

              <div className="space-y-2">
                {currentProfile.missing_information.map((item, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start justify-between gap-3 text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-800 font-mono">{item.field}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-600 uppercase font-bold tracking-wider">
                          {item.category}
                        </span>
                      </div>
                      <p className="mt-1 text-slate-600 text-[11px]">{item.description}</p>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[11px] bg-amber-100 text-amber-800 font-mono font-semibold shrink-0">
                      status: {item.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'json' && (
            <div className="relative">
              <button
                type="button"
                onClick={copyJson}
                className="absolute top-2 right-2 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs flex items-center gap-1 transition cursor-pointer"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy JSON'}</span>
              </button>
              <pre className="p-4 rounded-lg bg-slate-950 text-slate-100 font-mono text-[11px] overflow-x-auto leading-relaxed max-h-[580px]">
                {JSON.stringify(currentProfile, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <section className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header Banner */}
      <div className="border-b border-slate-200 p-6 bg-slate-50/70">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-sky-50 border border-sky-200 text-sky-800 text-xs font-semibold mb-2">
              <Sparkles className="w-3.5 h-3.5 text-sky-600" />
              <span>Patient Data Normalization &amp; Profile Extraction</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              Patient Clinical Profiles
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-600 max-w-2xl">
              Create patient profiles via clinical PDF/JSON document upload or manual entry.
              Preserves strict source provenance and documented attributes with zero diagnostic inference.
            </p>
          </div>

          <div className="flex flex-col items-start sm:items-end gap-1.5 shrink-0">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Strict Provenance (Zero Inference)</span>
            </div>
            <span className="text-[11px] text-slate-500">Ready for protocol eligibility evaluation</span>
          </div>
        </div>
      </div>

      {/* Prominent Two-Option Action Bar */}
      <div className="bg-slate-50 border-b border-slate-200 px-6 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setMode('upload');
              setSavedSuccessMsg(null);
            }}
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              mode === 'upload'
                ? 'bg-sky-800 text-white shadow-xs'
                : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-300'
            }`}
          >
            <UploadCloud className="w-4 h-4" />
            <span>Upload Patient Record</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('manual');
              setSavedSuccessMsg(null);
            }}
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              mode === 'manual'
                ? 'bg-sky-800 text-white shadow-xs'
                : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-300'
            }`}
          >
            <UserPlus className="w-4 h-4" />
            <span>Enter Patient Manually</span>
          </button>
        </div>

        {savedProfiles.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold text-slate-700">Existing Profiles ({savedProfiles.length}):</span>
            <select
              value={currentProfile?.patient_profile_id || ''}
              onChange={(e) => {
                const found = savedProfiles.find((p) => p.patient_profile_id === e.target.value);
                setCurrentProfile(found || null);
                setSavedSuccessMsg(null);
              }}
              className="text-xs py-1.5 px-3 rounded-md border border-slate-300 bg-white text-slate-700 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 font-mono"
            >
              <option value="">Select a patient profile to view...</option>
              {savedProfiles.map((p) => (
                <option key={p.patient_profile_id} value={p.patient_profile_id}>
                  {p.patient_profile_id} — {p.demographics?.age ? `${p.demographics.age}yo` : 'Age unk'}, {p.demographics?.sex || 'unspecified'}
                </option>
              ))}
            </select>
          </div>
        )}

        {mode === 'manual' && (
          <button
            type="button"
            onClick={clearForm}
            className="px-2.5 py-1 text-xs font-medium rounded text-slate-600 hover:text-slate-900 border border-slate-200 hover:bg-slate-100 bg-white transition cursor-pointer"
          >
            Clear Form
          </button>
        )}
      </div>

      {/* Empty State Banner (if no profiles exist) */}
      {savedProfiles.length === 0 && (
        <div className="mx-6 mt-6 p-4 rounded-xl bg-sky-50/70 border border-sky-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs">
          <div>
            <h4 className="font-bold text-sky-950 text-sm">No patient profiles have been created yet.</h4>
            <p className="text-slate-600 mt-0.5">
              Choose an option below to create your first patient profile for clinical trial eligibility screening.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setMode('upload')}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                mode === 'upload'
                  ? 'bg-sky-800 text-white shadow-xs'
                  : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-300'
              }`}
            >
              <UploadCloud className="w-3.5 h-3.5" />
              <span>Upload Patient Record</span>
            </button>
            <button
              type="button"
              onClick={() => setMode('manual')}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                mode === 'manual'
                  ? 'bg-sky-800 text-white shadow-xs'
                  : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-300'
              }`}
            >
              <UserPlus className="w-3.5 h-3.5 text-sky-700" />
              <span>Enter Patient Manually</span>
            </button>
          </div>
        </div>
      )}

      {/* Success alert */}
      {savedSuccessMsg && (
        <div className="mx-6 mt-6 p-4 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">{savedSuccessMsg}</span>
          </div>
          <button
            type="button"
            onClick={() => setSavedSuccessMsg(null)}
            className="text-emerald-700 hover:text-emerald-900 font-bold ml-4"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Mode View */}
      {mode === 'upload' ? (
        <div className="p-6 space-y-6">
          <PatientDocumentUploader
            onProfileSaved={(newProf) => {
              setSavedProfiles((prev) => [
                newProf,
                ...prev.filter((p) => p.patient_profile_id !== newProf.patient_profile_id),
              ]);
              setCurrentProfile(newProf);
              setActiveTab('structured');
              setSavedSuccessMsg(`Patient profile '${newProf.patient_profile_id}' saved successfully.`);
              if (onProfileSaved) {
                onProfileSaved(newProf);
              }
            }}
            onSwitchToManual={() => setMode('manual')}
          />

          {currentProfile && (
            <div className="border-t border-slate-200 pt-6 mt-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <h3 className="text-sm font-bold text-slate-900">
                    Active Patient Profile: <span className="font-mono text-sky-800">{currentProfile.patient_profile_id}</span>
                  </h3>
                </div>
                {currentProfile.metadata?.source && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 font-medium">
                    Source: {currentProfile.metadata.source}
                  </span>
                )}
              </div>
              <div className="max-w-4xl">
                {renderStructuredProfileCard()}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Manual Mode: Grid with Input Form Left, Output Right */
        <div className="p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Input Form (6 cols on lg) */}
          <div className="lg:col-span-6 space-y-6">
            <form onSubmit={handleSubmit} className="space-y-5">
            {/* Demographics Block */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
                <User className="w-4 h-4 text-sky-600" />
                <span>Demographics &amp; Biometrics</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Age (years)</label>
                  <input
                    type="number"
                    min="0"
                    max="130"
                    value={age}
                    onChange={(e) => setAge(e.target.value)}
                    placeholder="e.g. 69"
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Biological Sex</label>
                  <select
                    value={sex}
                    onChange={(e) => setSex(e.target.value)}
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="other">Other</option>
                    <option value="">Unspecified</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Height (cm)</label>
                  <input
                    type="number"
                    min="1"
                    max="300"
                    value={height}
                    onChange={(e) => setHeight(e.target.value)}
                    placeholder="e.g. 175"
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Weight (kg)</label>
                  <input
                    type="number"
                    min="1"
                    max="500"
                    step="0.1"
                    value={weight}
                    onChange={(e) => setWeight(e.target.value)}
                    placeholder="e.g. 82.5"
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              </div>

              {liveBmi && (
                <div className="mt-2.5 flex items-center gap-2 text-[11px] text-slate-600">
                  <span className="font-semibold text-slate-700">Calculated BMI:</span>
                  <span className="px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-mono font-bold">
                    {liveBmi} kg/m²
                  </span>
                  <span className="text-slate-400">• Deterministic formula weight / (height/100)²</span>
                </div>
              )}
            </div>

            {/* Conditions & History Block */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50 space-y-3">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
                <Activity className="w-4 h-4 text-sky-600" />
                <span>Active Conditions &amp; Medical History</span>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Active Diagnoses / Conditions (comma separated)
                </label>
                <input
                  type="text"
                  value={conditionsText}
                  onChange={(e) => setConditionsText(e.target.value)}
                  placeholder="e.g. Type 2 Diabetes, Hypertension, CKD"
                  className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
                <p className="mt-1 text-[11px] text-slate-500">
                  Standardized canonical names are mapped (e.g. "T2D" → "type 2 diabetes").
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Past Medical History (comma separated)
                </label>
                <input
                  type="text"
                  value={historyText}
                  onChange={(e) => setHistoryText(e.target.value)}
                  placeholder="e.g. Cholecystectomy (2018), Prior Fracture"
                  className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>
            </div>

            {/* Medications Block */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200">
                <div className="flex items-center gap-2 text-slate-800 font-semibold text-xs uppercase tracking-wider">
                  <Pill className="w-4 h-4 text-sky-600" />
                  <span>Current Medications ({medications.length})</span>
                </div>
                <button
                  type="button"
                  onClick={addMedication}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-700 hover:text-sky-900 transition"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Drug</span>
                </button>
              </div>

              {medications.length === 0 ? (
                <div className="text-center py-3 text-xs text-slate-400 italic">No medications added.</div>
              ) : (
                <div className="space-y-2">
                  {medications.map((m) => (
                    <div key={m.id} className="grid grid-cols-12 gap-2 items-center bg-white p-2 rounded border border-slate-200 text-xs">
                      <div className="col-span-4">
                        <input
                          type="text"
                          placeholder="Drug Name (e.g. Metformin)"
                          value={m.name}
                          onChange={(e) => updateMedication(m.id, 'name', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-2">
                        <input
                          type="text"
                          placeholder="Dose"
                          value={m.dose || ''}
                          onChange={(e) => updateMedication(m.id, 'dose', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-2">
                        <input
                          type="text"
                          placeholder="Unit"
                          value={m.unit || ''}
                          onChange={(e) => updateMedication(m.id, 'unit', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-3">
                        <input
                          type="text"
                          placeholder="Freq / Route"
                          value={m.frequency || ''}
                          onChange={(e) => updateMedication(m.id, 'frequency', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-1 text-right">
                        <button
                          type="button"
                          onClick={() => removeMedication(m.id)}
                          className="text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Laboratory Values Block */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200">
                <div className="flex items-center gap-2 text-slate-800 font-semibold text-xs uppercase tracking-wider">
                  <FlaskConical className="w-4 h-4 text-sky-600" />
                  <span>Laboratory Test Values ({labValues.length})</span>
                </div>
                <button
                  type="button"
                  onClick={addLabValue}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-700 hover:text-sky-900 transition"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Lab</span>
                </button>
              </div>

              {labValues.length === 0 ? (
                <div className="text-center py-3 text-xs text-slate-400 italic">No lab values added.</div>
              ) : (
                <div className="space-y-2">
                  {labValues.map((l) => (
                    <div key={l.id} className="grid grid-cols-12 gap-2 items-center bg-white p-2 rounded border border-slate-200 text-xs">
                      <div className="col-span-4">
                        <input
                          type="text"
                          placeholder="Test (e.g. eGFR, Platelets)"
                          value={l.name}
                          onChange={(e) => updateLabValue(l.id, 'name', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-2">
                        <input
                          type="number"
                          step="any"
                          placeholder="Value"
                          value={l.value}
                          onChange={(e) => updateLabValue(l.id, 'value', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500 font-mono"
                        />
                      </div>
                      <div className="col-span-2">
                        <input
                          type="text"
                          placeholder="Unit"
                          value={l.unit}
                          onChange={(e) => updateLabValue(l.id, 'unit', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-3">
                        <input
                          type="text"
                          placeholder="Ref Range (optional)"
                          value={l.reference_range || ''}
                          onChange={(e) => updateLabValue(l.id, 'reference_range', e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                        />
                      </div>
                      <div className="col-span-1 text-right">
                        <button
                          type="button"
                          onClick={() => removeLabValue(l.id)}
                          className="text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Unstructured Clinical Notes Block */}
            <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
              <div className="flex items-center gap-2 pb-2 mb-2 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
                <FileText className="w-4 h-4 text-sky-600" />
                <span>Clinical Notes Narrative (Optional)</span>
              </div>
              <textarea
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Paste physician progress notes, encounter summaries, or lab reports..."
                className="w-full text-xs px-2.5 py-2 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500 font-sans"
              />
            </div>

            {/* Error Display */}
            {error && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
                <div>
                  <span className="font-semibold">Validation Error:</span> {error}
                </div>
              </div>
            )}

            {/* Submit Action */}
            <button
              type="submit"
              disabled={isProcessing}
              className="w-full py-2.5 px-4 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:bg-sky-300 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-sm transition"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Validating &amp; Normalizing via Agent...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Process &amp; Normalize Profile</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Column: Normalized Output (6 cols on lg) */}
        <div className="lg:col-span-6 space-y-4">
          {renderStructuredProfileCard()}
        </div>
      </div>
    )}
  </section>
);
};
