import React, { useState, useRef, useEffect } from 'react';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  ChevronRight,
  Bookmark,
  FileCheck,
  Ban,
  Hash,
  Copy,
  Check,
} from 'lucide-react';
import { uploadTrialPDF, extractProtocol, getTrials } from '../services/api';
import { ProtocolExtractionResponse, ExtractedCriterion } from '../types';

interface ProtocolUploaderProps {
  onTrialActive?: (trialId: string) => void;
}

export const ProtocolUploader: React.FC<ProtocolUploaderProps> = ({ onTrialActive }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [trialId, setTrialId] = useState<string | null>(null);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [extractionResult, setExtractionResult] = useState<ProtocolExtractionResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'inclusion' | 'exclusion'>('all');
  const [copiedId, setCopiedId] = useState(false);
  const [availableTrials, setAvailableTrials] = useState<Array<{ trial_id: string; filename?: string; status?: string }>>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadTrials();
  }, []);

  const loadTrials = async () => {
    try {
      const data = await getTrials();
      if (Array.isArray(data)) {
        setAvailableTrials(data);
      }
    } catch {
      // Backend may be initializing
    }
  };

  const handleFileSelect = (selectedFile: File) => {
    setErrorMessage(null);
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setErrorMessage('Invalid file format. Please upload a PDF protocol document (.pdf).');
      return;
    }
    if (selectedFile.size > 25 * 1024 * 1024) {
      setErrorMessage('File size exceeds the 25 MB limit.');
      return;
    }
    setFile(selectedFile);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setErrorMessage(null);
    try {
      const res = await uploadTrialPDF(file);
      setTrialId(res.trial_id);
      setUploadedFilename(res.filename);
      onTrialActive?.(res.trial_id);
      // Reload trial list to include the newly uploaded trial
      loadTrials();
      // Automatically trigger extraction after successful upload
      await handleExtract(res.trial_id);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload protocol PDF.');
    } finally {
      setUploading(false);
    }
  };

  const handleExtract = async (id: string) => {
    setExtracting(true);
    setErrorMessage(null);
    try {
      const res = await extractProtocol(id);
      setExtractionResult(res);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to extract protocol criteria.');
    } finally {
      setExtracting(false);
    }
  };

  const handleSelectExistingTrial = async (selectedId: string) => {
    if (!selectedId) {
      setTrialId(null);
      setExtractionResult(null);
      return;
    }
    setTrialId(selectedId);
    setFile(null);
    onTrialActive?.(selectedId);
    await handleExtract(selectedId);
  };

  const copyTrialId = () => {
    if (trialId) {
      navigator.clipboard.writeText(trialId);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  const inclusionCount = extractionResult?.inclusion_criteria?.length || 0;
  const exclusionCount = extractionResult?.exclusion_criteria?.length || 0;

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-sky-50 border border-sky-200 text-sky-800 text-[11px] font-semibold mb-1">
            <FileCheck className="w-3 h-3 text-sky-600" />
            <span>Protocol Documents &amp; Evidence Extraction</span>
          </div>
          <h2 className="text-lg font-bold text-slate-900">Clinical Trial Protocol Ingestion</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Upload a trial protocol PDF to extract inclusion and exclusion criteria with source page provenance.
          </p>
        </div>

        {availableTrials.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 font-medium">Ingested Protocols ({availableTrials.length}):</span>
            <select
              value={trialId || ''}
              onChange={(e) => handleSelectExistingTrial(e.target.value)}
              className="text-xs py-1.5 px-3 rounded-md border border-slate-300 bg-white text-slate-700 focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500"
            >
              <option value="">Select protocol to view...</option>
              {availableTrials.map((t) => (
                <option key={t.trial_id} value={t.trial_id}>
                  {t.trial_id} {t.filename ? `(${t.filename})` : ''}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Upload Dropzone */}
      <div className="mt-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
            isDragging
              ? 'border-sky-500 bg-sky-50/50'
              : file
              ? 'border-emerald-300 bg-emerald-50/30'
              : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
          }`}
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => e.target.files && handleFileSelect(e.target.files[0])}
            accept=".pdf,application/pdf"
            className="hidden"
          />

          <div className="flex flex-col items-center justify-center gap-2">
            <div className="w-10 h-10 rounded-full bg-sky-100 flex items-center justify-center text-sky-700">
              <UploadCloud className="w-5 h-5" />
            </div>

            {file ? (
              <div>
                <div className="flex items-center justify-center gap-1.5 text-sm font-semibold text-slate-800">
                  <FileText className="w-4 h-4 text-emerald-600" />
                  <span>{file.name}</span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB • Ready for protocol extraction
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-slate-700">
                  <span className="text-sky-700 font-semibold hover:underline">Click to browse</span> or drag and drop trial protocol PDF
                </p>
                <p className="text-xs text-slate-500 mt-1">Standard clinical trial protocol PDFs (max 25 MB)</p>
              </div>
            )}
          </div>
        </div>

        {/* Upload Action Button */}
        {file && !extractionResult && (
          <div className="mt-4 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleUpload}
              disabled={uploading || extracting}
              className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors disabled:opacity-50"
            >
              {uploading || extracting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>{uploading ? 'Uploading Protocol...' : 'Extracting Criteria...'}</span>
                </>
              ) : (
                <>
                  <span>Extract Protocol Criteria</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div className="mt-4 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Processing Error</p>
            <p className="mt-0.5 text-rose-700">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Extraction Active State */}
      {extracting && (
        <div className="mt-6 p-6 rounded-xl border border-sky-100 bg-sky-50/40 text-center space-y-3">
          <Loader2 className="w-6 h-6 text-sky-600 animate-spin mx-auto" />
          <p className="text-sm font-semibold text-sky-900">Extracting protocol criteria...</p>
          <p className="text-xs text-slate-600 max-w-md mx-auto">
            Extracting page-by-page text, normalizing clinical formatting, and structuring inclusion and exclusion rules with exact page citations.
          </p>
        </div>
      )}

      {/* Extraction Results Viewer */}
      {extractionResult && (
        <div className="mt-8 space-y-6 pt-6 border-t border-slate-200">
          {/* Metadata Card */}
          <div className="p-4 rounded-lg bg-slate-900 text-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={`text-[11px] font-mono font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${
                    extractionResult.processing_status === 'validation_failed'
                      ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                      : 'bg-emerald-950/80 text-emerald-400 border-emerald-800'
                  }`}
                >
                  {extractionResult.processing_status}
                </span>
                {extractionResult.trial_identifier && (
                  <span className="text-[11px] font-mono text-sky-300 font-semibold bg-sky-950 px-2 py-0.5 rounded border border-sky-800">
                    {extractionResult.trial_identifier}
                  </span>
                )}
                {extractionResult.total_pages_analyzed && (
                  <span className="text-[11px] text-slate-400">
                    {extractionResult.total_pages_analyzed} Pages Analyzed
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-white tracking-tight">
                {extractionResult.trial_title}
              </h3>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400">Trial ID:</span>
              <code className="bg-slate-800 px-2 py-1 rounded text-slate-200 font-mono text-[11px]">
                {extractionResult.trial_id.slice(0, 8)}...
              </code>
              <button
                type="button"
                onClick={copyTrialId}
                title="Copy Full Trial ID"
                className="p-1 rounded hover:bg-slate-800 text-slate-300 transition-colors"
              >
                {copiedId ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {/* Validation Failure Warning */}
          {(extractionResult.processing_status === 'validation_failed' ||
            (inclusionCount === 0 && exclusionCount === 0)) && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-amber-950 space-y-2 shadow-2xs">
              <div className="flex items-center gap-2 font-bold text-sm text-amber-950">
                <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
                <span>Protocol Source Validation Alert: Document Criteria Not Found</span>
              </div>
              <p className="text-xs text-amber-900 leading-relaxed">
                {extractionResult.error_message ||
                  'The uploaded file does not contain identifiable inclusion or exclusion criteria. In accordance with clinical trial protocol safety principles, eligibility cannot be evaluated without validated criteria from the source document. No default criteria have been fabricated.'}
              </p>
              <p className="text-[11px] text-amber-800 font-medium">
                Note: Non-protocol documents (e.g. resumes, CVs, invoices, or general text) cannot be evaluated. Please upload an authentic Clinical Trial Protocol PDF.
              </p>
            </div>
          )}

          {/* Criteria Navigation Tabs */}
          <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
            <button
              type="button"
              onClick={() => setActiveTab('all')}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                activeTab === 'all'
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              All Criteria ({inclusionCount + exclusionCount})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('inclusion')}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                activeTab === 'inclusion'
                  ? 'bg-emerald-700 text-white'
                  : 'text-emerald-800 hover:bg-emerald-50'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Inclusion Criteria ({inclusionCount})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('exclusion')}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                activeTab === 'exclusion'
                  ? 'bg-rose-700 text-white'
                  : 'text-rose-800 hover:bg-rose-50'
              }`}
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Exclusion Criteria ({exclusionCount})</span>
            </button>
          </div>

          {/* Criteria Grid */}
          <div className="space-y-4">
            {/* Inclusion Criteria Section */}
            {(activeTab === 'all' || activeTab === 'inclusion') && (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-900 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <span>Inclusion Criteria (Mandatory Prerequisites)</span>
                  </h4>
                  <span className="text-[11px] text-slate-500 font-medium">
                    {inclusionCount} requirements identified
                  </span>
                </div>

                {extractionResult.inclusion_criteria.length === 0 ? (
                  <p className="text-xs text-slate-400 italic p-3 bg-slate-50 rounded-lg">
                    No explicit inclusion criteria extracted.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 gap-2.5">
                    {extractionResult.inclusion_criteria.map((criterion) => (
                      <CriterionCard key={criterion.criterion_id} criterion={criterion} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Exclusion Criteria Section */}
            {(activeTab === 'all' || activeTab === 'exclusion') && (
              <div className="space-y-2.5 pt-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-rose-900 flex items-center gap-1.5">
                    <Ban className="w-4 h-4 text-rose-600" />
                    <span>Exclusion Criteria (Contraindications & Disqualifying Conditions)</span>
                  </h4>
                  <span className="text-[11px] text-slate-500 font-medium">
                    {exclusionCount} disqualifying conditions identified
                  </span>
                </div>

                {extractionResult.exclusion_criteria.length === 0 ? (
                  <p className="text-xs text-slate-400 italic p-3 bg-slate-50 rounded-lg">
                    No explicit exclusion criteria extracted.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 gap-2.5">
                    {extractionResult.exclusion_criteria.map((criterion) => (
                      <CriterionCard key={criterion.criterion_id} criterion={criterion} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Other Requirements Section */}
            {extractionResult.other_requirements && extractionResult.other_requirements.length > 0 && (
              <div className="pt-4 border-t border-slate-100">
                <h4 className="text-xs font-semibold text-slate-700 mb-2">
                  Additional Eligibility Notes & Guidelines
                </h4>
                <ul className="list-disc list-inside text-xs text-slate-600 space-y-1">
                  {extractionResult.other_requirements.map((note, idx) => (
                    <li key={idx}>{note}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

interface CriterionCardProps {
  criterion: ExtractedCriterion;
}

const CriterionCard: React.FC<CriterionCardProps> = ({ criterion }) => {
  const isInclusion = criterion.type === 'inclusion';

  return (
    <div
      className={`p-3.5 rounded-lg border text-left transition-all ${
        isInclusion
          ? 'bg-emerald-50/30 border-emerald-200 hover:border-emerald-300'
          : 'bg-rose-50/30 border-rose-200 hover:border-rose-300'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${
              isInclusion
                ? 'bg-emerald-100 text-emerald-900 border-emerald-300'
                : 'bg-rose-100 text-rose-900 border-rose-300'
            }`}
          >
            {criterion.criterion_id}
          </span>
          <span className="text-[10px] uppercase font-semibold text-slate-500">
            {isInclusion ? 'Inclusion' : 'Exclusion'}
          </span>
        </div>

        {criterion.source_page && (
          <div className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200 shadow-2xs">
            <Bookmark className="w-3 h-3 text-sky-600" />
            <span>Page {criterion.source_page}</span>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-800 leading-relaxed font-sans font-medium">
        {criterion.text}
      </p>

      {criterion.trial_id && (
        <div className="mt-2 pt-2 border-t border-slate-200/60 flex items-center justify-between text-[10px] text-slate-400">
          <span>Source Document: {criterion.trial_id.slice(0, 8)}...</span>
          <span className="text-emerald-700 font-medium">Traceable Evidence</span>
        </div>
      )}
    </div>
  );
};
