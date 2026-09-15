import React from 'react';
import { ShieldCheck, Stethoscope, FileText, User } from 'lucide-react';

interface HeaderProps {
  onOpenArchitecture?: () => void;
  onNavigateHome?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenArchitecture, onNavigateHome }) => {
  return (
    <header className="border-b border-slate-200 bg-white sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <button
          type="button"
          onClick={onNavigateHome}
          className="flex items-center gap-3 text-left cursor-pointer hover:opacity-95 transition-opacity"
        >
          <div className="w-9 h-9 rounded-lg bg-sky-900 text-white flex items-center justify-center font-bold text-sm shadow-xs">
            <Stethoscope className="w-5 h-5 text-sky-200" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-900 tracking-tight text-sm sm:text-base">
                Clinical Trial Eligibility Assessment
              </span>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 hidden sm:inline-block">
                Clinical Decision Support
              </span>
            </div>
            <p className="text-xs text-slate-500 hidden sm:block">
              Traceable, evidence-backed protocol matching & safety analysis
            </p>
          </div>
        </button>

        <div className="flex items-center gap-3 text-xs font-medium text-slate-600">
          {onOpenArchitecture && (
            <button
              type="button"
              onClick={onOpenArchitecture}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 transition-colors cursor-pointer"
              title="View system architecture and documentation"
            >
              <FileText className="w-3.5 h-3.5 text-slate-500" />
              <span>How It Works</span>
            </button>
          )}
          <div className="hidden md:flex items-center gap-1.5 text-emerald-700 bg-emerald-50/70 border border-emerald-200/80 px-2.5 py-1 rounded-md">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Audit-Traceable</span>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 text-slate-700">
            <User className="w-3.5 h-3.5 text-slate-500" />
            <span className="hidden sm:inline">Clinical Evaluator</span>
          </div>
        </div>
      </div>
    </header>
  );
};
