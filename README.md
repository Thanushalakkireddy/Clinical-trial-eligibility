# Clinical Trial Eligibility & Exclusion Contradiction System (Agentic AI)

An Agentic AI system designed to analyze patient clinical eligibility against complex clinical trial protocols, detect silent exclusion criteria and clinical contradictions, and generate traceable, evidence-backed eligibility decisions.

> ⚠️ **IMPORTANT CLINICAL SAFETY NOTICE**
> This system is an **eligibility-support prototype** and is **NOT an autonomous medical decision maker**. 
> All outputs, criteria evaluations, contradiction alerts, and eligibility recommendations are intended solely to assist clinical trial investigators and study staff. Final eligibility determinations and clinical care decisions must always be made and verified by qualified healthcare professionals and trial investigators.

---

## 📌 Project Overview

Clinical trial matching is traditionally labor-intensive, error-prone, and slow. Protocols contain intricate inclusion criteria and nuanced exclusion criteria (often latent or phrased as contradictory medical history conditions).

This system provides:
1. **Automated Protocol Ingestion**: Structured criterion extraction from trial protocol PDFs.
2. **Patient Medical Record Processing**: Normalization of patient demographics, diagnoses, lab values, and prior treatments.
3. **RAG-Grounded Evidence Retrieval**: Precision semantic retrieval anchored to specific trial protocol sections.
4. **Multi-Agent Orchestration**: Specialized, cooperating agents for inclusion matching, exclusion detection, contradiction detection, and eligibility adjudication.
5. **Traceable Decisioning**: Complete audit trail showing exact criterion clauses, patient facts, and medical rationale.
6. **Production Hardening (Module 9)**: JWT authentication, salted PBKDF2 password hashing, role-based access control, CORS enforcement, request audit logging, input sanitization against path traversal, and multi-stage Docker deployment.

---

## 📁 Repository Structure

```text
clinical-trial-ai/
│
├── server.ts                 # Full-stack Express server (API endpoints & Vite middleware)
├── server/                   # Backend services & agent logic
│   ├── auth.ts               # JWT generator/validator & PBKDF2 password hashing
│   ├── dataStore.ts          # Persistence layer (durable disk + cache for trials/patients)
│   ├── evaluator.ts          # Deterministic 3-state inclusion & exclusion evaluators
│   ├── contradictionEvaluator.ts # Module 7 contradiction & silent exclusion engine
│   ├── decisionReviewer.ts   # Module 8 decision aggregation & review agent
│   ├── normalization.ts      # Clinical data normalization & profile builder
│   └── types.ts              # Domain interfaces, schemas, and types
│
├── frontend/                 # React 19 + TypeScript + Vite + Tailwind CSS UI
│   ├── src/
│   │   ├── components/       # Clinical workflow dashboards & evaluators
│   │   ├── services/api.ts   # Client API integration
│   │   └── App.tsx           # Multi-module tabbed navigation workspace
│   └── vite.config.ts
│
├── data/
│   └── patients/             # Persistent JSON patient records
├── storage/
│   ├── pdfs/                 # Persistent extracted trial protocol definitions
│   └── faiss/                # Vector store index metadata
│
├── test/                     # Automated validation test suites
│   ├── test_module8.ts       # Module 8 decision reviewer tests
│   ├── test_workflow.ts      # Multi-agent sequential pipeline tests
│   └── test_module9.ts       # Module 9 security, auth, CORS & persistence tests
│
├── Dockerfile                # Production multi-stage container build
├── docker-compose.yml        # Orchestration with PostgreSQL and Redis
├── .env.example              # Environment variables template
└── README.md                 # System documentation
```

---

## 🚀 Quickstart & Setup

### Prerequisites
- Node.js 20+ & npm 9+
- Docker & Docker Compose (optional for containerized deployment)

### 1. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key environment configuration variables:
- `JWT_SECRET_KEY`: Secret string for signing HMAC-SHA256 tokens (min 32 chars).
- `ACCESS_TOKEN_EXPIRE_MINUTES`: JWT validity window (default: 60 minutes).
- `CORS_ORIGINS`: Comma-separated list of allowed origins (e.g. `http://localhost:3000`).
- `DATABASE_URL`: Optional PostgreSQL connection string for enterprise database persistence.
- `REDIS_URL`: Optional Redis connection string for distributed caching.
- `GEMINI_API_KEY`: Server-side API key for Google Gemini model access.

### 2. Install Dependencies & Run Locally

```bash
# Install dependencies
npm install

# Start development server (Port 3000)
npm run dev
```

The application is accessible at: `http://localhost:3000`

### 3. Production Build & Execution

