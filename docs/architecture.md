# Architecture Specification: Agentic AI Clinical Trial Eligibility & Exclusion Contradiction System

## 1. Project Purpose

Clinical trial patient screening is a critical bottleneck in biomedical research. Trial protocols typically span 50–150+ pages containing complex medical eligibility criteria consisting of:
- **Inclusion Criteria**: Explicit prerequisites (e.g., specific histological cancer subtypes, age thresholds, biomarker mutations, ECOG performance scores).
- **Exclusion Criteria**: Prohibitive conditions (e.g., prior lines of therapy within 28 days, active CNS metastases, renal impairment thresholds).
- **Silent Exclusion Triggers & Medical Contradictions**: Nuanced or latent medical conflicts that disqualify a patient even when preliminary inclusion rules appear met (e.g., a patient taking an unlisted medication for a secondary ailment that interacts with the investigational agent, or an implicit organ dysfunction revealed across disparate lab values).

The purpose of this system is to provide an **Agentic, Evidence-Traceable Clinical Trial Eligibility & Contradiction System**. Using a cooperative multi-agent LangGraph workflow and Retrieval-Augmented Generation (RAG), the system:
1. Ingests and structures clinical trial protocol documents (PDFs).
2. Parses and normalizes patient health records and profile narratives.
3. Performs semantic RAG retrieval against protocol evidence chunks.
4. Distributes analysis to specialized AI agents (Protocol Extraction, Patient Profile, Inclusion Matching, Exclusion Detection, Contradiction Detection, and Decision Review).
5. Produces a deterministic, audited outcome:
   - **Eligible**
   - **Not Eligible**
   - **More Information Required**
6. Backs every verdict with traceable citations mapping exact protocol criterion clauses to specific patient data points.

---

## 2. Frontend Architecture

- **Core Stack**:
  - **Framework**: React 18+ (SPA) with TypeScript
  - **Bundler & Build Tool**: Vite
  - **Styling**: Tailwind CSS
  - **State & Data Fetching**: React Hooks with modular API client service layer (`frontend/src/services/api.ts`)

- **Component & Design Philosophy**:
  - **Single Page Application Layout**: Clean, high-contrast, accessible healthcare dashboard.
  - **Modular Views**:
    - `LandingPage`: Overview, system status, and workflow entrypoint.
    - `ProtocolUploader`: Dropzone and progress feedback for trial protocol PDFs.
    - `PatientProfileForm`: Structured and unstructured patient clinical data entry.
    - `AnalysisDashboard`: Interactive decision viewer displaying eligibility status badges, criterion checklist, contradiction warnings, and audit citations.
    - `TraceabilityDrawer`: Side-panel detailing exact protocol text excerpts and confidence rationale for each criterion.
  - **Strict Type Safety**: All domain entities (Protocols, Criteria, Patient Attributes, Agent States, Decision Enums) are codified in TypeScript interfaces in `frontend/src/types/`.

---

## 3. Backend Architecture

- **Core Stack**:
  - **Framework**: FastAPI (Python 3.10+)
  - **Data Validation & Serialization**: Pydantic v2
  - **Asynchronous Execution**: Native Python `asyncio` for non-blocking I/O operations across agent steps and database queries.
  - **API Routing**: Versioned REST architecture under `/api/v1/` with dedicated sub-routers for health, protocols, patients, and eligibility workflows.

- **Design Patterns**:
  - **Dependency Injection**: FastAPI `Depends` handles database sessions, configuration instances, and service clients.
  - **Factory & Strategy Patterns**: Modular interfaces for LLMs (`BaseLLMService`), vector stores (`BaseVectorStore`), and workflow state stores (`BaseWorkflowStateService`), allowing swap-in replacement without altering domain logic.
  - **Centralized Settings**: Pydantic `BaseSettings` reading from `.env` with strict type validation.

---

## 4. Agent Architecture (LangGraph Orchestration)

The system orchestrates a multi-agent cognitive graph built on **LangGraph**. Each agent operates as a specialized state graph node with bounded agency and dedicated responsibilities:

