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

  app.post('/api/v1/trials/:trialId/extract-protocol', (req, res) => {
    const trialId = req.params.trialId;
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