```bash
# Build Vite frontend assets and bundle Express server into dist/server.cjs
npm run build

# Start production server
npm start
```

### 4. Docker Deployment

```bash
# Build and run the unified stack (App + PostgreSQL + Redis)
docker-compose up --build
```

---

## 🎯 Verification & Deliverables Status (Modules 1–9)

### Module 1: Architecture & Foundations
- Unified full-stack architecture running Node.js / Express + Vite SPA on port 3000.
- Health endpoints: `GET /health` and `GET /api/v1/health` returning system status.

### Module 2: Clinical Trial PDF Processing & Protocol Extraction
- Protocol upload endpoint `POST /api/v1/trials/upload` with PDF MIME validation and path-traversal sanitization.
- Structured protocol extraction with exact page provenance for criteria clauses.

### Module 3: RAG Pipeline, Embeddings & Semantic Search
- Hierarchical document chunking and metadata preservation.
- REST search and indexing endpoints: `POST /api/v1/trials/:trialId/rag/index` and `POST /api/v1/trials/:trialId/rag/search`.

### Module 4: Patient Profile Processing
- Deterministic clinical data normalization (demographics, labs, units, medications).
- Explicit missing information tracking (`unknown` state rather than assumed negative).
- Endpoints: `POST /api/v1/patients/profile`, `GET /api/v1/patients/:id`, `GET /api/v1/patients`.

### Module 5: Inclusion Matching Agent
- Deterministic 3-state logic (`satisfied`, `unsatisfied`, `unknown`).
- Arithmetic comparisons for numerical laboratory thresholds (e.g., age, ANC, platelets, eGFR).
- Zero diagnosis inference from lab values alone.

### Module 6: Exclusion Detection Agent
- Deterministic exclusion evaluation with strict 3-state evaluation (`triggered`, `not_triggered`, `unknown`).
- Clear mapping of disqualifying conditions and clinical safety risks.

### Module 7: Contradiction & Silent Exclusion Engine
- Detection of latent clinical contradictions and silent exclusions (e.g., undiagnosed organ impairment, drug interactions).
- Severity classifications (`low`, `medium`, `high`, `critical`).

### Module 8: Decision Reviewer & Multi-Agent Workflow
- Adjudication engine synthesizing inclusion, exclusion, and contradiction findings.
- Decisions: `ELIGIBLE`, `NOT_ELIGIBLE`, `MORE_INFORMATION_REQUIRED`.
- Endpoints: `POST /api/v1/trials/:trialId/patients/:patientProfileId/workflow-evaluation` and `POST /api/v1/eligibility/evaluate`.

### Module 9: Production Hardening, Security & Deployment Readiness
- **Authentication**: JWT token generation and validation with HMAC-SHA256.
- **Password Security**: Salted PBKDF2 (SHA-512, 100,000 iterations) with constant-time equality checks.
- **Pre-seeded Accounts**:
  - Clinician: `clinical_evaluator` / `Evaluator123!` (role: `clinician`)
  - Admin: `admin` / `AdminSecret123!` (role: `admin`)
- **Protected Endpoints**:
  - `POST /api/v1/auth/login`: Issue access token.
  - `GET /api/v1/auth/me`: Validate token and return authenticated user details.
- **CORS & Security Headers**: Configurable `CORS_ORIGINS`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`.
- **Upload Security**: PDF extension and MIME validation, 30MB file cap, filename sanitization against path traversal.
- **Persistence**: Durable disk storage for patient records (`data/patients/*.json`) and trial protocols (`storage/pdfs/*_protocol.json`).
- **Structured Audit Logging**: Safe request telemetry without PII exposure, and structured audit logs for clinical evaluation outcomes.
- **Deployment**: Production multi-stage `Dockerfile` and `docker-compose.yml`.

---

## 🧪 Automated Testing

Run the test suites:

```bash
# Run Module 8 Decision Reviewer tests
npx tsx test/test_module8.ts

# Run Multi-Agent Workflow tests
npx tsx test/test_workflow.ts

# Run Module 9 Production Hardening & Security tests
npx tsx test/test_module9.ts
```

All test suites execute with 100% pass rates.

---

## ⚖️ Safety & Regulatory Considerations

1. **Non-Autonomous Assistance**: This system is designed as a Decision Support System (DSS). It does not initiate or modify therapy, approve trial enrollments, or replace clinical judgment.
2. **Data Privacy (HIPAA / GDPR)**: Production deployments must ensure that patient data at rest and in transit is encrypted, de-identified or pseudonymized in compliance with local healthcare privacy regulations.
3. **Auditability**: All criteria determinations trace directly to source document citations and patient health record entries to enable clinical review.