```
[Patient Input + Clinical Trial Protocol PDF]
                      │
                      ▼
        ┌───────────────────────────┐
        │ Protocol Extraction Agent │  (Parses inclusion/exclusion rules, formats into structured criteria)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │   Patient Profile Agent   │  (Normalizes patient history, labs, comorbidities, medications)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │       RAG Retrieval       │  (Fetches relevant protocol chunks, guidelines & lab thresholds)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │ Inclusion Matching Agent  │  (Systematically checks each inclusion criterion against patient facts)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │ Exclusion Detection Agent │  (Identifies explicit contraindications & disqualifying conditions)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │    Contradiction Agent    │  (Uncovers latent conflicts, drug-disease clashes, silent triggers)
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │  Decision/Reviewer Agent  │  (Adjudicates overall status: Eligible / Not Eligible / More Info)
        └─────────────┬─────────────┘
                      │
                      ▼
         [Traceable Eligibility Result]
```

### Agent Node Roles:
1. **Protocol Extraction Agent**: Extracts and separates clinical trial criteria into distinct items with unique identifiers, category tags, and raw excerpt provenance.
2. **Patient Profile Agent**: Ingests patient records (labs, medications, conditions, dates) into a standardized medical profile representation.
3. **RAG Retrieval Step**: Queries the vector store for semantic context when criteria require deeper interpretation or referenced protocol appendices.
4. **Inclusion Matching Agent**: Evaluates patient facts against each positive prerequisite. Evaluates satisfaction status (`Met`, `Unmet`, `Unknown`).
5. **Exclusion Detection Agent**: Screens for explicit exclusion factors. Any verified exclusion flags the protocol as immediately disqualified.
6. **Contradiction Agent**: Detects cross-clause contradictions and silent exclusion triggers (e.g., patient is on a prohibited CYP3A4 inhibitor not explicitly listed by brand name, or lab trend implies acute injury).
7. **Decision / Reviewer Agent**: Aggregates all evaluations, checks logical consistency, resolves edge cases, verifies audit evidence chains, and produces the finalized `EligibilityDecision`.

---

## 5. RAG Architecture

- **Embeddings Layer**:
  - Initial Provider: `sentence-transformers/all-MiniLM-L6-v2` (or domain-specific BioBERT / PubMedBERT embeddings).
  - Interface: `BaseEmbeddingService` enables straightforward migration to Google Gemini text embeddings or OpenAI embeddings.
- **Vector Store Layer**:
  - Initial Store: **FAISS** (Facebook AI Similarity Search) running in-process for lightweight local similarity indexing.
  - Interface: `BaseVectorStore` abstract class defining `add_documents()`, `similarity_search()`, and `delete()`.
  - Future Migration: Configurable to **ChromaDB** or **Pinecone** via configuration flag (`VECTOR_STORE_BACKEND=faiss|chroma|pinecone`) without changing application business logic.
- **Chunking Strategy**:
  - Domain-aware medical chunking preserving hierarchical header context (e.g., "Section 4.1: Inclusion Criteria - Biomarker Status").

---

## 6. Database Architecture

- **Engine**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.0 (AsyncIO engine with `asyncpg`)
- **Alembic**: Database migrations (ready for Module 2+ schema provisioning).
- **Core Entities Planned**:
  - `TrialProtocol`: Trial metadata, NCT ID, title, original document references.
  - `Criterion`: Extracted inclusion/exclusion rules, category, source page, raw text.
  - `PatientRecord`: Patient demographics, clinical summary, structured attributes.
  - `EvaluationRun`: Execution instance linking a patient to a protocol with session audit logs.
  - `CriterionEvaluation`: Specific agent decision for a single criterion with explanation and patient evidence references.
  - `ContradictionAlert`: Detected silent triggers or medical inconsistencies.
- **Modularity**: Database access abstracted through async session management in `app/database/session.py`.

---

## 7. Future Request / Data Flow

