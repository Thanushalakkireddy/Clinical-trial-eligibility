import express from 'express';
import path from 'path';
import multer from 'multer';
import { createServer as createViteServer } from 'vite';
import { dataStore } from './server/dataStore';
import { buildStructuredProfile } from './server/normalization';
import {
  evaluateAllInclusionCriteria,
  evaluateAllExclusionCriteria,
} from './server/evaluator';
import { evaluateContradictions } from './server/contradictionEvaluator';
import { evaluateFinalEligibility } from './server/decisionReviewer';
import { ProtocolExtractionResponse, StructuredPatientProfile } from './server/types';
import {
  extractPatientFromPdfBuffer,
  extractPatientFromJson,
} from './server/patientExtractor';
import { extractProtocolFromPdfBuffer } from './server/protocolExtractor';
import {
  authenticateUser,
  generateToken,
  requireAuth,
  extractAuth,
} from './server/auth';

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 30 * 1024 * 1024 }, // 30 MB max
});

async function startServer() {
  const app = express();
  const PORT = 3000;

  // --------------------------------------------------------------------------
  // CORS & SECURITY HEADERS (MODULE 9)
  // --------------------------------------------------------------------------
  const allowedOrigins = (process.env.CORS_ORIGINS || 'http://localhost:3000,http://127.0.0.1:3000')
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);

  app.use((req, res, next) => {
    const origin = req.headers.origin;
    if (origin) {
      if (allowedOrigins.includes(origin) || allowedOrigins.includes('*')) {
        res.setHeader('Access-Control-Allow-Origin', origin);
      }
    } else {
      res.setHeader('Access-Control-Allow-Origin', '*');
    }
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');

    if (req.method === 'OPTIONS') {
      return res.sendStatus(204);
    }
    next();
  });

  // Request logger (safe, no PII)
  app.use((req, res, next) => {
    const start = Date.now();
    res.on('finish', () => {
      const duration = Date.now() - start;
      if (req.path.startsWith('/api') || req.path === '/health') {
        console.log(`[HTTP] ${req.method} ${req.path} ${res.statusCode} - ${duration}ms`);
      }
    });
    next();
  });

  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use(extractAuth);

  // --------------------------------------------------------------------------
  // HEALTH ENDPOINTS
  // --------------------------------------------------------------------------
  const healthHandler = (_req: express.Request, res: express.Response) => {
    res.json({
      status: 'ok',
      service: 'clinical-trial-eligibility-api',
      environment: process.env.ENVIRONMENT || 'development',
      version: '1.0.0',
      llm_provider: process.env.LLM_PROVIDER || 'xai',
      xai_configured: Boolean(process.env.XAI_API_KEY),
      gemini_configured: Boolean(process.env.GEMINI_API_KEY),
    });
  };

  app.get('/health', healthHandler);
  app.get('/api/v1/health', healthHandler);

  // --------------------------------------------------------------------------
  // AUTHENTICATION & AUTHORIZATION (MODULE 9)
  // --------------------------------------------------------------------------
  app.post('/api/v1/auth/login', (req, res) => {
    const username = req.body?.username;
    const password = req.body?.password;

    if (!username || !password) {
      return res.status(400).json({ detail: 'Username and password are required' });
    }

    const user = authenticateUser(username, password);
    if (!user) {
      return res.status(401).json({ detail: 'Incorrect username or password' });
    }

    const token = generateToken(user.username, user.role);
    res.json({
      access_token: token,
      token_type: 'bearer',
      user: {
        username: user.username,
        role: user.role,
      },
    });
  });

  app.get('/api/v1/auth/me', requireAuth, (req, res) => {
    res.json({
      username: (req as any).user.username,
      role: (req as any).user.role,
    });
  });

  // --------------------------------------------------------------------------
  // TRIALS & PROTOCOLS (MODULE 2)
  // --------------------------------------------------------------------------
  app.get('/api/v1/trials', (_req, res) => {
    const trials = dataStore.getTrials();
    res.json(trials);
  });

  app.post('/api/v1/trials', (req, res) => {
    const trial = req.body;
    if (!trial || !trial.trial_id) {
      return res.status(400).json({ detail: 'trial_id is required' });
    }
    dataStore.saveTrial(trial);
    res.status(201).json(trial);
  });

  app.post('/api/v1/trials/upload', upload.single('file') as any, async (req, res) => {
    const file = req.file;

    // Validate PDF MIME type and file extension if a file was provided
    if (!file) {
      return res.status(400).json({ detail: 'A PDF protocol file must be provided for upload.' });
    }

    const ext = path.extname(file.originalname).toLowerCase();
    const isPdf = ext === '.pdf' || file.mimetype === 'application/pdf';
    if (!isPdf) {
      return res.status(400).json({ detail: 'Only PDF files are permitted for protocol uploads.' });
    }

    const rawName = file.originalname;
    // Path traversal sanitization: retain only safe basename characters
    const filename = path.basename(rawName).replace(/[^a-zA-Z0-9._-]/g, '_');
    const fileSize = file.size;

    // Generate clean unique trial ID
    const trialId = `trial_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 7)}`;

    // Strictly extract protocol criteria directly from uploaded PDF buffer
    let extractedTrial: ProtocolExtractionResponse;
    try {
      extractedTrial = await extractProtocolFromPdfBuffer(file.buffer, filename, trialId);
    } catch (err: any) {
      extractedTrial = {
        trial_id: trialId,
        trial_title: filename.replace(/\.[^/.]+$/, '').replace(/_/g, ' '),
        trial_identifier: null,
        inclusion_criteria: [],
        exclusion_criteria: [],
        other_requirements: [],
        processing_status: 'validation_failed',
        total_pages_analyzed: 0,
        error_message: `Extraction error: ${err?.message || 'Failed to parse protocol'}`,
      };
    }

    // Save extracted trial to data store
    dataStore.saveTrial(extractedTrial, filename, fileSize);

    res.json({
      trial_id: trialId,
      filename,
      status: extractedTrial.processing_status === 'validation_failed' ? 'validation_failed' : 'uploaded',
      processing_status: extractedTrial.processing_status,
      file_size_bytes: fileSize,
      error_message: extractedTrial.error_message || null,
      criteria_count: extractedTrial.inclusion_criteria.length + extractedTrial.exclusion_criteria.length,
    });
  });

  app.get('/api/v1/trials/:trialId', (req, res) => {
    const trialId = req.params.trialId;
    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }
    res.json(trial);
  });

  app.post('/api/v1/trials/:trialId/extract-protocol', upload.single('file') as any, async (req, res) => {
    const trialId = req.params.trialId;
    const file = req.file;

    if (file) {
      const ext = path.extname(file.originalname).toLowerCase();
      const isPdf = ext === '.pdf' || file.mimetype === 'application/pdf';
      if (!isPdf) {
        return res.status(400).json({ detail: 'Only PDF files are permitted for protocol extraction.' });
      }

      const rawName = file.originalname;
      const filename = path.basename(rawName).replace(/[^a-zA-Z0-9._-]/g, '_');
      const fileSize = file.size;

      let extractedTrial: ProtocolExtractionResponse;
      try {
        extractedTrial = await extractProtocolFromPdfBuffer(file.buffer, filename, trialId);
      } catch (err: any) {
        extractedTrial = {
          trial_id: trialId,
          trial_title: filename.replace(/\.[^/.]+$/, '').replace(/_/g, ' '),
          trial_identifier: null,
          inclusion_criteria: [],
          exclusion_criteria: [],
          other_requirements: [],
          processing_status: 'validation_failed',
          total_pages_analyzed: 0,
          error_message: `Extraction error: ${err?.message || 'Failed to parse protocol'}`,
        };
      }

      dataStore.saveTrial(extractedTrial, filename, fileSize);

      return res.json({
        trial_id: trialId,
        protocol_id: extractedTrial.trial_identifier || trialId,
        title: extractedTrial.trial_title,
        trial_title: extractedTrial.trial_title,
        trial_identifier: extractedTrial.trial_identifier || trialId,
        inclusion_criteria: extractedTrial.inclusion_criteria,
        exclusion_criteria: extractedTrial.exclusion_criteria,
        other_requirements: extractedTrial.other_requirements,
        source_document: filename,
        processing_status: extractedTrial.processing_status,
        total_pages_analyzed: extractedTrial.total_pages_analyzed,
        extraction_metadata: {
          extracted_at: new Date().toISOString(),
          total_pages: extractedTrial.total_pages_analyzed,
          model: process.env.XAI_MODEL || (process.env.LLM_PROVIDER === 'gemini' ? (process.env.GEMINI_MODEL || 'gemini-3.8-flash') : 'grok-2-latest'),
          inclusion_count: extractedTrial.inclusion_criteria.length,
          exclusion_count: extractedTrial.exclusion_criteria.length,
          other_count: extractedTrial.other_requirements.length,
        },
        error_message: extractedTrial.error_message || null,
      });
    }

    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }
    res.json(trial);
  });

  // --------------------------------------------------------------------------
  // RAG / VECTOR SEARCH (MODULE 3)
  // --------------------------------------------------------------------------
  app.get('/api/v1/trials/:trialId/rag/status', (req, res) => {
    const trialId = req.params.trialId;
    const isIndexed = dataStore.isIndexed(trialId);
    res.json({
      trial_id: trialId,
      is_indexed: isIndexed,
    });
  });

  app.post('/api/v1/trials/:trialId/rag/index', (req, res) => {
    const trialId = req.params.trialId;
    const result = dataStore.indexTrial(trialId);
    res.json(result);
  });

  app.post('/api/v1/trials/:trialId/rag/search', (req, res) => {
    const trialId = req.params.trialId;
    const query = req.body?.query || '';
    const topK = req.body?.top_k || 5;

    const results = dataStore.searchRAG(trialId, query, topK);
    res.json({
      trial_id: trialId,
      query,
      results,
    });
  });

  // --------------------------------------------------------------------------
  // PATIENT PROFILES (MODULE 4)
  // --------------------------------------------------------------------------
  app.get('/api/v1/patients', (_req, res) => {
    const patients = dataStore.getPatients();
    res.json(patients);
  });

  app.get('/api/v1/patients/:patientProfileId', (req, res) => {
    const pid = req.params.patientProfileId;
    const patient = dataStore.getPatient(pid);
    if (!patient) {
      return res.status(404).json({ detail: `Patient profile '${pid}' not found.` });
    }
    res.json(patient);
  });

  app.post('/api/v1/patients/profile', (req, res) => {
    const body = req.body || {};
    const profile =
      body.demographics && Array.isArray(body.conditions) && body.patient_profile_id
        ? (body as StructuredPatientProfile)
        : buildStructuredProfile({
            patient_profile_id: body.patient_profile_id,
            age: body.age ?? body.demographics?.age,
            sex: body.sex ?? body.demographics?.sex,
            height: body.height ?? body.demographics?.height,
            weight: body.weight ?? body.demographics?.weight,
            pregnancy_status: body.demographics?.pregnancy_status ?? body.pregnancy_status,
            breastfeeding_status: body.demographics?.breastfeeding_status ?? body.breastfeeding_status,
            demographics: body.demographics,
            conditions: body.conditions,
            medical_history: body.medical_history,
            medications: body.medications,
            lab_values: body.lab_values,
            allergies: body.allergies,
            vital_signs: body.vital_signs,
            clinical_notes_raw: body.clinical_notes_raw,
            metadata: body.metadata,
          });

    if (profile.demographics) {
      if (body.demographics?.pregnancy_status !== undefined && body.demographics?.pregnancy_status !== null) {
        profile.demographics.pregnancy_status = String(body.demographics.pregnancy_status).trim().toLowerCase();
      } else if (body.pregnancy_status !== undefined && body.pregnancy_status !== null) {
        profile.demographics.pregnancy_status = String(body.pregnancy_status).trim().toLowerCase();
      }

      if (body.demographics?.breastfeeding_status !== undefined && body.demographics?.breastfeeding_status !== null) {
        profile.demographics.breastfeeding_status =
          typeof body.demographics.breastfeeding_status === 'boolean'
            ? body.demographics.breastfeeding_status
            : ['false', 'no', '0', 'none', 'negative', 'denies'].includes(String(body.demographics.breastfeeding_status).toLowerCase())
            ? false
            : true;
      } else if (body.breastfeeding_status !== undefined && body.breastfeeding_status !== null) {
        profile.demographics.breastfeeding_status =
          typeof body.breastfeeding_status === 'boolean'
            ? body.breastfeeding_status
            : ['false', 'no', '0', 'none', 'negative', 'denies'].includes(String(body.breastfeeding_status).toLowerCase())
            ? false
            : true;
      }
    }

    dataStore.savePatient(profile);
    res.json(profile);
  });

  // Patient Document Upload & Extraction (PDF & JSON)
  app.post('/api/v1/patients/extract-document', upload.single('file') as any, async (req, res) => {
    const file = req.file;

    // Check if JSON body provided directly without multipart file
    if (!file) {
      if (req.body && typeof req.body === 'object' && Object.keys(req.body).length > 0) {
        try {
          const result = extractPatientFromJson(req.body, 'uploaded_record.json');
          return res.json(result);
        } catch (err: any) {
          return res.status(400).json({ detail: err.message || 'Invalid JSON patient record.' });
        }
      }
      return res.status(400).json({ detail: 'Please upload a PDF or JSON patient record.' });
    }

    const rawName = file.originalname || 'document';
    const ext = path.extname(rawName).toLowerCase();
    const mime = (file.mimetype || '').toLowerCase();
    const isPdf = ext === '.pdf' || mime === 'application/pdf';
    const isJson = ext === '.json' || mime === 'application/json' || mime === 'text/json';

    if (!isPdf && !isJson) {
      return res.status(400).json({ detail: 'Please upload a PDF or JSON patient record.' });
    }

    try {
      if (isPdf) {
        const result = await extractPatientFromPdfBuffer(file.buffer, rawName);
        console.log(`[AUDIT] Processed patient PDF upload (filename: ${path.basename(rawName)}, size: ${file.size} bytes)`);
        return res.json(result);
      } else {
        const text = file.buffer.toString('utf8');
        const result = extractPatientFromJson(text, rawName);
        console.log(`[AUDIT] Processed patient JSON upload (filename: ${path.basename(rawName)}, size: ${file.size} bytes)`);
        return res.json(result);
      }
    } catch (err: any) {
      return res.status(400).json({
        detail:
          err.message ||
          'Could not extract patient information from this document. Please verify that the document contains readable patient information or enter the profile manually.',
      });
    }
  });

  // --------------------------------------------------------------------------
  // INCLUSION MATCHING EVALUATION (MODULE 5)
  // --------------------------------------------------------------------------
  const evaluateInclusionHandler = (req: express.Request, res: express.Response) => {
    const trialId = req.params.trialId;
    const patientProfileId = req.params.patientProfileId;

    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }

    const patient = dataStore.getPatient(patientProfileId);
    if (!patient) {
      return res.status(404).json({ detail: `Patient profile with ID '${patientProfileId}' not found.` });
    }

    const result = evaluateAllInclusionCriteria(
      trialId,
      patientProfileId,
      trial.inclusion_criteria || [],
      patient
    );
    res.json(result);
  };

  app.post('/api/v1/trials/:trialId/patients/:patientProfileId/inclusion-evaluation', evaluateInclusionHandler);
  app.post('/api/v1/eligibility/inclusion/:trialId/:patientProfileId', evaluateInclusionHandler);

  // --------------------------------------------------------------------------
  // EXCLUSION DETECTION EVALUATION (MODULE 6)
  // --------------------------------------------------------------------------
  const evaluateExclusionHandler = (req: express.Request, res: express.Response) => {
    const trialId = req.params.trialId;
    const patientProfileId = req.params.patientProfileId;

    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }

    const patient = dataStore.getPatient(patientProfileId);
    if (!patient) {
      return res.status(404).json({ detail: `Patient profile with ID '${patientProfileId}' not found.` });
    }

    const result = evaluateAllExclusionCriteria(
      trialId,
      patientProfileId,
      trial.exclusion_criteria || [],
      patient
    );
    res.json(result);
  };

  app.post('/api/v1/trials/:trialId/patients/:patientProfileId/exclusion-evaluation', evaluateExclusionHandler);
  app.post('/api/v1/eligibility/exclusion/:trialId/:patientProfileId', evaluateExclusionHandler);

  // --------------------------------------------------------------------------
  // CONTRADICTION & SILENT EXCLUSION EVALUATION (MODULE 7)
  // --------------------------------------------------------------------------
  const contradictionHandler = (req: express.Request, res: express.Response) => {
    const trialId = req.params.trialId;
    const patientProfileId = req.params.patientProfileId;

    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }

    const patient = dataStore.getPatient(patientProfileId);
    if (!patient) {
      return res.status(404).json({ detail: `Patient profile with ID '${patientProfileId}' not found.` });
    }

    const incResults = evaluateAllInclusionCriteria(
      trialId,
      patientProfileId,
      trial.inclusion_criteria || [],
      patient
    ).criteria_results;

    const excResults = evaluateAllExclusionCriteria(
      trialId,
      patientProfileId,
      trial.exclusion_criteria || [],
      patient
    ).criteria_results;

    const result = evaluateContradictions(
      trialId,
      patientProfileId,
      patient,
      trial,
      incResults,
      excResults
    );
    res.json(result);
  };

  app.post('/api/v1/trials/:trialId/patients/:patientProfileId/contradiction-evaluation', contradictionHandler);
  app.post('/api/v1/eligibility/contradiction/:trialId/:patientProfileId', contradictionHandler);

  // --------------------------------------------------------------------------
  // DECISION / REVIEWER AGENT EVALUATION (MODULE 8)
  // --------------------------------------------------------------------------
  const finalEvaluationHandler = (req: express.Request, res: express.Response) => {
    const trialId = req.params.trialId;
    const patientProfileId = req.params.patientProfileId;

    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      return res.status(404).json({ detail: `Trial with ID '${trialId}' not found.` });
    }

    const patient = dataStore.getPatient(patientProfileId);
    if (!patient) {
      return res.status(404).json({ detail: `Patient profile with ID '${patientProfileId}' not found.` });
    }

    const inclusionResp = evaluateAllInclusionCriteria(
      trialId,
      patientProfileId,
      trial.inclusion_criteria || [],
      patient
    );

    const exclusionResp = evaluateAllExclusionCriteria(
      trialId,
      patientProfileId,
      trial.exclusion_criteria || [],
      patient
    );

    const contradictionResp = evaluateContradictions(
      trialId,
      patientProfileId,
      patient,
      trial,
      inclusionResp.criteria_results,
      exclusionResp.criteria_results
    );

    const finalResult = evaluateFinalEligibility(
      trialId,
      patientProfileId,
      inclusionResp,
      exclusionResp,
      contradictionResp,
      patient,
      trial
    );

    // Structured Audit Logging (Module 9 - Part H)
    console.log(
      `[AUDIT] Trial=${trialId} Patient=${patientProfileId} Decision=${finalResult.final_decision} Timestamp=${finalResult.evaluated_at}`
    );

    res.json(finalResult);
  };

  app.post('/api/v1/trials/:trialId/patients/:patientProfileId/final-evaluation', finalEvaluationHandler);
  app.post('/api/v1/trials/:trialId/patients/:patientProfileId/workflow-evaluation', finalEvaluationHandler);
  app.post('/api/v1/eligibility/final/:trialId/:patientProfileId', finalEvaluationHandler);

  // --------------------------------------------------------------------------
  // LANGGRAPH WORKFLOW ENGINE EVALUATION ENDPOINT (/api/v1/workflow/evaluate)
  // --------------------------------------------------------------------------
  const runWorkflowEvaluationLogic = (
    trialId: string,
    rawPatient: any,
    referenceDate?: string | null
  ) => {
    const trial = dataStore.getTrial(trialId);
    if (!trial) {
      throw new Error(`Trial with ID '${trialId}' not found.`);
    }

    const patientProfileId = rawPatient?.patient_profile_id || 'PATIENT-001';
    let patient = dataStore.getPatient(patientProfileId);

    if (!patient && rawPatient) {
      const demographics = rawPatient.demographics || {};
      const clinicalStatus = rawPatient.clinical_status || {};
      const treatmentHistory = rawPatient.treatment_history || {};
      const labs = rawPatient.labs || {};

      const lab_values: any[] = [];
      const addLab = (name: string, lab: any) => {
        if (lab && lab.value != null) {
          lab_values.push({
            name,
            normalized_name: name.toLowerCase(),
            value: lab.value,
            unit: lab.unit || null,
            reference_range: lab.reference_range || null,
            source: 'patient_json',
          });
        }
      };

      addLab('eGFR', labs.egfr);
      addLab('ANC', labs.anc);
      addLab('Platelets', labs.platelets);
      addLab('Hemoglobin', labs.hemoglobin);
      addLab('AST', labs.ast);
      addLab('ALT', labs.alt);
      addLab('Bilirubin', labs.bilirubin);
      if (labs.other_labs) {
        for (const [k, v] of Object.entries(labs.other_labs)) {
          addLab(k, v);
        }
      }

      patient = {
        patient_profile_id: patientProfileId,
        profile_status: 'complete',
        created_at: new Date().toISOString(),
        demographics: {
          age: demographics.age ?? null,
          sex: demographics.sex ?? null,
          pregnancy_status: demographics.pregnancy_status ?? null,
          breastfeeding_status: demographics.breastfeeding_status ?? null,
          height: demographics.height_cm ?? demographics.height ?? null,
          weight: demographics.weight_kg ?? demographics.weight ?? null,
        },
        conditions: (rawPatient.conditions || []).map((c: any) => ({
          name: c.name,
          normalized_name: c.name?.toLowerCase?.() || c.name,
          status: c.status || 'active',
          source: c.source_provenance || 'patient_json',
        })),
        medical_history: [],
        medications: (rawPatient.medications || []).map((m: any) => ({
          name: m.name,
          normalized_name: m.name?.toLowerCase?.() || m.name,
          dose: m.dose || null,
          frequency: m.frequency || null,
          is_current: m.status === 'active' || m.status === 'current',
          source: 'patient_json',
        })),
        lab_values,
        allergies: (rawPatient.allergies || []).map((a: any) => ({
          allergen: a.substance || a.allergen || 'Unknown',
          normalized_allergen: (a.substance || a.allergen || 'unknown').toLowerCase(),
          severity: a.severity || null,
          source: 'patient_json',
        })),
        vital_signs: rawPatient.vital_signs
          ? {
              systolic_bp: rawPatient.vital_signs.blood_pressure?.systolic ?? null,
              diastolic_bp: rawPatient.vital_signs.blood_pressure?.diastolic ?? null,
              heart_rate: rawPatient.vital_signs.heart_rate ?? null,
              unit: rawPatient.vital_signs.blood_pressure?.unit || 'mmHg',
            }
          : null,
        missing_information: [],
        clinical_status: {
          ecog_performance_status: clinicalStatus.ecog_performance_status ?? null,
          active_serious_infection: clinicalStatus.active_serious_infection ?? null,
          uncontrolled_cardiac_disease: clinicalStatus.uncontrolled_cardiac_disease ?? null,
        },
        treatment_history: {
          recent_systemic_anticancer_therapy:
            treatmentHistory.recent_systemic_anticancer_therapy ?? null,
          prior_therapies: treatmentHistory.prior_therapies || [],
          last_treatment_date: treatmentHistory.last_treatment_date || null,
        },
        metadata: {
          ecog_score: clinicalStatus.ecog_performance_status ?? null,
          active_serious_infection: clinicalStatus.active_serious_infection ?? null,
          uncontrolled_cardiac_disease: clinicalStatus.uncontrolled_cardiac_disease ?? null,
          recent_systemic_anticancer_therapy:
            treatmentHistory.recent_systemic_anticancer_therapy ?? null,
        },
      };
    }

    if (!patient) {
      throw new Error(`Patient profile '${patientProfileId}' not found.`);
    }

    const inclusionResp = evaluateAllInclusionCriteria(
      trialId,
      patient.patient_profile_id,
      trial.inclusion_criteria || [],
      patient
    );

    const exclusionResp = evaluateAllExclusionCriteria(
      trialId,
      patient.patient_profile_id,
      trial.exclusion_criteria || [],
      patient
    );

    const contradictionResp = evaluateContradictions(
      trialId,
      patient.patient_profile_id,
      patient,
      trial,
      inclusionResp.criteria_results,
      exclusionResp.criteria_results
    );

    const finalResult = evaluateFinalEligibility(
      trialId,
      patient.patient_profile_id,
      inclusionResp,
      exclusionResp,
      contradictionResp,
      patient,
      trial
    );

    const assessmentId = `ASM-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`;

    const findings = [
      ...contradictionResp.contradictions.map((c, i) => ({
        finding_id: c.contradiction_id || `CONTRADICTION-${i + 1}`,
        trial_id: trialId,
        contradiction_type: 'CLINICAL_CONTRADICTION' as const,
        severity: (c.severity === 'critical' ? 'CRITICAL' : c.severity === 'high' ? 'WARNING' : 'INFO') as any,
        title: c.title,
        description: c.description,
        criterion_ids: [] as string[],
        patient_fields: (c.patient_evidence || []).map((e: any) => e.field),
        evidence: c.patient_evidence,
        recommended_action: c.suggested_reconciliation || c.clinical_risk_rationale || '',
      })),
      ...contradictionResp.silent_exclusions.map((s, i) => ({
        finding_id: s.trigger_id || `SILENT-${i + 1}`,
        trial_id: trialId,
        contradiction_type: 'SILENT_EXCLUSION' as const,
        severity: 'CRITICAL' as const,
        title: s.name,
        description: s.clinical_rationale,
        criterion_ids: [] as string[],
        patient_fields: s.patient_evidence ? [s.patient_evidence.field] : [],
        evidence: s.patient_evidence,
        recommended_action: 'Perform clinical verification for silent exclusion.',
      })),
    ];

    const decisionEvidence = finalResult.decision_factors.map((f, i) => ({
      criterion_id: f.criterion_id || `DEC-CRIT-${i + 1}`,
      criterion_text: f.criterion_text || f.reason,
      patient_value: f.patient_value,
      status:
        f.status === 'satisfied'
          ? 'PASS'
          : f.status === 'unsatisfied'
          ? 'FAIL'
          : f.status === 'triggered'
          ? 'TRIGGERED'
          : f.status === 'not_triggered'
          ? 'CLEAR'
          : f.status === 'critical_conflict'
          ? 'FAIL'
          : f.status === 'silent_exclusion'
          ? 'SILENT_EXCLUSION'
          : 'UNKNOWN',
      source_page: f.protocol_page || (f.type === 'exclusion' ? 2 : 1),
      source_document: `${trial.trial_title || trialId}.pdf`,
      source_excerpt: f.protocol_evidence?.text || f.reason,
      originating_agent:
        f.type === 'inclusion'
          ? 'InclusionMatchingAgent'
          : f.type === 'exclusion'
          ? 'ExclusionDetectionAgent'
          : f.type === 'silent_exclusion'
          ? 'ContradictionAgent'
          : 'DecisionReviewer',
    }));

    const workflowState = {
      assessment_id: assessmentId,
      trial_id: trialId,
      patient_profile_id: patient.patient_profile_id,
      protocol_evidence: (dataStore.searchRAG(trialId, 'clinical trial eligibility criteria', 10) || []).map((c, i) => ({
        chunk_id: c.chunk_id,
        trial_id: trialId,
        criterion_id: `CHUNK-${i + 1}`,
        criterion_type: c.criterion_type || 'criterion',
        text: c.text,
        score: c.similarity_score,
        source_page: c.page_number || 1,
        source_document: `${trial.trial_title || trialId}.pdf`,
        source_excerpt: c.text,
      })),
      inclusion_assessment: {
        trial_id: trialId,
        patient_profile_id: patient.patient_profile_id,
        overall_status:
          inclusionResp.overall_inclusion_status === 'satisfied'
            ? ('MET' as const)
            : inclusionResp.overall_inclusion_status === 'unsatisfied'
            ? ('NOT_MET' as const)
            : ('UNKNOWN' as const),
        criteria: inclusionResp.criteria_results.map((c) => ({
          criterion_id: c.criterion_id,
          trial_id: trialId,
          status:
            c.result === 'satisfied'
              ? ('PASS' as const)
              : c.result === 'unsatisfied'
              ? ('FAIL' as const)
              : ('UNKNOWN' as const),
          criterion_text: c.criterion_text,
          patient_value: c.patient_evidence?.value,
          expected_requirement: c.reason,
          rationale: c.reason,
          evidence: c.patient_evidence ? { [c.patient_evidence.field]: c.patient_evidence.value } : null,
          source_page: c.protocol_evidence?.source_page || 1,
          source_document: `${trial.trial_title || trialId}.pdf`,
          source_excerpt: c.protocol_evidence?.text || c.criterion_text,
        })),
        missing_information: inclusionResp.criteria_results.flatMap((c) => c.missing_information || []),
        warnings: [] as string[],
      },
      exclusion_assessment: {
        trial_id: trialId,
        patient_profile_id: patient.patient_profile_id,
        overall_status:
          exclusionResp.overall_exclusion_status === 'triggered'
            ? ('EXCLUDED' as const)
            : exclusionResp.overall_exclusion_status === 'not_triggered'
            ? ('NOT_EXCLUDED' as const)
            : ('UNKNOWN' as const),
        criteria: exclusionResp.criteria_results.map((c) => ({
          criterion_id: c.criterion_id,
          trial_id: trialId,
          status:
            c.result === 'triggered'
              ? ('TRIGGERED' as const)
              : c.result === 'not_triggered'
              ? ('CLEAR' as const)
              : ('UNKNOWN' as const),
          criterion_text: c.criterion_text,
          patient_value: c.patient_evidence?.value,
          exclusion_requirement: c.reason,
          rationale: c.reason,
          evidence: c.patient_evidence ? { [c.patient_evidence.field]: c.patient_evidence.value } : null,
          source_page: c.protocol_evidence?.source_page || 2,
          source_document: `${trial.trial_title || trialId}.pdf`,
          source_excerpt: c.protocol_evidence?.text || c.criterion_text,
        })),
        missing_information: exclusionResp.criteria_results.flatMap((c) => c.missing_information || []),
        warnings: [] as string[],
      },
      contradiction_assessment: {
        trial_id: trialId,
        patient_profile_id: patient.patient_profile_id,
        findings,
        checked_criteria: [] as string[],
        warnings: [] as string[],
        has_critical_findings:
          contradictionResp.has_critical_conflicts || contradictionResp.has_silent_exclusions,
      },
      decision_assessment: {
        trial_id: trialId,
        patient_profile_id: patient.patient_profile_id,
        final_status: finalResult.final_decision,
        requires_human_review: finalResult.final_decision !== 'ELIGIBLE',
        primary_reasons: [finalResult.explanation],
        decision_evidence: decisionEvidence,
        unresolved_information: finalResult.missing_information || [],
        contradiction_findings: findings,
        warnings: [] as string[],
        disclaimer:
          'This evaluation is an automated decision-support suggestion and does not substitute for independent clinical judgment.',
      },
      warnings: [] as string[],
      errors: [] as string[],
      current_step: 'END',
    };

    dataStore.saveAssessment({
      assessment_id: assessmentId,
      trial_id: trialId,
      patient_profile_id: patient.patient_profile_id,
      reference_date: referenceDate || new Date().toISOString(),
      workflow_status: 'COMPLETED',
      final_decision: finalResult.final_decision,
      current_step: 'END',
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      has_errors: false,
      error_count: 0,
      warning_count: 0,
      warnings: [],
      errors: [],
      snapshot: workflowState,
      traces: [
        {
          sequence: 1,
          stage: 'inclusion_matching',
          status: 'completed',
          payload: workflowState.inclusion_assessment,
          created_at: new Date().toISOString(),
        },
        {
          sequence: 2,
          stage: 'exclusion_detection',
          status: 'completed',
          payload: workflowState.exclusion_assessment,
          created_at: new Date().toISOString(),
        },
        {
          sequence: 3,
          stage: 'contradiction_detection',
          status: 'completed',
          payload: workflowState.contradiction_assessment,
          created_at: new Date().toISOString(),
        },
        {
          sequence: 4,
          stage: 'decision_reviewer',
          status: 'completed',
          payload: workflowState.decision_assessment,
          created_at: new Date().toISOString(),
        },
      ],
    });

    console.log(
      `[WORKFLOW AUDIT] Trial=${trialId} Patient=${patient.patient_profile_id} AssessmentId=${assessmentId} Decision=${finalResult.final_decision}`
    );

    return workflowState;
  };

  app.post('/api/v1/workflow/evaluate', (req, res) => {
    try {
      const trialId = req.body.trial_id;
      const patientProfile = req.body.patient_profile;
      const referenceDate = req.body.reference_date;

      if (!trialId) {
        return res.status(400).json({ detail: 'trial_id is required' });
      }

      const workflowState = runWorkflowEvaluationLogic(trialId, patientProfile, referenceDate);
      res.json(workflowState);
    } catch (err: any) {
      console.error('[WORKFLOW EVALUATION ERROR]', err?.message || err);
      res.status(err?.status || 400).json({ detail: err?.message || 'Workflow evaluation failed' });
    }
  });

  // --------------------------------------------------------------------------
  // PERSISTED ASSESSMENT AUDIT HISTORY (MODULE 10)
  // --------------------------------------------------------------------------
  app.get('/api/v1/assessments', (req, res) => {
    const trial_id = req.query.trial_id as string | undefined;
    const patient_profile_id = req.query.patient_profile_id as string | undefined;
    const limit = req.query.limit ? parseInt(req.query.limit as string, 10) : 50;
    const offset = req.query.offset ? parseInt(req.query.offset as string, 10) : 0;
    const assessments = dataStore.getAssessments({ trial_id, patient_profile_id, limit, offset });
    res.json(assessments);
  });

  app.get('/api/v1/assessments/:assessmentId', (req, res) => {
    const assessment = dataStore.getAssessment(req.params.assessmentId);
    if (!assessment) {
      return res.status(404).json({ detail: `Assessment '${req.params.assessmentId}' not found.` });
    }
    res.json(assessment);
  });

  // Pre-seed sample assessments if store is currently empty
  try {
    const defaultTrial = dataStore.getTrials()[0]?.trial_id;
    const defaultPatient = dataStore.getPatients()[0];
    if (defaultTrial && defaultPatient) {
      runWorkflowEvaluationLogic(defaultTrial, defaultPatient);
    }
  } catch (err) {
    // Non-fatal if seeding fails
  }

  app.post('/api/v1/eligibility/evaluate', (req, res) => {
    const trialId = req.body.trial_id;
    const patientProfileId = req.body.patient_id || req.body.patient_profile_id;
    if (!trialId || !patientProfileId) {
      return res.status(400).json({ error: 'trial_id and patient_id are required' });
    }
    // Re-route to final evaluation handler
    (req.params as any).trialId = trialId;
    (req.params as any).patientProfileId = patientProfileId;
    return finalEvaluationHandler(req, res);
  });

  // --------------------------------------------------------------------------
  // GLOBAL ERROR HANDLER (MODULE 9 - PART F)
  // --------------------------------------------------------------------------
  app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error('[SERVER ERROR]', err?.message || err);
    res.status(err.status || 500).json({
      detail: err.message || 'An unexpected internal server error occurred.',
    });
  });

  // --------------------------------------------------------------------------
  // VITE MIDDLEWARE (DEV) & STATIC FILES (PROD)
  // --------------------------------------------------------------------------
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
