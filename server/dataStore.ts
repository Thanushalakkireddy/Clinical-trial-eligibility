import fs from 'fs';
import path from 'path';
import {
  ProtocolExtractionResponse,
  StructuredPatientProfile,
  RAGChunk,
  RAGSearchResult,
  ExtractedCriterion,
} from './types';
import { buildStructuredProfile } from './normalization';

export interface AssessmentSummary {
  assessment_id: string;
  trial_id: string;
  patient_profile_id: string;
  reference_date?: string | null;
  workflow_status: string;
  final_decision?: 'ELIGIBLE' | 'NOT_ELIGIBLE' | 'MORE_INFORMATION_REQUIRED' | null;
  current_step?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  has_errors: boolean;
  error_count: number;
  warning_count: number;
}

export interface AssessmentTrace {
  sequence: number;
  stage: string;
  status?: string | null;
  payload?: Record<string, any> | null;
  created_at?: string | null;
}

export interface AssessmentDetail extends AssessmentSummary {
  warnings: string[];
  errors: string[];
  snapshot?: Record<string, any> | null;
  traces: AssessmentTrace[];
}

export class DataStore {
  private trials: Map<string, ProtocolExtractionResponse> = new Map();
  private trialFiles: Map<string, { filename: string; size: number; uploadDate: string }> = new Map();
  private patients: Map<string, StructuredPatientProfile> = new Map();
  private chunks: Map<string, RAGChunk[]> = new Map();
  private indexedTrials: Set<string> = new Set();
  private assessments: Map<string, AssessmentDetail> = new Map();

  constructor() {
    this.loadFromDisk();
  }

  public clearAll(): void {
    this.trials.clear();
    this.trialFiles.clear();
    this.patients.clear();
    this.chunks.clear();
    this.indexedTrials.clear();
    this.assessments.clear();
  }

  public reloadFromDisk(): void {
    this.clearAll();
    this.loadFromDisk();
  }

  /**
   * For automated test suites only. NEVER called during normal application startup.
   */
  public seedTestFixtures(fixtures?: { trials?: ProtocolExtractionResponse[]; patients?: StructuredPatientProfile[] }): void {
    if (fixtures?.trials) {
      for (const t of fixtures.trials) {
        this.trials.set(t.trial_id, t);
        this.indexTrial(t.trial_id);
      }
    }
    if (fixtures?.patients) {
      for (const p of fixtures.patients) {
        this.patients.set(p.patient_profile_id, p);
      }
    }
  }

