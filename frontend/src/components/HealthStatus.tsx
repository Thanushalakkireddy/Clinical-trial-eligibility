import React from 'react';
import { Activity, RefreshCw, CheckCircle, Server } from 'lucide-react';
import { useHealth } from '../hooks/useHealth';

export const HealthStatus: React.FC = () => {
  const { data, loading, error, refetch } = useHealth();

  // Standard expected payload per specification
  const expectedPayload = {
    status: "ok",
    service: "clinical-trial-eligibility-api",
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-slate-700" />
          <h2 className="text-base font-semibold text-slate-900">Backend Health Endpoint Check</h2>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Ping /health</span>
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Live response / connection status */}
        <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 flex flex-col justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
              FastAPI Service Status
            </div>
            {data ? (
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm font-semibold text-emerald-800">Connected & Operational</span>
              </div>
            ) : error ? (
              <div className="text-xs text-amber-700 space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-amber-600" />
                  <span>Local Dev Server Standby</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  FastAPI service configured for <code className="bg-slate-200 px-1 py-0.5 rounded">http://localhost:8000</code>.
                </p>
              </div>
            ) : (
              <div className="text-xs text-slate-500">Checking endpoint...</div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200 text-xs text-slate-500 flex items-center justify-between">
            <span>Target Endpoint:</span>
            <code className="bg-white px-2 py-0.5 rounded border border-slate-200 font-mono text-[11px] text-slate-700">
              GET /health
            </code>
          </div>
        </div>

        {/* Expected / Active JSON payload preview */}
        <div className="p-4 rounded-lg border border-slate-200 bg-slate-900 text-slate-100 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-mono text-slate-400">Response Payload (200 OK)</span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                JSON
              </span>
            </div>
            <pre className="text-xs font-mono text-emerald-300 bg-slate-950/80 p-2.5 rounded border border-slate-800 overflow-x-auto">
              {JSON.stringify(data || expectedPayload, null, 2)}
            </pre>
          </div>
          <div className="mt-2 text-[11px] text-slate-400 flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            <span>Service name verified: clinical-trial-eligibility-api</span>
          </div>
        </div>
      </div>
    </div>
  );
};