```
1. Client (React UI) -> POST /api/v1/protocols/upload (PDF File)
   └── Document Processing Service extracts raw text
   └── Protocol Extraction Agent generates structured Criteria
   └── RAG Pipeline computes embeddings and indexes into FAISS
   └── Protocol & Criteria saved to PostgreSQL

2. Client -> POST /api/v1/patients/ (JSON Medical Record or Note)
   └── Patient Profile Agent parses and normalizes medical facts
   └── Patient profile stored in PostgreSQL

3. Client -> POST /api/v1/eligibility/evaluate
   └── Body: { "protocol_id": "...", "patient_id": "..." }
   └── LangGraph workflow initialized with state
   └── Iterative agent execution:
       - RAG semantic retrieval on ambiguous criteria
       - Inclusion agent evaluates positive criteria
       - Exclusion agent evaluates prohibitive criteria
       - Contradiction agent identifies latent clinical conflicts
       - Decision agent determines consensus and compiles traceable links
   └── Result persisted to database
   └── Response returned to Client

4. Client displays interactive dashboard:
   - High-level decision card
   - Categorized criteria table with badge indicators
   - Expandable evidence panels with PDF citation anchors
```

---

## 8. Folder Responsibilities

### `backend/`
- `app/main.py`: Application entrypoint, FastAPI instance creation, CORS middleware, top-level routes.
- `app/config/`: `settings.py` for pydantic-settings environment variable loading.
- `app/api/`: Versioned API endpoints (`/api/v1/endpoints/`) and dependency providers (`deps.py`).
- `app/models/`: SQLAlchemy ORM database models and declarative base definitions.
- `app/schemas/`: Pydantic models for request bodies, responses, and intermediate validation.
- `app/services/`: External service abstractions (Gemini LLM wrapper, Workflow state manager).
- `app/agents/`: LangGraph agent definitions, state schemas, node functions, and graph compilation.
- `app/rag/`: Vector database abstraction, FAISS provider, and embedding wrappers.
- `app/document_processing/`: PDF extraction, text normalization, and chunking interfaces.
- `app/database/`: Async SQLAlchemy engine and session factory.
- `app/utils/`: Standardized logging, formatting, and exception utilities.
- `tests/`: Automated pytest unit and integration test fixtures.

### `frontend/`
- `src/components/`: Reusable, accessible UI components (Navbar, Status Cards, Badges).
- `src/pages/`: Main application screens (LandingPage, EvaluationView).
- `src/services/`: HTTP client communicating with backend endpoints.
- `src/types/`: TypeScript definitions matching backend Pydantic schemas.
- `src/hooks/`: React hooks for API state management and health checking.
- `src/utils/`: Utility functions for date, string, and clinical status formatting.
- `src/App.tsx`: Main routing and view coordination.

### `docs/`
- `architecture.md`: Comprehensive system architecture and specification reference.

---

## 9. Future Deployment Architecture

- **Backend (Render)**:
  - Docker container deployment via Render Web Service.
  - Health check configured to `GET /health`.
  - Managed PostgreSQL instance connected via secure connection string (`DATABASE_URL`).
  - Environment variables configured through Render dashboard.

- **Frontend (Vercel)**:
  - Static Vite deployment connected directly to the GitHub repository.
  - Environment variable `VITE_API_BASE_URL` pointing to the Render backend domain.
  - Edge network distribution with automated preview deployments on pull requests.

- **Local Development**:
  - `docker-compose.yml` defining synchronized multi-container environment (PostgreSQL database, FastAPI backend, and React frontend).

---

## 10. Module 2: Clinical Trial PDF Processing & Protocol Extraction

Module 2 implements the protocol ingestion pipeline that transforms unstructured clinical trial protocol PDFs into structured, evidence-traceable criteria models:

