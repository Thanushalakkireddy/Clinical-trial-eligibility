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
  'http://localhost:8000';

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
 * Upload a clinical trial PDF to the FastAPI backend.
 */
export async function uploadTrialPDF(file: File): Promise<PDFUploadResponse> {
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/trials/upload` : '/api/v1/trials/upload';
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let errorDetail = `Upload failed with status: ${response.status}`;
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
 * Run protocol text extraction and agent extraction on an uploaded trial.
 */
export async function extractProtocol(trialId: string): Promise<ProtocolExtractionResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}/extract-protocol`
    : `/api/v1/trials/${trialId}/extract-protocol`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
    },
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

/**
 * Get previously extracted trial protocol.
 */
export async function getTrialProtocol(trialId: string): Promise<ProtocolExtractionResponse> {
  const url = API_BASE_URL
    ? `${API_BASE_URL}/api/v1/trials/${trialId}`
    : `/api/v1/trials/${trialId}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch trial protocol with status: ${response.status}`);
  }

  return response.json();
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
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/trials` : '/api/v1/trials';
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch trials with status: ${response.status}`);
  }

  return response.json();
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



