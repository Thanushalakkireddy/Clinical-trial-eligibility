import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  AlertTriangle,
  CheckCircle2,
  ShieldCheck,
  RotateCcw,
  Save,
  X,
  FileCode,
  User,
  Activity,
  Pill,
  FlaskConical,
  HelpCircle,
  Clock,
  Sparkles,
  ChevronRight,
} from 'lucide-react';
import { extractPatientDocument, createPatientProfile, PatientExtractionResponse } from '../services/api';
import type { StructuredPatientProfile } from '../types';

interface PatientDocumentUploaderProps {
  onProfileSaved: (profile: StructuredPatientProfile) => void;
  onCancel?: () => void;
  onSwitchToManual?: () => void;
}

export const PatientDocumentUploader: React.FC<PatientDocumentUploaderProps> = ({
  onProfileSaved,
  onCancel,
  onSwitchToManual,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [extractedData, setExtractedData] = useState<PatientExtractionResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndProcessFile = async (file: File) => {
    setError(null);

    // Validate file extension
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (ext !== '.pdf' && ext !== '.json') {
      setError('Please upload a PDF or JSON patient record.');
      return;
    }

    // Validate file size (30MB max)
    const maxBytes = 30 * 1024 * 1024;
    if (file.size > maxBytes) {
      setError('File size exceeds the 30MB limit. Please upload a smaller patient record file.');
      return;
    }

    setIsExtracting(true);
    try {
      const result = await extractPatientDocument(file);
      setExtractedData(result);
    } catch (err: any) {
      setError(
        err.message ||
          'Could not extract patient information from this document. Please verify that the document contains readable patient information or enter the profile manually.'
      );
    } finally {
      setIsExtracting(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndProcessFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      validateAndProcessFile(e.target.files[0]);
    }
  };

  const handleSave = async () => {
    if (!extractedData) return;
    setIsSaving(true);
    setError(null);
    try {
      const saved = await createPatientProfile(extractedData.profile);
      onProfileSaved(saved);
    } catch (err: any) {
      setError(err.message || 'Failed to save patient profile. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelReview = () => {
    setExtractedData(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (onCancel) {
      onCancel();
    }
  };

  // =========================================================================
  // VIEW 1: REVIEW EXTRACTED PATIENT INFORMATION (BEFORE SAVING)
  // =========================================================================
  if (extractedData) {
    const { profile, extractedFields, sourceDocument, sourceType } = extractedData;
    const demographics = profile.demographics || {};
    const conditions = profile.conditions || [];
    const labs = profile.lab_values || [];
    const meds = profile.medications || [];
    const allergies = profile.allergies || [];
    const missing = profile.missing_information || [];
    const ecogScore = profile.clinical_status?.ecog_performance_status ?? profile.metadata?.ecog_score;
    const activeSeriousInfection = profile.clinical_status?.active_serious_infection ?? profile.metadata?.active_serious_infection;
    const uncontrolledCardiacDisease = profile.clinical_status?.uncontrolled_cardiac_disease ?? profile.metadata?.uncontrolled_cardiac_disease;
    const recentTherapy = profile.treatment_history?.recent_systemic_anticancer_therapy ?? profile.metadata?.recent_systemic_anticancer_therapy;
    const severeHypersensitivity =
      profile.treatment_history?.severe_hypersensitivity_to_investigational_therapy ??
      profile.metadata?.severe_hypersensitivity_to_investigational_therapy ??
      profile.treatment_history?.investigational_therapy_hypersensitivity ??
      profile.metadata?.investigational_therapy_hypersensitivity;
    const vitalSigns = profile.vital_signs;

    return (
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden animate-in fade-in duration-200">
        {/* Review Banner */}
        <div className="border-b border-slate-200 p-6 bg-slate-50/80">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-sky-50 border border-sky-200 text-sky-800 text-xs font-semibold mb-2">
                <Sparkles className="w-3.5 h-3.5 text-sky-600" />
                <span>Verification Stage</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
                Review Extracted Patient Information
              </h2>
              <p className="mt-1 text-xs sm:text-sm text-slate-600 max-w-2xl">
                Please verify the extracted clinical information prior to saving. No clinical values have been invented or assumed.
              </p>
            </div>

            <div className="flex flex-col items-start sm:items-end gap-1.5 shrink-0">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>{sourceType}</span>
              </div>
              <span className="text-[11px] font-mono text-slate-500 max-w-xs truncate">
                File: {sourceDocument}
              </span>
            </div>
          </div>
        </div>

        {/* Error Alert if saving fails */}
        {error && (
          <div className="mx-6 mt-6 p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <strong className="font-semibold block">Saving Error:</strong>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Content Sections */}
        <div className="p-6 space-y-6">
          {/* Section 1: Patient Information */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-sky-600" />
                <span>Patient Information</span>
              </div>
              <span className="text-[11px] font-normal text-slate-500 lowercase">
                {extractedFields.includes('patient_id') ? 'id from document' : 'auto-generated id'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Patient ID</span>
                <span className="text-sm font-bold font-mono text-slate-900 mt-0.5 block truncate">
                  {profile.patient_profile_id}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Age</span>
                <span className="text-sm font-semibold text-slate-900 mt-0.5 block">
                  {demographics.age !== null && demographics.age !== undefined ? `${demographics.age} years` : (
                    <span className="text-amber-700 italic font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Sex</span>
                <span className="text-sm font-semibold text-slate-900 mt-0.5 block capitalize">
                  {demographics.sex ? demographics.sex : (
                    <span className="text-amber-700 italic font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Pregnancy / Lactation</span>
                <div className="text-xs text-slate-700 mt-0.5 flex flex-wrap gap-1 items-center">
                  {demographics.pregnancy_status !== undefined && demographics.pregnancy_status !== null ? (
                    <span className="font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded text-[11px]">
                      {demographics.pregnancy_status}
                    </span>
                  ) : (
                    <span className="text-slate-400 italic text-[11px]">Preg: unk</span>
                  )}
                  {demographics.breastfeeding_status !== undefined && demographics.breastfeeding_status !== null ? (
                    <span className="font-medium text-slate-700 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-[11px]">
                      BF: {demographics.breastfeeding_status ? 'yes' : 'no'}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Biometrics</span>
                <span className="text-xs text-slate-700 mt-0.5 block">
                  {demographics.height ? `${demographics.height} cm` : 'Ht: unk'},{' '}
                  {demographics.weight ? `${demographics.weight} kg` : 'Wt: unk'}{' '}
                  {demographics.bmi ? `(BMI ${demographics.bmi})` : ''}
                </span>
              </div>
            </div>
          </div>

          {/* Section 2: Conditions */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <Activity className="w-4 h-4 text-indigo-600" />
              <span>Conditions ({conditions.length})</span>
            </div>

            {conditions.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2">
                No active medical conditions or diagnoses documented in the uploaded record.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-100 text-slate-600 uppercase text-[10px] font-semibold">
                    <tr>
                      <th className="p-2.5 rounded-l">Diagnosis / Condition</th>
                      <th className="p-2.5">Normalized Name</th>
                      <th className="p-2.5 rounded-r">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 bg-white">
                    {conditions.map((c, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="p-2.5 font-medium text-slate-900">{c.name}</td>
                        <td className="p-2.5 text-slate-600 font-mono text-[11px]">{c.normalized_name}</td>
                        <td className="p-2.5">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 capitalize">
                            {c.status || 'active'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section 3: Clinical Status & Vitals */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <Clock className="w-4 h-4 text-emerald-600" />
              <span>Clinical Status &amp; Vitals</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">
                  ECOG Performance Status
                </span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {ecogScore !== undefined && ecogScore !== null ? (
                    <span className="text-slate-900 font-medium">ECOG {ecogScore}</span>
                  ) : (
                    <span className="text-amber-700 italic text-xs font-normal">
                      UNKNOWN (Not documented)
                    </span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">Blood Pressure</span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {vitalSigns?.systolic_bp !== undefined && vitalSigns?.systolic_bp !== null && vitalSigns?.diastolic_bp !== undefined && vitalSigns?.diastolic_bp !== null ? (
                    <span className="text-slate-900 font-mono">
                      {vitalSigns.systolic_bp}/{vitalSigns.diastolic_bp} {vitalSigns.unit || 'mmHg'}
                    </span>
                  ) : (
                    <span className="text-slate-400 italic text-xs font-normal">Not documented</span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">
                  Active Serious Infection
                </span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {activeSeriousInfection === false ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> None / Absent (false)
                    </span>
                  ) : activeSeriousInfection === true ? (
                    <span className="inline-flex items-center gap-1 text-rose-700 text-xs font-medium">
                      <AlertTriangle className="w-3.5 h-3.5" /> Active Infection (true)
                    </span>
                  ) : (
                    <span className="text-amber-700 italic text-xs font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">
                  Cardiac Disease
                </span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {uncontrolledCardiacDisease === false ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> None / Controlled (false)
                    </span>
                  ) : uncontrolledCardiacDisease === true ? (
                    <span className="inline-flex items-center gap-1 text-rose-700 text-xs font-medium">
                      <AlertTriangle className="w-3.5 h-3.5" /> Uncontrolled (true)
                    </span>
                  ) : (
                    <span className="text-amber-700 italic text-xs font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>
            </div>

            {/* Treatment & Safety History row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-200/80">
              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">
                  Recent Systemic Anticancer Therapy
                </span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {recentTherapy === false ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> None Documented (false)
                    </span>
                  ) : recentTherapy === true ? (
                    <span className="inline-flex items-center gap-1 text-rose-700 text-xs font-medium">
                      <AlertTriangle className="w-3.5 h-3.5" /> Recent Therapy (true)
                    </span>
                  ) : (
                    <span className="text-amber-700 italic text-xs font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>

              <div className="bg-white p-3 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block uppercase font-medium">
                  Investigational Therapy Hypersensitivity
                </span>
                <span className="text-sm font-semibold mt-0.5 block">
                  {severeHypersensitivity === false ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> None Documented (false)
                    </span>
                  ) : severeHypersensitivity === true ? (
                    <span className="inline-flex items-center gap-1 text-rose-700 text-xs font-medium">
                      <AlertTriangle className="w-3.5 h-3.5" /> Severe Hypersensitivity (true)
                    </span>
                  ) : (
                    <span className="text-amber-700 italic text-xs font-normal">UNKNOWN</span>
                  )}
                </span>
              </div>
            </div>
          </div>

          {/* Section 4: Laboratory Results */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <FlaskConical className="w-4 h-4 text-amber-600" />
              <span>Laboratory Results ({labs.length})</span>
            </div>

            {labs.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2">
                No laboratory test values documented in the uploaded record.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-100 text-slate-600 uppercase text-[10px] font-semibold">
                    <tr>
                      <th className="p-2.5 rounded-l">Test</th>
                      <th className="p-2.5">Value</th>
                      <th className="p-2.5">Unit</th>
                      <th className="p-2.5 rounded-r">Reference Range</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 bg-white">
                    {labs.map((l, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="p-2.5 font-medium text-slate-900">{l.name}</td>
                        <td className="p-2.5 font-mono font-bold text-sky-900">{l.value}</td>
                        <td className="p-2.5 text-slate-600">{l.unit}</td>
                        <td className="p-2.5 text-slate-500">
                          {l.reference_range || <span className="text-slate-400 italic">Unspecified</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section 5: Medications */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <Pill className="w-4 h-4 text-emerald-600" />
              <span>Medications ({meds.length})</span>
            </div>

            {meds.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2">
                No active medications documented in the uploaded record.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-100 text-slate-600 uppercase text-[10px] font-semibold">
                    <tr>
                      <th className="p-2.5 rounded-l">Medication</th>
                      <th className="p-2.5">Dose</th>
                      <th className="p-2.5">Frequency</th>
                      <th className="p-2.5 rounded-r">Route</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 bg-white">
                    {meds.map((m, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="p-2.5 font-medium text-slate-900">{m.name}</td>
                        <td className="p-2.5 text-slate-700">
                          {m.dose ? `${m.dose} ${m.unit || ''}` : <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-2.5 text-slate-600">
                          {m.frequency || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-2.5 text-slate-600">
                          {m.route || <span className="text-slate-400 italic">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section 6: Allergies */}
          <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-200 text-slate-800 font-semibold text-xs uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
              <span>Allergies ({allergies.length})</span>
            </div>

            {allergies.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-2">
                No drug or substance allergies documented in the uploaded record.
              </p>
            ) : (
              <div className="space-y-2">
                {allergies.map((a, idx) => (
                  <div key={idx} className="bg-white p-2.5 rounded border border-slate-200 flex items-center justify-between text-xs">
                    <div>
                      <span className="font-medium text-slate-900">{a.substance || a.allergen}</span>
                      {a.source_document && (
                        <span className="text-[10px] text-slate-400 font-mono ml-2">({a.source_document})</span>
                      )}
                    </div>
                    <span className="text-slate-500">
                      {a.reaction ? `Reaction: ${a.reaction}` : ''}{' '}
                      {a.severity ? `(${a.severity})` : (
                        (a.substance || a.allergen)?.toLowerCase().includes('none') ? (
                          <span className="text-emerald-700 font-medium">Severity: None documented</span>
                        ) : ''
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 7: Unknown / Missing Information */}
          <div className="border border-amber-200 rounded-lg p-4 bg-amber-50/40">
            <div className="flex items-center gap-2 pb-2 mb-3 border-b border-amber-200 text-amber-900 font-semibold text-xs uppercase tracking-wider">
              <HelpCircle className="w-4 h-4 text-amber-700" />
              <span>Unknown / Missing Information ({missing.length})</span>
            </div>

            {missing.length === 0 ? (
              <div className="flex items-center gap-2 text-xs text-emerald-800 bg-emerald-50 p-2.5 rounded border border-emerald-200">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>None — All standard clinical fields documented in this patient record.</span>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-[11px] text-amber-900 mb-2">
                  The following fields were not present in the uploaded document and remain strictly UNKNOWN (no clinical values have been assumed):
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {missing.map((m, idx) => (
                    <div key={idx} className="bg-white p-2.5 rounded border border-amber-200 text-xs flex items-start gap-2">
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 uppercase shrink-0">
                        UNKNOWN
                      </span>
                      <div>
                        <strong className="text-slate-900 block font-medium capitalize">
                          {m.field.replace(/_/g, ' ')}
                        </strong>
                        <span className="text-[11px] text-slate-600 block mt-0.5">{m.description}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Action Bar (Save / Cancel) */}
        <div className="border-t border-slate-200 p-6 bg-slate-50 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Strict Provenance: {sourceType} ({sourceDocument})</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleCancelReview}
              disabled={isSaving}
              className="px-4 py-2 text-xs font-semibold rounded-md border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="inline-flex items-center gap-2 px-5 py-2 text-xs font-semibold rounded-md bg-sky-800 text-white hover:bg-sky-900 shadow-sm transition disabled:opacity-50 cursor-pointer"
            >
              {isSaving ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Saving Patient Profile...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>Save Patient Profile</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW 2: DROP ZONE & FILE SELECTION
  // =========================================================================
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden animate-in fade-in duration-200">
      <div className="border-b border-slate-200 p-6 bg-slate-50/80">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              Upload Patient Record
            </h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-600 max-w-2xl">
              Upload a clinical patient PDF or structured JSON record to extract and normalize patient attributes for clinical trial eligibility screening.
            </p>
          </div>

          {onSwitchToManual && (
            <button
              type="button"
              onClick={onSwitchToManual}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-100 text-slate-700 text-xs font-semibold transition cursor-pointer self-start sm:self-auto"
            >
              <User className="w-3.5 h-3.5 text-sky-600" />
              <span>Enter Patient Manually</span>
            </button>
          )}
        </div>
      </div>

      <div className="p-6">
        {/* Error Alert */}
        {error && (
          <div className="mb-5 p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <strong className="font-semibold block">Upload Error:</strong>
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-rose-500 hover:text-rose-700"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Drag & Drop Card */}
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-10 text-center transition-all ${
            dragActive
              ? 'border-sky-500 bg-sky-50/60'
              : 'border-slate-300 hover:border-slate-400 bg-slate-50/30'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.json,application/pdf,application/json"
            onChange={handleChange}
            className="hidden"
            id="patient-file-input"
          />

          {isExtracting ? (
            <div className="py-6 space-y-4">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-sky-100 text-sky-800 mb-2">
                <div className="w-6 h-6 border-3 border-sky-300 border-t-sky-800 rounded-full animate-spin" />
              </div>
              <h3 className="text-base font-semibold text-slate-900">
                Extracting Patient Information...
              </h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Parsing clinical documentation, normalising laboratory units, and identifying documented criteria with zero clinical inference.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-sky-50 text-sky-800 border border-sky-100">
                <UploadCloud className="w-6 h-6" />
              </div>

              <div>
                <h3 className="text-base font-semibold text-slate-900">
                  Drag &amp; drop a PDF or JSON file here
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Supports medical PDF records and structured JSON EHR exports (up to 30MB)
                </p>
              </div>

              <div>
                <label
                  htmlFor="patient-file-input"
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-md bg-sky-800 hover:bg-sky-900 text-white text-xs font-semibold shadow-sm transition cursor-pointer"
                >
                  <FileText className="w-4 h-4" />
                  <span>Choose File</span>
                </label>
              </div>

              <div className="pt-2 flex items-center justify-center gap-4 text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <FileText className="w-3.5 h-3.5 text-rose-500" />
                  <span>PDF (.pdf)</span>
                </span>
                <span>•</span>
                <span className="inline-flex items-center gap-1">
                  <FileCode className="w-3.5 h-3.5 text-amber-500" />
                  <span>JSON (.json)</span>
                </span>
                <span>•</span>
                <span>Supported: PDF, JSON</span>
              </div>
            </div>
          )}
        </div>

        {/* Privacy & Provenance Notice */}
        <div className="mt-5 p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex items-start gap-2.5 text-xs text-slate-600">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <strong className="font-semibold text-slate-800 block">Strict Privacy &amp; Zero Inference Standard</strong>
            <span>
              All patient information is extracted directly from explicit documentation without diagnostic inference.
              Documents are processed securely and presented for review prior to saving.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
