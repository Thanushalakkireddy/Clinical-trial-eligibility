# Clinical Trial Eligibility System - Frontend

React + TypeScript + Tailwind CSS frontend interface for the Agentic AI Clinical Trial Eligibility & Exclusion Contradiction System.

## Architecture Highlights
- **React 18+** SPA with modern functional components and hooks.
- **Vite** next-generation frontend tooling.
- **Tailwind CSS** responsive, high-contrast healthcare UI styling.
- **TypeScript** strict typing matching backend Pydantic schemas.
- **Decoupled API Service Layer** with health monitoring.

## Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Configure Environment (Optional)
```bash
# Optional API endpoint URL (defaults to http://localhost:8000 via Vite proxy)
VITE_API_BASE_URL=http://localhost:8000
```

### 3. Start Development Server
```bash
npm run dev
```

The application will run at: `http://localhost:3000`

### 4. Build for Production (Vercel Ready)
```bash
npm run build
```
The compiled static assets will be output to the `dist/` directory.
