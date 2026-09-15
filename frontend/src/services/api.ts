import {
  HealthResponse,
  PDFUploadResponse,
  ProtocolExtractionResponse,
  RAGIndexRequest,
  RAGIndexResponse,
  RAGSearchRequest,
  RAGSearchResponse,
  RAGStatusResponse,
} from '../types';

const API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) || '';
const FASTAPI_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_FASTAPI_BASE_URL) ||
  API_BASE_URL ||
  '';

/**
 * Configurable timeout for protocol extraction (Render cold-starts can take 60-100s).
 * Defaults to 120 seconds for resilient production communication with sleeping services.
 */
const DEFAULT_EXTRACTION_TIMEOUT_MS = 120000;
export const PROTOCOL_EXTRACTION_TIMEOUT_MS =
  (typeof import.meta !== 'undefined' &&
    import.meta.env &&
    Number(import.meta.env.VITE_PROTOCOL_EXTRACTION_TIMEOUT_MS)) ||
  DEFAULT_EXTRACTION_TIMEOUT_MS;

/**
 * Service to interact with the FastAPI Backend.
 */
export async function getHealthStatus(): Promise<HealthResponse> {
  const url = API_BASE_URL ? `${API_BASE_URL}/health` : '/health';
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status: ${response.status}`);
  }

  return response.json();
}

/**
 * Helper to derive or sanitize a valid trial_id from a protocol filename.
 * Implements deterministic clinical trial identifier conventions:
 * 1. NCT numbers (e.g. NCT01234567, NCT-01234567)
 * 2. 3-part codes with trailing number (e.g. SYN_CARDIO_001, SYN-CARDIO-001 -> SYN-CARDIO-001)
 * 3. 2-part codes with trailing number (e.g. TRIAL-999, CARDIO-101 -> TRIAL-999)
 * 4. Trial codes preceding standard keywords (protocol, clinical, study, draft, v1, etc.)
 * 5. General sanitized alphanumeric fallback (max 32 chars).
 */
export function deriveTrialIdFromFilename(filename: string): string {
  if (!filename) return 'TRIAL-001';

  // 1. NCT numbers: e.g. NCT01234567 or NCT-01234567
  const nctMatch = filename.match(/(?:^|[^a-zA-Z0-9])(NCT[-_]?\d{8})(?:[^a-zA-Z0-9]|$)/i);
  if (nctMatch) {
    return nctMatch[1].toUpperCase().replace('_', '-');
  }

  // Strip extension
  const baseName = filename.replace(/\.[^/.]+$/, '');

  // 2. Standard 3-part clinical trial codes with trailing number/code:
  // e.g., SYN_CARDIO_001_Acute_... -> SYN-CARDIO-001
  const threePartCode = baseName.match(/^([A-Za-z]{2,10}[-_][A-Za-z0-9]{2,12}[-_]\d{1,8})(?:[-_]|$)/i);
  if (threePartCode) {
    return threePartCode[1].toUpperCase().replace(/_/g, '-');
  }

  // 3. Standard 2-part clinical trial codes with trailing number:
  // e.g., TRIAL-999, TRIAL_001, CARDIO-101, ONC-002, STUDY-1
  const twoPartCode = baseName.match(/^([A-Za-z]{2,10}[-_]\d{1,8})(?:[-_]|$)/i);
  if (twoPartCode) {
    return twoPartCode[1].toUpperCase().replace(/_/g, '-');
  }

  // 4. Code followed by standard document suffix (protocol, study, phase, clinical, draft, final, v1):
  // e.g. CARDIO-101_Study_Protocol, TRIAL_A_Protocol
  const suffixMatch = baseName.match(/^([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+){1,3}?)(?:[-_](?:protocol|phase|clinical|trial|study|v\d+|\d{4}|final|draft|amendment))/i);
  if (suffixMatch) {
    return suffixMatch[1].toUpperCase().replace(/_/g, '-');
  }

  // 5. Fallback: sanitize base name to alphanumeric, dashes, and underscores (max 32 chars)
  const clean = baseName
    .replace(/[^a-zA-Z0-9_-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '')
    .slice(0, 32);

  return clean || `trial-${Date.now().toString(36)}`;
}

/**
 * Adapts FastAPI ExtractedProtocol or Node ProtocolExtractionResponse into frontend ProtocolExtractionResponse.
 * Ensures page provenance, criteria IDs, sections, excerpts, and titles are consistently mapped.
 */
export function adaptProtocolResponse(data: any): ProtocolExtractionResponse {
  if (!data) {
    throw new Error('Empty protocol response received from backend');
  }

  const trialId = data.trial_id || data.protocol_id || 'UNKNOWN-TRIAL';
  const trialTitle = data.title || data.trial_title || data.protocol_id || 'Clinical Trial Protocol';
  const protocolId = data.protocol_id || data.trial_identifier || trialId;

  const mapCriterion = (c: any, defaultType: 'inclusion' | 'exclusion'): import('../types').ExtractedCriterion => {
    const rawType = (c.type || defaultType).toLowerCase();
    const criterionType = rawType.includes('inc') ? 'inclusion' : rawType.includes('exc') ? 'exclusion' : defaultType;
    const page = typeof c.source_page === 'number' ? c.source_page : (typeof c.page_number === 'number' ? c.page_number : 1);

    return {
      criterion_id: c.criterion_id || `${criterionType === 'inclusion' ? 'INC' : 'EXC'}-000`,
      type: criterionType as 'inclusion' | 'exclusion',
      text: c.text || c.raw_text || '',
      source_page: page,
      page_number: page,
      section: c.section || `${criterionType === 'inclusion' ? 'Inclusion' : 'Exclusion'} Criteria`,
      source_excerpt: c.source_excerpt || null,
      trial_id: c.trial_id || trialId,
      category: c.category || c.section || undefined,
      structured_rule: c.structured_rule || undefined,
    };
  };

  const inclusionCriteria = (data.inclusion_criteria || []).map((c: any) =>
    mapCriterion(c, 'inclusion')
  );
  const exclusionCriteria = (data.exclusion_criteria || []).map((c: any) =>
    mapCriterion(c, 'exclusion')
  );

  const otherRequirements = (data.other_requirements || []).map((item: any) => {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object' && item.text) return item.text;
    return String(item);
  });

  const totalPages =
    data.extraction_metadata?.total_pages ??
    data.total_pages_analyzed ??
    data.extraction_metadata?.page_count ??
    undefined;

  return {
    trial_id: trialId,
    trial_title: trialTitle,
    title: trialTitle,
    protocol_id: protocolId,
    trial_identifier: protocolId,
    inclusion_criteria: inclusionCriteria,
    exclusion_criteria: exclusionCriteria,
    other_requirements: otherRequirements,
    processing_status:
      data.processing_status ||
      (inclusionCriteria.length > 0 || exclusionCriteria.length > 0 ? 'completed' : 'extracted'),
    total_pages_analyzed: totalPages,
    source_document: data.source_document,
    extraction_metadata: data.extraction_metadata,
    error_message: data.error_message,
  };
}

/**
 * Upload a clinical trial PDF to the authoritative FastAPI backend.
 * Adapts to the consolidated POST /api/v1/trials/{trialId}/extract-protocol endpoint.
 */
export async function uploadTrialPDF(file: File, trialId?: string): Promise<PDFUploadResponse> {
  const effectiveTrialId = trialId || deriveTrialIdFromFilename(file.name);
  const res = await extractProtocol(effectiveTrialId, file);

  return {
    trial_id: res.trial_id,
    filename: file.name,
    status: res.processing_status || 'uploaded',
    file_size_bytes: file.size,
    processing_status: res.processing_status,
    criteria_count: (res.inclusion_criteria?.length || 0) + (res.exclusion_criteria?.length || 0),
    error_message: res.error_message,
  };
}

/**
 * Run protocol text extraction and agent extraction on a clinical trial protocol PDF.
 * Authoritative FastAPI endpoint: POST /api/v1/trials/{trialId}/extract-protocol
 * Handles multipart file upload directly to FastAPI.
 */
export async function extractProtocol(
  trialId: string,
  file?: File,
  timeoutMs: number = PROTOCOL_EXTRACTION_TIMEOUT_MS
): Promise<ProtocolExtractionResponse> {
  const cleanTrialId = trialId.replace(/[^a-zA-Z0-9_-]/g, '') || 'TRIAL-DEFAULT';
  const effectiveBaseUrl = FASTAPI_BASE_URL || API_BASE_URL;

  if (file) {
    const url = effectiveBaseUrl
      ? `${effectiveBaseUrl}/api/v1/trials/${cleanTrialId}/extract-protocol`
      : `/api/v1/trials/${cleanTrialId}/extract-protocol`;

    const formData = new FormData();
    formData.append('file', file);

    const controller = new AbortController();
    const timeoutDuration = timeoutMs > 0 ? timeoutMs : DEFAULT_EXTRACTION_TIMEOUT_MS;
    const timeoutSeconds = Math.round(timeoutDuration / 1000);
    const timeoutId = setTimeout(() => controller.abort(), timeoutDuration);

    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
    } catch (fetchErr: any) {
      clearTimeout(timeoutId);
      if (fetchErr.name === 'AbortError' || controller.signal.aborted) {
        throw new Error(
          `Protocol extraction request timed out after ${timeoutSeconds} seconds. The backend server may be waking up from cold-start or processing a complex protocol. Please try again.`
        );
      }
      throw new Error(
        `Unable to reach backend server (${fetchErr.message || 'network failure'}). Please check your network connection and verify backend status.`
      );
    } finally {
      clearTimeout(timeoutId);
    }

    if (!response.ok) {
      let errorDetail = `Protocol extraction failed with status: ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson.detail) {
          errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
        } else if (errJson.error_message) {
          errorDetail = errJson.error_message;
        }
      } catch {
        // ignore
      }
      throw new Error(errorDetail);
    }

    const rawData = await response.json();
    return adaptProtocolResponse(rawData);
  }

  // If no file passed, attempt to fetch previously processed trial protocol
  const url = effectiveBaseUrl
    ? `${effectiveBaseUrl}/api/v1/trials/${cleanTrialId}`
    : `/api/v1/trials/${cleanTrialId}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Failed to fetch protocol for '${cleanTrialId}' with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  const rawData = await response.json();
  return adaptProtocolResponse(rawData);
}

/**
 * Get previously extracted trial protocol.
 */
export async function getTrialProtocol(trialId: string): Promise<ProtocolExtractionResponse> {
  const cleanTrialId = trialId.replace(/[^a-zA-Z0-9_-]/g, '') || trialId;
  const effectiveBaseUrl = FASTAPI_BASE_URL || API_BASE_URL;
  const url = effectiveBaseUrl
    ? `${effectiveBaseUrl}/api/v1/trials/${cleanTrialId}`
    : `/api/v1/trials/${cleanTrialId}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch trial protocol with status: ${response.status}`);
  }

  const rawData = await response.json();
  return adaptProtocolResponse(rawData);
}

/**
 * Trigger RAG indexing for a clinical trial protocol.
 */
export async function indexTrialRAG(
  trialId: string,
  options?: RAGIndexRequest
): Promise<RAGIndexResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/rag/index`
    : `/api/v1/trials/${trialId}/rag/index`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(options || {}),
  });

  if (!response.ok) {
    let errorDetail = `RAG indexing failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Perform semantic similarity search over indexed protocol evidence.
 */
export async function searchTrialRAG(
  trialId: string,
  request: RAGSearchRequest
): Promise<RAGSearchResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/rag/search`
    : `/api/v1/trials/${trialId}/rag/search`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let errorDetail = `RAG search failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Check whether a trial's protocol is currently indexed in FAISS.
 */
export async function getTrialRAGStatus(trialId: string): Promise<RAGStatusResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/rag/status`
    : `/api/v1/trials/${trialId}/rag/status`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to check RAG index status: ${response.status}`);
  }

  return response.json();
}

/**
 * Module 5: Evaluate Clinical Trial Inclusion Criteria against a Patient Profile.
 */
export async function evaluateInclusionCriteria(
  trialId: string,
  patientProfileId: string
): Promise<import('../types').InclusionEvaluationResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/patients/${patientProfileId}/inclusion-evaluation`
    : `/api/v1/trials/${trialId}/patients/${patientProfileId}/inclusion-evaluation`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Inclusion evaluation failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Module 6: Evaluate Clinical Trial Exclusion Criteria against a Patient Profile.
 */
export async function evaluateExclusionCriteria(
  trialId: string,
  patientProfileId: string
): Promise<import('../types').ExclusionEvaluationResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/patients/${patientProfileId}/exclusion-evaluation`
    : `/api/v1/trials/${trialId}/patients/${patientProfileId}/exclusion-evaluation`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Exclusion evaluation failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Module 7: Evaluate Contradictions and Silent Exclusions.
 */
export async function evaluateContradictions(
  trialId: string,
  patientProfileId: string
): Promise<import('../types').ContradictionEvaluationResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/patients/${patientProfileId}/contradiction-evaluation`
    : `/api/v1/trials/${trialId}/patients/${patientProfileId}/contradiction-evaluation`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Contradiction evaluation failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Module 8: Evaluate Final Clinical Trial Eligibility (Decision / Reviewer Agent).
 */
export async function evaluateFinalEligibility(
  trialId: string,
  patientProfileId: string
): Promise<import('../types').FinalEvaluationResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/patients/${patientProfileId}/final-evaluation`
    : `/api/v1/trials/${trialId}/patients/${patientProfileId}/final-evaluation`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Final evaluation failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Module 9: Run the multi-agent LangGraph eligibility workflow against the Python FastAPI engine.
 * Sends the full structured patient profile so retrieval -> inclusion -> exclusion ->
 * contradiction -> decision agents execute end-to-end on the authoritative backend.
 */
export async function runWorkflowEvaluation(
  trialId: string,
  patientProfile: import('../types').FastAPIPatientProfile,
  referenceDate?: string | null
): Promise<import('../types').WorkflowStateResponse> {
  const url = `${FASTAPI_BASE_URL}/api/v1/workflow/evaluate`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      trial_id: trialId,
      patient_profile: patientProfile,
      reference_date: referenceDate || null,
    } as import('../types').WorkflowEvaluateRequest),
  });

  if (!response.ok) {
    let errorDetail = `Workflow evaluation failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail =
          typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Fetch persisted assessment summary history (newest first) from the FastAPI backend.
 * Throws a descriptive error when persistence is not configured (503) or the backend
 * is unavailable.
 */
export async function getAssessments(
  options?: { limit?: number; trial_id?: string; patient_profile_id?: string }
): Promise<import('../types').AssessmentSummaryResponse[]> {
  const params = new URLSearchParams();
  if (options?.limit != null) params.set('limit', String(options.limit));
  if (options?.trial_id) params.set('trial_id', options.trial_id);
  if (options?.patient_profile_id) params.set('patient_profile_id', options.patient_profile_id);
  const qs = params.toString();
  const url = `${FASTAPI_BASE_URL}/api/v1/assessments${qs ? `?${qs}` : ''}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `Failed to fetch assessment history with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail =
          typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Fetch the full audit detail (warnings, errors, snapshot, traces) for a single
 * persisted assessment run. Returns null for a 404 "not found" response.
 */
export async function getAssessmentDetail(
  assessmentId: string
): Promise<import('../types').AssessmentDetailResponse | null> {
  const url = `${FASTAPI_BASE_URL}/api/v1/assessments/${encodeURIComponent(assessmentId)}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    let errorDetail = `Failed to fetch assessment detail with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail =
          typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

/**
 * Fetch all available clinical trials from the data store.
 */
export async function getTrials(): Promise<ProtocolExtractionResponse[]> {
  const effectiveBaseUrl = FASTAPI_BASE_URL || API_BASE_URL;
  const url = effectiveBaseUrl ? `${effectiveBaseUrl}/api/v1/trials` : '/api/v1/trials';
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 404) {
        return [];
      }
      throw new Error(`Failed to fetch trials with status: ${response.status}`);
    }

    const data = await response.json();
    return Array.isArray(data) ? data.map(adaptProtocolResponse) : [];
  } catch (err) {
    console.warn('Could not fetch trial list from backend:', err);
    return [];
  }
}

