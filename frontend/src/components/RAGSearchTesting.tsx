import React, { useState, useEffect } from 'react';
import {
  Search,
  Database,
  Layers,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  RefreshCw,
  Hash,
  Sliders,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  Tag,
} from 'lucide-react';
import { indexTrialRAG, searchTrialRAG, getTrialRAGStatus } from '../services/api';
import { RAGSearchResult, RAGIndexResponse } from '../types';

interface RAGSearchTestingProps {
  initialTrialId?: string | null;
}

export const RAGSearchTesting: React.FC<RAGSearchTestingProps> = ({ initialTrialId }) => {
  const [trialId, setTrialId] = useState<string>(initialTrialId || '');
  const [isIndexed, setIsIndexed] = useState<boolean | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);

  // Indexing state
  const [indexing, setIndexing] = useState(false);
  const [indexResult, setIndexResult] = useState<RAGIndexResponse | null>(null);
  const [indexError, setIndexError] = useState<string | null>(null);

  // Search state
  const [query, setQuery] = useState<string>('What are the renal exclusion criteria?');
  const [topK, setTopK] = useState<number>(5);
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<RAGSearchResult[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Sync prop changes
  useEffect(() => {
    if (initialTrialId && initialTrialId !== trialId) {
      setTrialId(initialTrialId);
    }
  }, [initialTrialId]);

  // Check index status when trialId changes
  useEffect(() => {
    if (!trialId.trim()) {
      setIsIndexed(null);
      return;
    }
    checkStatus(trialId.trim());
  }, [trialId]);

  const checkStatus = async (tid: string) => {
    setCheckingStatus(true);
    try {
      const res = await getTrialRAGStatus(tid);
      setIsIndexed(res.is_indexed);
    } catch {
      setIsIndexed(false);
    } finally {
      setCheckingStatus(false);
    }
  };

  const handleIndex = async () => {
    if (!trialId.trim()) {
      setIndexError('Please enter or select a Trial ID first.');
      return;
    }

    setIndexing(true);
    setIndexError(null);
    setIndexResult(null);

    try {
      const res = await indexTrialRAG(trialId.trim());
      setIndexResult(res);
      setIsIndexed(true);
    } catch (err: any) {
      setIndexError(err.message || 'Failed to index protocol.');
    } finally {
      setIndexing(false);
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!trialId.trim()) {
      setSearchError('Please provide a Trial ID before searching.');
      return;
    }
    if (!query.trim()) {
      setSearchError('Please enter a semantic search query.');
      return;
    }

    setSearching(true);
    setSearchError(null);

    try {
      const res = await searchTrialRAG(trialId.trim(), {
        query: query.trim(),
        top_k: topK,
      });
      setSearchResults(res.results);
      // Auto-update index status as search succeeded
      setIsIndexed(true);
    } catch (err: any) {
      setSearchError(err.message || 'Semantic search failed.');
      setSearchResults(null);
    } finally {
      setSearching(false);
    }
  };

  const sampleQueries = [
    'What are the renal exclusion criteria?',
    'What is the minimum and maximum eligible patient age?',
    'What are the cardiac and hypertension exclusion limits?',
    'What are the required baseline neutrophil and platelet counts?',
  ];

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-6 border-b border-slate-100 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
              Protocol Search
            </span>
            <h2 className="text-lg font-bold text-slate-900">
              Protocol Knowledge Base & Semantic Search
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Grounded vector retrieval with page citations, sentence transformers embeddings, and strict trial isolation.
          </p>
        </div>

        {/* Index Status Badge */}
        <div className="flex items-center gap-2">
          {trialId.trim() && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border bg-slate-50">
              <span className="text-slate-500">FAISS Index:</span>
              {checkingStatus ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" />
              ) : isIndexed ? (
                <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-amber-700 font-semibold">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-600" /> Not Indexed
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Target Trial ID & Indexing Control */}
      <div className="p-4 bg-slate-50/80 rounded-lg border border-slate-200 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-8">
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Target Clinical Trial ID
            </label>
            <div className="relative">
              <input
                type="text"
                value={trialId}
                onChange={(e) => setTrialId(e.target.value)}
                placeholder="e.g. trial-uuid or upload a PDF above"
                className="w-full pl-9 pr-3 py-2 text-xs font-mono bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-slate-800"
              />
              <Hash className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            </div>
          </div>

          <div className="md:col-span-4 flex gap-2">
            <button
              type="button"
              onClick={handleIndex}
              disabled={indexing || !trialId.trim()}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-sm"
            >
              {indexing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Indexing Vectors...</span>
                </>
              ) : (
                <>
                  <Database className="w-3.5 h-3.5" />
                  <span>{isIndexed ? 'Re-index Protocol' : 'Index in FAISS'}</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => trialId && checkStatus(trialId)}
              title="Refresh Index Status"
              className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${checkingStatus ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Index Feedback */}
        {indexResult && (
          <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-md text-xs text-emerald-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>
                <strong>Protocol Indexed:</strong> Created <strong>{indexResult.chunks_created}</strong> chunks in FAISS with <strong>{indexResult.embedding_dimension}D</strong> embeddings (all-MiniLM-L6-v2).
              </span>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
              Isolation: Trial-Specific FlatIP
            </span>
          </div>
        )}

        {indexError && (
          <div className="mt-3 p-3 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-800 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <span>{indexError}</span>
          </div>
        )}
      </div>

      {/* Semantic Search Query Form */}
      <form onSubmit={handleSearch} className="space-y-4 mb-6">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-semibold text-slate-700">
              Natural Language Protocol Query
            </label>
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Sliders className="w-3.5 h-3.5" />
              <span>Top-K:</span>
              <select
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="py-0.5 px-2 bg-slate-50 border border-slate-200 rounded text-xs text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value={3}>3 chunks</option>
                <option value={5}>5 chunks</option>
                <option value={8}>8 chunks</option>
                <option value={10}>10 chunks</option>
              </select>
            </div>
          </div>

          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a clinical question about protocol criteria..."
              className="w-full pl-10 pr-28 py-2.5 text-sm bg-slate-50/50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white text-slate-800 transition"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />

            <button
              type="submit"
              disabled={searching || !query.trim() || !trialId.trim()}
              className="absolute right-1.5 top-1.5 bottom-1.5 px-4 rounded-md bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition inline-flex items-center gap-1.5"
            >
              {searching ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Searching...</span>
                </>
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" />
                  <span>Retrieve</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Quick Suggestion Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium text-slate-500">Suggested Clinical Queries:</span>
          {sampleQueries.map((q, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setQuery(q)}
              className={`text-xs px-2.5 py-1 rounded-md border transition ${
                query === q
                  ? 'bg-indigo-50 border-indigo-300 text-indigo-700 font-medium'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300'
              }`}
            >
              {q}
            </button>
          ))}
        </div>
      </form>

      {/* Error Message */}
      {searchError && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-start gap-2 mb-6">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <strong>Search Error:</strong> {searchError}
          </div>
        </div>
      )}

      {/* Retrieved Evidence Results */}
      {searchResults !== null && (
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h3 className="text-xs font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Grounded Protocol Evidence ({searchResults.length} chunks retrieved)</span>
            </h3>
            <span className="text-[11px] text-slate-500">
              Ranked by Cosine Similarity
            </span>
          </div>

          {searchResults.length === 0 ? (
            <div className="text-center py-8 bg-slate-50 rounded-lg border border-dashed border-slate-200">
              <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-60" />
              <p className="text-xs font-medium text-slate-600">
                No matching evidence chunks found for this trial protocol.
              </p>
              <p className="text-[11px] text-slate-400 mt-1">
                The RAG pipeline never hallucinates criteria. If unmentioned in the protocol, zero evidence is returned.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {searchResults.map((result, idx) => {
                const isExclusion = result.criterion_type?.toLowerCase() === 'exclusion';
                const isInclusion = result.criterion_type?.toLowerCase() === 'inclusion';
                const scorePercent = Math.round(result.similarity_score * 100);

                return (
                  <div
                    key={result.chunk_id || idx}
                    className="p-4 rounded-lg border border-slate-200 bg-white hover:border-indigo-200 transition shadow-xs space-y-2.5"
                  >
                    {/* Top Metadata Badges */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {/* Criterion Type Pill */}
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                            isExclusion
                              ? 'bg-rose-50 text-rose-700 border-rose-200'
                              : isInclusion
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-slate-100 text-slate-700 border-slate-200'
                          }`}
                        >
                          {result.criterion_type ? result.criterion_type.toUpperCase() : 'PROTOCOL EVIDENCE'}
                        </span>

                        {/* Page Number Citation */}
                        {result.page_number && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
                            <FileText className="w-3 h-3" />
                            <span>Page {result.page_number}</span>
                          </span>
                        )}

                        {/* Section Header */}
                        {result.section && (
                          <span className="text-[11px] text-slate-500 font-medium truncate max-w-xs">
                            {result.section}
                          </span>
                        )}
                      </div>

                      {/* Similarity Score Pill */}
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] text-slate-400 font-medium">Relevance:</span>
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded-full font-mono ${
                            result.similarity_score >= 0.75
                              ? 'bg-emerald-100 text-emerald-800'
                              : result.similarity_score >= 0.5
                              ? 'bg-indigo-100 text-indigo-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {scorePercent}% (score: {result.similarity_score.toFixed(4)})
                        </span>
                      </div>
                    </div>

                    {/* Verbatim Clinical Text */}
                    <div className="p-3 bg-slate-50 rounded border border-slate-100 font-sans text-xs text-slate-800 leading-relaxed whitespace-pre-line">
                      {result.text}
                    </div>

                    {/* Evidence Traceability Footnote */}
                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 font-mono">
                      <span>Chunk: {result.chunk_id}</span>
                      <span className="text-slate-500">Trial: {result.trial_id}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