```
[Clinical Trial PDF]
         │
         ▼
[POST /api/v1/trials/upload]
  ├─ Multipart Validation (.pdf extension, %PDF- magic bytes, size <= 25MB)
  ├─ UUID Trial ID Generation
  └─ Modular Storage Persistence (data/uploads/{trial_id}.pdf)
         │
         ▼
[POST /api/v1/trials/{trial_id}/extract-protocol]
         │
         ▼
[PDFProtocolProcessor (PyMuPDF / pypdf)]
  ├─ Page-by-page text extraction
  └─ 1-indexed source page numbering preservation
         │
         ▼
[Document Cleaner (clean_protocol_text)]
  ├─ Normalizes whitespace and paragraph continuations
  └─ STRICT PRESERVATION: Inequalities (<, >, <=, >=, =), units (mL/min/1.73m², mg/dL, cells/mcL), thresholds
         │
         ▼
[ProtocolExtractionAgent]
  ├─ Modular LLM Structured Extraction (GeminiLLMService with Pydantic response schema)
  └─ Deterministic Clinical Rule-Based Fallback (guarantees offline & automated test repeatability)
         │
         ▼
[Structured ProtocolExtractionResponse]
  ├─ trial_id, trial_title, trial_identifier (NCT ID)
  ├─ inclusion_criteria: [criterion_id, type="inclusion", text, source_page, trial_id]
  ├─ exclusion_criteria: [criterion_id, type="exclusion", text, source_page, trial_id]
  └─ other_requirements: [general eligibility instructions]
```

### Traceability & Medical Safety Principles:
- **No Autonomous Decisions**: The Protocol Extraction Agent strictly structures protocol rules; it does NOT evaluate patient eligibility.
- **Verbatim Integrity**: Criteria text maintains clinical wording without destructive summarization.
- **Provenance Citations**: Every individual criterion carries a direct reference to its originating `source_page` and `trial_id`.

---

## 11. Module 4: Patient Profile Processing & Patient Profile Agent

Module 4 implements the patient record intake, clinical data validation, deterministic normalization, missing information detection, and structured profile generation pipeline:

```
[Raw Patient Clinical Information (JSON / Clinical Notes)]
                       │
                       ▼
         [Pydantic v2 Input Validation]
  ├─ Demographics validation (age: 0–130, weight/height > 0)
  ├─ Lab constraints (non-empty names, non-negative values for eGFR/platelets/etc.)
  └─ Missing optional field tolerance
                       │
                       ▼
      [Clinical Normalization Service (Deterministic)]
  ├─ Standardizes lab test names to canonical identifiers (e.g., "eGFR (CKD-EPI)" → "egfr")
  ├─ Standardizes measurement units (e.g., "ml/min/1.73m2" → "mL/min/1.73m²", "10*9/l" → "10^9/L")
  ├─ Normalizes condition names (e.g., "T2DM" → "type 2 diabetes", "HTN" → "hypertension")
  ├─ Normalizes medications (parses dose/unit if combined, extracts canonical drug entity)
  ├─ Calculates BMI deterministically (weight / (height/100)²)
  └─ SAFETY GUARANTEE: Never performs unsafe unit conversions without known molecular mass
                       │
                       ▼
             [Patient Profile Agent]
  ├─ Bounded Agentic Node in LangGraph workflow
  ├─ Extracts explicitly stated clinical entities
  ├─ Zero Hallucination Guarantee: Never invents missing data
  ├─ Strictly avoids diagnostic inference (e.g., eGFR 28 NEVER automatically becomes "renal failure")
  ├─ Preserves original names, values, and units alongside normalized counterparts
  └─ Attaches source provenance tags to every attribute (e.g., source: "patient_input")
                       │
                       ▼
       [Explicit Missing Information Audit]
  ├─ Scans for unsupplied key clinical domains (liver, renal, cardiac, ecog, pregnancy)
  └─ Explicitly marks omitted fields as {"field": "...", "status": "unknown"}
     (Never converts missing data to "no disease" or "false")
                       │
                       ▼
          [StructuredPatientProfile]
  ├─ Unique non-PII patient_profile_id (UUID-derived)
  ├─ profile_status: "processed"
  ├─ demographics: { age, sex, height, weight, bmi }
  ├─ conditions: [NormalizedCondition]
  ├─ medical_history: [NormalizedCondition]
  ├─ medications: [NormalizedMedication]
  ├─ lab_values: [NormalizedLabValue]
  ├─ allergies: [NormalizedAllergy]
  ├─ vital_signs: NormalizedVitalSigns
  └─ missing_information: [MissingInfoItem]
                       │
                       ▼
          [REST API & Persistent Storage]
  ├─ POST /api/v1/patients/profile (Ingests & processes profile)
  ├─ GET /api/v1/patients/{patient_profile_id} (Retrieves stored profile)
  └─ GET /api/v1/patients (Lists all processed profiles)
```