/**
 * Fetch all available patient profiles from the data store.
 */
export async function getPatients(): Promise<import('../types').StructuredPatientProfile[]> {
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/patients` : '/api/v1/patients';
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch patients with status: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch a single patient profile by ID.
 */
export async function getPatientProfile(
  patientProfileId: string
): Promise<import('../types').StructuredPatientProfile> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/patients/${patientProfileId}`
    : `/api/v1/patients/${patientProfileId}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch patient profile with status: ${response.status}`);
  }

  return response.json();
}

/**
 * Create or update a structured patient profile.
 */
export async function createPatientProfile(
  data: any
): Promise<import('../types').StructuredPatientProfile> {
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/patients/profile` : '/api/v1/patients/profile';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let errorDetail = `Failed to create patient profile with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export interface PatientExtractionResponse {
  profile: import('../types').StructuredPatientProfile;
  extractedFields: string[];
  sourceDocument: string;
  sourceType: string;
}

/**
 * Upload and extract patient clinical information from a PDF or JSON document.
 * Returns the extracted structured profile for user review before saving.
 */
export async function extractPatientDocument(file: File): Promise<PatientExtractionResponse> {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (ext !== '.pdf' && ext !== '.json') {
    throw new Error('Please upload a PDF or JSON patient record.');
  }

  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/patients/extract-document`
    : '/api/v1/patients/extract-document';

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let errorDetail = `Extraction failed with status: ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json();
}



