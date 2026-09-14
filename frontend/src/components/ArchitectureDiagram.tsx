import React from 'react';
import {
  FileText,
  UserCheck,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Scale,
  Award,
  ArrowDown,
} from 'lucide-react';

interface AgentStep {
  title: string;
  subtitle: string;
  role: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}

const AGENT_STEPS: AgentStep[] = [
  {
    title: 'Protocol Extraction Agent',
    subtitle: 'Step 1 • Document Parsing',
    role: 'Segments PDF into structured inclusion & exclusion criteria with section anchors.',
    icon: FileText,
    accent: 'border-slate-300 text-slate-700 bg-slate-50',
  },
  {
    title: 'Patient Profile Agent',
    subtitle: 'Step 2 • Clinical Normalization',
    role: 'Standardizes patient history, medications, diagnoses, and lab reference ranges.',
    icon: UserCheck,
    accent: 'border-blue-200 text-blue-700 bg-blue-50/50',
  },
  {
    title: 'RAG Retrieval',
    subtitle: 'Step 3 • Semantic Grounding',
    role: 'Sentence Transformers + FAISS retrieve protocol clauses, lab appendices, and guidelines.',
    icon: Search,
    accent: 'border-indigo-200 text-indigo-700 bg-indigo-50/50',
  },
  {
    title: 'Inclusion Matching Agent',
    subtitle: 'Step 4 • Prerequisite Verification',
    role: 'Evaluates positive criteria satisfaction (Met, Unmet, Unknown) with evidence traces.',
    icon: CheckCircle2,
    accent: 'border-emerald-200 text-emerald-700 bg-emerald-50/50',
  },
  {
    title: 'Exclusion Detection Agent',
    subtitle: 'Step 5 • Contraindication Screening',
    role: 'Screens for disqualifying pathologies, concurrent therapies, and wash-out windows.',
    icon: XCircle,
    accent: 'border-rose-200 text-rose-700 bg-rose-50/50',
  },
  {
    title: 'Contradiction Agent',
    subtitle: 'Step 6 • Silent Trigger Analysis',
    role: 'Detects cross-clause clashes, implicit contraindications, and drug-disease conflicts.',
    icon: AlertTriangle,
    accent: 'border-amber-200 text-amber-700 bg-amber-50/50',
  },
  {
    title: 'Decision / Reviewer Agent',
    subtitle: 'Step 7 • Clinical Adjudication',
    role: 'Resolves agent outputs into one verdict: Eligible, Not Eligible, or More Info Required.',
    icon: Scale,
    accent: 'border-purple-200 text-purple-700 bg-purple-50/50',
  },
];

export const ArchitectureDiagram: React.FC = () => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-base font-semibold text-slate-900">LangGraph Multi-Agent Orchestration Flow</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Sequential state transitions with evidence accumulation across specialized reasoning agents
          </p>
        </div>
        <span className="text-xs font-medium px-2.5 py-1 bg-slate-100 text-slate-700 rounded-md border border-slate-200">
          Clinical Decision Workflow
        </span>
      </div>

      {/* Input node */}
      <div className="mt-5 flex flex-col items-center">
        <div className="w-full max-w-lg p-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center gap-3 text-xs font-semibold text-slate-700">
          <span className="px-2 py-0.5 bg-white border border-slate-200 rounded text-slate-800">
            Patient Input
          </span>
          <span className="text-slate-400 font-bold">+</span>
          <span className="px-2 py-0.5 bg-white border border-slate-200 rounded text-slate-800">
            Clinical Trial PDF Protocol
          </span>
        </div>
        <ArrowDown className="w-4 h-4 text-slate-400 my-1.5" />
      </div>

      {/* Agent steps */}
      <div className="space-y-2 max-w-xl mx-auto">
        {AGENT_STEPS.map((step, idx) => {
          const Icon = step.icon;
          return (
            <React.Fragment key={step.title}>
              <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 bg-white hover:border-slate-300 transition-colors">
                <div className={`p-2 rounded-md border ${step.accent} shrink-0 mt-0.5`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
                    <span className="text-[11px] font-medium text-slate-400">{step.subtitle}</span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">{step.role}</p>
                </div>
              </div>
              {idx < AGENT_STEPS.length - 1 && (
                <div className="flex justify-center -my-1">
                  <ArrowDown className="w-3.5 h-3.5 text-slate-400" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Final output node */}
      <div className="mt-3 flex flex-col items-center">
        <ArrowDown className="w-4 h-4 text-slate-400 mb-1.5" />
        <div className="w-full max-w-lg p-3.5 rounded-lg border border-emerald-300 bg-emerald-50/70 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <Award className="w-4 h-4 text-emerald-700" />
            <span className="font-semibold text-emerald-950">Traceable Eligibility Result</span>
          </div>
          <div className="flex items-center gap-1.5 font-medium text-[11px]">
            <span className="px-2 py-0.5 bg-white border border-emerald-200 text-emerald-800 rounded">
              Eligible
            </span>
            <span className="px-2 py-0.5 bg-white border border-rose-200 text-rose-800 rounded">
              Not Eligible
            </span>
            <span className="px-2 py-0.5 bg-white border border-amber-200 text-amber-800 rounded">
              More Info Required
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