  private loadFromDisk() {
    const cwd = process.cwd();

    // 1. Scan patient profiles
    const patientDirs = [
      path.join(cwd, 'data', 'patients'),
      path.join(cwd, 'backend', 'data', 'patients'),
    ];

    for (const pDir of patientDirs) {
      if (fs.existsSync(pDir)) {
        try {
          const files = fs.readdirSync(pDir);
          for (const f of files) {
            if (f.endsWith('.json')) {
              try {
                const fullPath = path.join(pDir, f);
                const raw = fs.readFileSync(fullPath, 'utf8');
                const profile = JSON.parse(raw);
                if (profile && profile.patient_profile_id) {
                  this.patients.set(profile.patient_profile_id, profile);
                }
              } catch (e) {
                // ignore corrupted file
              }
            }
          }
        } catch {
          // ignore directory error
        }
      }
    }

    // 2. Scan protocols
    const protocolDirs = [
      path.join(cwd, 'storage', 'pdfs'),
      path.join(cwd, 'backend', 'data', 'uploads'),
    ];

    for (const pDir of protocolDirs) {
      if (fs.existsSync(pDir)) {
        try {
          const files = fs.readdirSync(pDir);
          for (const f of files) {
            if (f.endsWith('_protocol.json') || (f.endsWith('.json') && !f.includes('metadata'))) {
              try {
                const fullPath = path.join(pDir, f);
                const raw = fs.readFileSync(fullPath, 'utf8');
                const proto: ProtocolExtractionResponse = JSON.parse(raw);
                if (proto && proto.trial_id) {
                  const existing = this.trials.get(proto.trial_id);
                  const hasCriteria = Array.isArray(proto.inclusion_criteria) && proto.inclusion_criteria.length > 0;
                  if (!existing || (!existing.inclusion_criteria?.length && hasCriteria)) {
                    proto.inclusion_criteria = Array.isArray(proto.inclusion_criteria) ? proto.inclusion_criteria : [];
                    proto.exclusion_criteria = Array.isArray(proto.exclusion_criteria) ? proto.exclusion_criteria : [];
                    proto.other_requirements = Array.isArray(proto.other_requirements) ? proto.other_requirements : [];
                    this.trials.set(proto.trial_id, proto);
                  }
                  this.trialFiles.set(proto.trial_id, {
                    filename: (proto as any).original_filename || `${proto.trial_title || proto.trial_id}.pdf`,
                    size: (proto as any).size_bytes || 102400,
                    uploadDate: (proto as any).uploaded_at || new Date().toISOString(),
                  });
                }
              } catch {
                // ignore
              }
            }
          }
        } catch {
          // ignore
        }
      }
    }

    // 3. Scan chunk metadata for vector search
    const vectorDirs = [
      path.join(cwd, 'storage', 'faiss'),
      path.join(cwd, 'backend', 'data', 'vector_store'),
    ];

    for (const vDir of vectorDirs) {
      if (fs.existsSync(vDir)) {
        try {
          const files = fs.readdirSync(vDir);
          for (const f of files) {
            if (f.endsWith('_metadata.json')) {
              try {
                const trialId = f.replace('_metadata.json', '');
                const raw = fs.readFileSync(path.join(vDir, f), 'utf8');
                const data = JSON.parse(raw);
                const chunkList: RAGChunk[] = [];
                for (const key of Object.keys(data)) {
                  const item = data[key];
                  if (item && item.text) {
                    chunkList.push({
                      chunk_id: item.chunk_id || `${trialId}_c_${key}`,
                      trial_id: item.trial_id || trialId,
                      text: item.text,
                      page_number: item.page_number || 1,
                      section: item.section || null,
                      criterion_type: item.criterion_type || null,
                    });
                  }
                }
                if (chunkList.length > 0) {
                  this.chunks.set(trialId, chunkList);
                  this.indexedTrials.add(trialId);
                }
              } catch {
                // ignore
              }
            }
          }
        } catch {
          // ignore
        }
      }
    }

    // Ensure all seeded trials have chunks
    for (const [tid, trial] of this.trials.entries()) {
      if (!this.chunks.has(tid)) {
        const generatedChunks: RAGChunk[] = [];
        let cIndex = 0;

        generatedChunks.push({
          chunk_id: `${tid}_title`,
          trial_id: tid,
          text: `Title: ${trial.trial_title}\nIdentifier: ${trial.trial_identifier || 'N/A'}\nPages: ${trial.total_pages_analyzed || 1}`,
          page_number: 1,
          section: 'Protocol Header',
          criterion_type: 'general',
        });

        const incCriteria = Array.isArray(trial.inclusion_criteria) ? trial.inclusion_criteria : [];
        for (const inc of incCriteria) {
          generatedChunks.push({
            chunk_id: `${tid}_inc_${cIndex++}`,
            trial_id: tid,
            text: `Inclusion Criterion [${inc.criterion_id}]: ${inc.text}`,
            page_number: inc.source_page || 1,
            section: 'Inclusion Criteria',
            criterion_type: 'inclusion',
          });
        }

        const excCriteria = Array.isArray(trial.exclusion_criteria) ? trial.exclusion_criteria : [];
        for (const exc of excCriteria) {
          generatedChunks.push({
            chunk_id: `${tid}_exc_${cIndex++}`,
            trial_id: tid,
            text: `Exclusion Criterion [${exc.criterion_id}]: ${exc.text}`,
            page_number: exc.source_page || 2,
            section: 'Exclusion Criteria',
            criterion_type: 'exclusion',
          });
        }

        const otherReqs = Array.isArray(trial.other_requirements) ? trial.other_requirements : [];
        for (const other of otherReqs) {
          generatedChunks.push({
            chunk_id: `${tid}_other_${cIndex++}`,
            trial_id: tid,
            text: `Other Requirement: ${other}`,
            page_number: 1,
            section: 'General Requirements',
            criterion_type: 'general',
          });
        }

        this.chunks.set(tid, generatedChunks);
        this.indexedTrials.add(tid);
      }
    }
  }