### Safety & Medical Boundaries:
1. **No Eligibility Decisions**: The Patient Profile Agent processes patient information only; it does NOT determine clinical trial eligibility, evaluate inclusion/exclusion criteria, or detect contradictions. Eligibility evaluation occurs strictly downstream in Module 5.
2. **Missing Information Is Unknown, Not Negative**: A missing history of liver disease does NOT mean "patient has no liver disease." It is explicitly recorded as `unknown`.
3. **No Unsafe Normalization**: Values are never converted between incompatible units (e.g., mg/dL to mmol/L) without precise molecular weights.
4. **Audit Traceability**: Every extracted condition, medication, allergy, and laboratory result retains its exact source provenance (`patient_input`, `ehr_feed`, or specific document).

---

## 12. Module 5: Inclusion Matching Agent

Module 5 implements deterministic and semantic evaluation of clinical trial inclusion criteria against structured patient profiles using a strict 3-state logic engine:

```
Clinical Trial Inclusion Criteria (Module 2)
                 +
Structured Patient Profile (Module 4)
                 │
                 ▼
     [Inclusion Matching Agent]
                 │
                 ├─ [1. Deterministic Rule Evaluator] (Primary Priority)
                 │    ├─ Numeric ranges (e.g., 18 <= age <= 70)
                 │    ├─ Thresholds (>=, <=, >, < for labs like HbA1c, eGFR, platelets)
                 │    ├─ Direct condition confirmation (e.g., documented Type 2 Diabetes)
                 │    └─ Arithmetic checks (never asks an LLM for simple numeric comparisons)
                 │
                 ├─ [2. LLM Semantic Fallback] (For complex narrative criteria)
                 │    ├─ RAG protocol context enrichment (Module 3)
                 │    └─ Structured Pydantic response schema (Zero Hallucination)
                 │
                 ├─ [3. Three-State Classification for Every Criterion]
                 │    ├─ Satisfied: Explicit patient data proves criterion is met
                 │    ├─ Unsatisfied: Explicit patient data proves criterion is failed
                 │    └─ Unknown: Insufficient data to evaluate (Never assumed satisfied or negative)
                 │
                 ├─ [4. Medical Safety & Zero Diagnosis Inference]
                 │    ├─ Glucose >= 180 does NOT infer "Type 2 Diabetes" without diagnosis
                 │    ├─ eGFR <= 28 does NOT infer "Chronic Kidney Disease" without diagnosis
                 │    └─ Preserves laboratory values and condition records as separate entities
                 │
                 ├─ [5. Overall Inclusion Status Aggregation]
                 │    ├─ If ANY criterion is UNSATISFIED ───────► overall = "unsatisfied"
                 │    ├─ Else if ANY criterion is UNKNOWN ─────► overall = "unknown"
                 │    └─ Else (ALL criteria satisfied) ────────► overall = "satisfied"
                 │
                 └─ [6. Complete Evidence Traceability]
                      ├─ patient_evidence: { field, value, source }
                      ├─ protocol_evidence: { text, source_page, trial_id }
                      ├─ missing_information: ["field1", "field2"]
                      └─ reason: clear, human-readable medical rationale
                                │
                                ▼
        [InclusionEvaluationResponse (REST API)]
  POST /api/v1/trials/{trial_id}/patients/{patient_profile_id}/inclusion-evaluation
                                │
                                ▼
        [Interactive Frontend Evaluation Dashboard]
  (Overall status banner, metric counters, filterable criterion cards)
```

### Module 5 Boundaries & Constraints:
1. **Inclusion Criteria Only**: Evaluates inclusion criteria only. Exclusion criteria, latent contradiction analysis, and final eligibility synthesis are strictly reserved for downstream modules.
2. **Deterministic Priority**: Arithmetical and range comparisons are performed using native Python logic; LLMs are never tasked with basic numeric operations.
3. **Auditability**: Every criterion evaluation contains non-empty reasoning and links directly to the protocol source page citation and patient evidence record.