  public getTrials(): Array<{
    trial_id: string;
    filename: string;
    status: string;
    file_size_bytes?: number;
    upload_date?: string;
  }> {
    const list: Array<{
      trial_id: string;
      filename: string;
      status: string;
      file_size_bytes?: number;
      upload_date?: string;
    }> = [];

    for (const [id, meta] of this.trialFiles.entries()) {
      list.push({
        trial_id: id,
        filename: meta.filename,
        status: 'processed',
        file_size_bytes: meta.size,
        upload_date: meta.uploadDate,
      });
    }

    return list;
  }

  public getTrial(trialId: string): ProtocolExtractionResponse | null {
    let trial = this.trials.get(trialId);
    if (!trial) {
      // Check prefix/suffix alias (e.g. trial_mu1pv9rf_6qkd3j vs trial_mu1pv9rf_6qkd3)
      for (const [id, t] of this.trials.entries()) {
        if (id.startsWith(trialId) || trialId.startsWith(id)) {
          trial = t;
          break;
        }
      }
    }
    if (!trial) return null;
    if (!Array.isArray(trial.inclusion_criteria)) trial.inclusion_criteria = [];
    if (!Array.isArray(trial.exclusion_criteria)) trial.exclusion_criteria = [];
    if (!Array.isArray(trial.other_requirements)) trial.other_requirements = [];
    return trial;
  }

  public saveTrial(trial: ProtocolExtractionResponse, filename?: string, size?: number): void {
    this.trials.set(trial.trial_id, trial);
    this.trialFiles.set(trial.trial_id, {
      filename: filename || `${trial.trial_title || trial.trial_id}.pdf`,
      size: size || 102400,
      uploadDate: new Date().toISOString(),
    });

    // Durable disk persistence to storage/pdfs
    try {
      const storageDir = path.join(process.cwd(), 'storage', 'pdfs');
      if (!fs.existsSync(storageDir)) {
        fs.mkdirSync(storageDir, { recursive: true });
      }
      fs.writeFileSync(
        path.join(storageDir, `${trial.trial_id}_protocol.json`),
        JSON.stringify(trial, null, 2),
        'utf8'
      );
    } catch {
      // ignore persistence error
    }

    // Auto generate chunks and index
    this.indexTrial(trial.trial_id);
  }

  public getPatients(): StructuredPatientProfile[] {
    return Array.from(this.patients.values());
  }

  public getPatient(patientId: string): StructuredPatientProfile | null {
    return this.patients.get(patientId) || null;
  }

  public savePatient(profile: StructuredPatientProfile): void {
    this.patients.set(profile.patient_profile_id, profile);
    // Persist to data/patients if possible
    try {
      const dir = path.join(process.cwd(), 'data', 'patients');
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(
        path.join(dir, `${profile.patient_profile_id}.json`),
        JSON.stringify(profile, null, 2),
        'utf8'
      );
    } catch {
      // ignore persistence error
    }
  }

  public isIndexed(trialId: string): boolean {
    return this.indexedTrials.has(trialId);
  }

  public indexTrial(trialId: string): { trial_id: string; status: string; chunks_created: number; embedding_dimension: number } {
    const trial = this.trials.get(trialId);
    let chunkCount = 0;

    if (trial) {
      const generatedChunks: RAGChunk[] = [];
      let cIndex = 0;

      generatedChunks.push({
        chunk_id: `${trialId}_header`,
        trial_id: trialId,
        text: `Title: ${trial.trial_title}\nIdentifier: ${trial.trial_identifier || 'N/A'}\nTotal Pages: ${trial.total_pages_analyzed || 1}`,
        page_number: 1,
        section: 'Header',
        criterion_type: 'general',
      });

      const incCriteria = Array.isArray(trial.inclusion_criteria) ? trial.inclusion_criteria : [];
      for (const inc of incCriteria) {
        generatedChunks.push({
          chunk_id: `${trialId}_inc_${cIndex++}`,
          trial_id: trialId,
          text: `Inclusion Criterion [${inc.criterion_id}]: ${inc.text}`,
          page_number: inc.source_page || 1,
          section: 'Inclusion Criteria',
          criterion_type: 'inclusion',
        });
      }

      const excCriteria = Array.isArray(trial.exclusion_criteria) ? trial.exclusion_criteria : [];
      for (const exc of excCriteria) {
        generatedChunks.push({
          chunk_id: `${trialId}_exc_${cIndex++}`,
          trial_id: trialId,
          text: `Exclusion Criterion [${exc.criterion_id}]: ${exc.text}`,
          page_number: exc.source_page || 2,
          section: 'Exclusion Criteria',
          criterion_type: 'exclusion',
        });
      }

      const otherReqs = Array.isArray(trial.other_requirements) ? trial.other_requirements : [];
      for (const other of otherReqs) {
        generatedChunks.push({
          chunk_id: `${trialId}_other_${cIndex++}`,
          trial_id: trialId,
          text: `Other Requirement: ${other}`,
          page_number: 1,
          section: 'General Requirements',
          criterion_type: 'general',
        });
      }

      this.chunks.set(trialId, generatedChunks);
      chunkCount = generatedChunks.length;
    } else {
      chunkCount = this.chunks.get(trialId)?.length || 0;
    }

    this.indexedTrials.add(trialId);

    return {
      trial_id: trialId,
      status: 'indexed',
      chunks_created: chunkCount,
      embedding_dimension: 384,
    };
  }

  public searchRAG(trialId: string, query: string, topK: number = 5): RAGSearchResult[] {
    const chunkList = this.chunks.get(trialId) || [];
    if (chunkList.length === 0) return [];

    const queryTokens = query.toLowerCase().split(/\W+/).filter((t) => t.length > 2);
    if (queryTokens.length === 0) {
      return chunkList.slice(0, topK).map((c, i) => ({
        chunk_id: c.chunk_id,
        trial_id: c.trial_id,
        text: c.text,
        page_number: c.page_number,
        section: c.section || undefined,
        criterion_type: c.criterion_type || undefined,
        similarity_score: parseFloat((0.85 - i * 0.05).toFixed(3)),
      }));
    }

    // Score chunks by token presence and phrase match
    const scored = chunkList.map((chunk) => {
      const lower = chunk.text.toLowerCase();
      let score = 0;

      for (const token of queryTokens) {
        if (lower.includes(token)) {
          score += 1.0;
        }
      }

      // Exact substring boost
      if (lower.includes(query.toLowerCase().trim())) {
        score += 3.0;
      }

      // Normalize similarity score to [0.45, 0.95]
      const maxPossible = queryTokens.length + 3.0;
      const normalizedScore = Math.min(0.95, 0.45 + 0.5 * (score / Math.max(1, maxPossible)));

      return {
        chunk,
        score: parseFloat(normalizedScore.toFixed(3)),
      };
    });

    // Sort descending by score
    scored.sort((a, b) => b.score - a.score);

    return scored.slice(0, topK).map((item) => ({
      chunk_id: item.chunk.chunk_id,
      trial_id: item.chunk.trial_id,
      text: item.chunk.text,
      page_number: item.chunk.page_number,
      section: item.chunk.section || undefined,
      criterion_type: item.chunk.criterion_type || undefined,
      similarity_score: item.score,
    }));
  }

  public saveAssessment(detail: AssessmentDetail): void {
    this.assessments.set(detail.assessment_id, detail);
  }

  public getAssessments(filter?: {
    trial_id?: string;
    patient_profile_id?: string;
    limit?: number;
    offset?: number;
  }): AssessmentSummary[] {
    let list = Array.from(this.assessments.values());
    if (filter?.trial_id) {
      list = list.filter((a) => a.trial_id === filter.trial_id);
    }
    if (filter?.patient_profile_id) {
      list = list.filter((a) => a.patient_profile_id === filter.patient_profile_id);
    }
    // Sort newest first
    list.sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
    );
    const offset = filter?.offset || 0;
    const limit = filter?.limit || 50;
    return list.slice(offset, offset + limit).map((a) => ({
      assessment_id: a.assessment_id,
      trial_id: a.trial_id,
      patient_profile_id: a.patient_profile_id,
      reference_date: a.reference_date,
      workflow_status: a.workflow_status,
      final_decision: a.final_decision,
      current_step: a.current_step,
      created_at: a.created_at,
      completed_at: a.completed_at,
      has_errors: a.has_errors,
      error_count: a.error_count,
      warning_count: a.warning_count,
    }));
  }

  public getAssessment(id: string): AssessmentDetail | null {
    return this.assessments.get(id) || null;
  }
}

export const dataStore = new DataStore();
