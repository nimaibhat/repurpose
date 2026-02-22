'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';
import { supabase } from '@/lib/supabase';

const WaveField = dynamic(() => import('@/components/WaveField'), { ssr: false });

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// ─── Data ────────────────────────────────────────────────────────────────────

const CANCER_TYPES = [
  'Pancreatic Cancer',
  'Breast Cancer',
  'Lung Cancer (NSCLC)',
  'Lung Cancer (SCLC)',
  'Colorectal Cancer',
  'Melanoma',
  'Glioblastoma',
  'Prostate Cancer',
  'Ovarian Cancer',
  'Acute Myeloid Leukemia',
  'Multiple Myeloma',
  'Hepatocellular Carcinoma',
  'Renal Cell Carcinoma',
  'Bladder Cancer',
  'Gastric Cancer',
];

const PROTEIN_TARGETS = [
  'EGFR', 'KRAS', 'BRAF', 'TP53', 'HER2',
  'ALK', 'PIK3CA', 'PTEN', 'RB1', 'MYC',
];

const LOADING_STEPS = [
  'Discovering protein targets...',
  'Fetching 3D protein structure...',
  'Searching drug candidates...',
  'Running DiffDock AI simulations...',
  'Generating analysis report...',
];

type FocusMode = 'explore' | 'target';
type Status = 'idle' | 'loading' | 'done' | 'error';

interface DockingResult {
  drug_name: string | null;
  smiles: string;
  confidence_score: number;
  ligand_sdf: string;
  num_poses: number;
  mechanism?: string | null;
  max_phase?: number | null;
}

interface PipelineResult {
  disease: string;
  targets: { ensembl_id: string; symbol: string; name: string; score: number }[];
  structures: { symbol: string; pdb_id: string; resolution: number | null; source: string }[];
  drugs: { chembl_id: string; name: string | null; smiles: string; max_phase: number; mechanism: string | null }[];
  docking_results: DockingResult[];
  report: string;
}

// ─── Searchable Dropdown ─────────────────────────────────────────────────────

function SearchDropdown({
  options, value, onChange, placeholder, allowFreeText = false,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  allowFreeText?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = options.filter((o) => o.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const select = useCallback((v: string) => { onChange(v); setQuery(''); setOpen(false); }, [onChange]);

  return (
    <div ref={ref} className="relative">
      <div
        className="flex items-center gap-3 w-full px-4 py-3.5 rounded-lg border border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15] focus-within:border-white/20 transition-colors duration-300 cursor-text"
        onClick={() => { setOpen(true); inputRef.current?.focus(); }}
      >
        <svg className="w-4 h-4 text-white/25 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          className="flex-1 bg-transparent outline-none text-sm text-white/80 placeholder:text-white/45 font-light"
          placeholder={value || placeholder}
          value={open ? query : value}
          onChange={(e) => { setQuery(e.target.value); if (!open) setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && allowFreeText && query.trim()) select(query.trim());
            if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); }
          }}
        />
        {value && (
          <button className="text-white/20 hover:text-white/50 transition-colors" onClick={(e) => { e.stopPropagation(); onChange(''); setQuery(''); }}>
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
        <svg className={`w-3.5 h-3.5 text-white/20 transition-transform duration-200 shrink-0 ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 mt-1.5 w-full max-h-56 overflow-y-auto rounded-lg border border-white/[0.08] bg-[#0d0e13]/95 backdrop-blur-xl shadow-2xl"
          >
            {filtered.length > 0 ? filtered.map((option) => (
              <button
                key={option}
                className={`w-full text-left px-4 py-2.5 text-sm font-light transition-colors duration-150 ${option === value ? 'text-white/90 bg-white/[0.06]' : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'}`}
                onClick={() => select(option)}
              >{option}</button>
            )) : (
              <div className="px-4 py-3 text-sm text-white/25 font-light">
                {allowFreeText ? 'Press Enter to use custom value' : 'No results found'}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Focus Mode Icons ─────────────────────────────────────────────────────────

function ExploreIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
    </svg>
  );
}

function TargetIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" fill="currentColor" />
      <line x1="12" y1="2" x2="12" y2="5" /><line x1="12" y1="19" x2="12" y2="22" />
      <line x1="2" y1="12" x2="5" y2="12" /><line x1="19" y1="12" x2="22" y2="12" />
    </svg>
  );
}

// ─── Focus Mode Card ──────────────────────────────────────────────────────────

function FocusModeCard({ icon: Icon, label, subtitle, selected, onClick }: {
  icon: React.FC<{ className?: string }>;
  label: string; subtitle: string; selected: boolean; onClick: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      className={`relative flex-1 flex flex-col items-center gap-2.5 px-4 py-5 rounded-xl border transition-colors duration-300 cursor-pointer ${selected ? 'border-blue-500/30 bg-blue-500/[0.06]' : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]'}`}
      whileTap={{ scale: 0.98 }}
    >
      {selected && (
        <motion.div layoutId="focus-glow" className="absolute inset-0 rounded-xl border border-blue-500/20"
          style={{ boxShadow: '0 0 20px rgba(59, 130, 246, 0.08), inset 0 0 20px rgba(59, 130, 246, 0.03)' }}
          transition={{ type: 'spring', bounce: 0.2, duration: 0.6 }}
        />
      )}
      <Icon className={`w-5 h-5 transition-colors duration-300 ${selected ? 'text-blue-400/80' : 'text-white/30'}`} />
      <span className={`text-xs font-light tracking-wide transition-colors duration-300 ${selected ? 'text-white/90' : 'text-white/50'}`}>{label}</span>
      <span className={`text-[10px] font-light transition-colors duration-300 ${selected ? 'text-white/40' : 'text-white/20'}`}>{subtitle}</span>
    </motion.button>
  );
}

// ─── Loading State ────────────────────────────────────────────────────────────

function LoadingPanel() {
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setStepIdx((i) => Math.min(i + 1, LOADING_STEPS.length - 1)), 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-[560px] mx-4 flex flex-col items-center gap-8"
    >
      <div className="w-8 h-8 rounded-full border border-white/10 border-t-white/50 animate-spin" />
      <div className="text-center space-y-3">
        <AnimatePresence mode="wait">
          <motion.p
            key={stepIdx}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.4 }}
            className="text-sm font-light text-white/60 tracking-wide"
          >
            {LOADING_STEPS[stepIdx]}
          </motion.p>
        </AnimatePresence>
        <div className="flex gap-1.5 justify-center">
          {LOADING_STEPS.map((_, i) => (
            <div key={i} className={`h-px transition-all duration-500 ${i <= stepIdx ? 'w-6 bg-blue-400/60' : 'w-3 bg-white/10'}`} />
          ))}
        </div>
      </div>
      <p className="text-[0.65rem] tracking-[0.15em] uppercase text-white/20 font-light">
        AI docking simulations may take 1–3 minutes
      </p>
    </motion.div>
  );
}

// ─── Results Panel ────────────────────────────────────────────────────────────

function ResultsPanel({ results, onReset }: { results: PipelineResult; onReset: () => void }) {
  const topTarget = results.targets[0];
  const structure = results.structures[0];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="w-full max-w-[720px] mx-4 space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="text-[0.65rem] tracking-[0.2em] uppercase text-white/25 font-light mb-1">Results for</p>
          <h2 className="text-xl font-extralight text-white/90 tracking-wide">{results.disease}</h2>
        </div>
        <button
          onClick={onReset}
          className="text-[0.65rem] tracking-[0.15em] uppercase text-white/25 hover:text-white/50 transition-colors font-light border border-white/[0.06] px-3 py-1.5 rounded-lg hover:border-white/[0.12]"
        >
          New search
        </button>
      </div>

      {/* Target + Structure */}
      {topTarget && (
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 backdrop-blur-xl">
          <p className="text-[0.6rem] tracking-[0.15em] uppercase text-white/25 font-light mb-3">Top Protein Target</p>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-lg font-light text-white/90 tracking-wider">{topTarget.symbol}</span>
              <p className="text-xs text-white/40 font-light mt-0.5">{topTarget.name}</p>
            </div>
            <div className="text-right">
              <span className="text-xs text-white/30 font-light">Association score</span>
              <p className="text-sm text-blue-400/80 font-light">{topTarget.score.toFixed(3)}</p>
            </div>
          </div>
          {structure && (
            <div className="mt-3 pt-3 border-t border-white/[0.05] flex items-center gap-2">
              <span className="text-[0.6rem] tracking-[0.12em] uppercase text-white/20 font-light">Structure</span>
              <span className="text-xs text-white/50 font-light">{structure.pdb_id}</span>
              <span className={`text-[0.55rem] tracking-wider uppercase px-1.5 py-0.5 rounded border font-light ${structure.source === 'rcsb' ? 'border-green-500/20 text-green-400/60' : 'border-purple-500/20 text-purple-400/60'}`}>
                {structure.source === 'rcsb' ? 'RCSB' : 'AlphaFold'}
              </span>
              {structure.resolution && (
                <span className="text-[0.6rem] text-white/20 font-light ml-auto">{structure.resolution}Å</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Docking Results */}
      {results.docking_results.length > 0 && (
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 backdrop-blur-xl">
          <p className="text-[0.6rem] tracking-[0.15em] uppercase text-white/25 font-light mb-4">
            Drug Candidates — ranked by binding confidence
          </p>
          <div className="space-y-2.5">
            {results.docking_results.slice(0, 8).map((r, i) => {
              const score = r.confidence_score;
              const pct = Math.max(0, Math.min(100, ((score + 10) / 15) * 100));
              return (
                <div key={i} className="flex items-center gap-4 py-2.5 border-b border-white/[0.04] last:border-0">
                  <span className="text-[0.65rem] text-white/20 font-light w-4 shrink-0">#{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-light text-white/80">{r.drug_name || 'Unknown'}</span>
                      {r.max_phase && (
                        <span className="text-[0.55rem] tracking-wider uppercase px-1.5 py-0.5 rounded border border-white/[0.08] text-white/30 font-light">
                          Phase {r.max_phase}
                        </span>
                      )}
                    </div>
                    {r.mechanism && (
                      <p className="text-[0.65rem] text-white/30 font-light truncate">{r.mechanism}</p>
                    )}
                    <div className="mt-1.5 h-px bg-white/[0.06] rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.8, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                        className="h-full bg-blue-400/50 rounded-full"
                      />
                    </div>
                  </div>
                  <span className={`text-sm font-light shrink-0 ${score > 0 ? 'text-green-400/70' : score > -2 ? 'text-blue-400/70' : 'text-white/40'}`}>
                    {score.toFixed(3)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Claude Report */}
      {results.report && !results.report.startsWith('No docking') && !results.report.startsWith('Report generation failed') && (
        <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 backdrop-blur-xl">
          <p className="text-[0.6rem] tracking-[0.15em] uppercase text-white/25 font-light mb-4">AI Analysis Report</p>
          <div className="text-xs text-white/50 font-light leading-relaxed whitespace-pre-wrap">
            {results.report}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ResearchPage() {
  const router = useRouter();
  const [cancerType, setCancerType] = useState('');
  const [focusMode, setFocusMode] = useState<FocusMode>('explore');
  const [proteinTarget, setProteinTarget] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [maxTargets, setMaxTargets] = useState(5);
  const [maxCandidates, setMaxCandidates] = useState(25);

  const [status, setStatus] = useState<Status>('idle');
  const [results, setResults] = useState<PipelineResult | null>(null);
  const [error, setError] = useState('');
  const [recentProteins, setRecentProteins] = useState<string[]>([]);

  useEffect(() => {
    async function fetchRecentProteins() {
      const { data, error } = await supabase
        .from('protein_registry')
        .select('display_name, target_id')
        .order('created_at', { ascending: false })
        .limit(3);

      if (!error && data && data.length > 0) {
        setRecentProteins(
          data.map((r) => r.display_name).filter(Boolean) as string[]
        );
      }
    }
    fetchRecentProteins();
  }, []);

  const handleRunAnalysis = () => {
    // Target-Specific mode: route to the protein-first pipeline
    if (focusMode === 'target') {
      if (!proteinTarget) return;
      const params = new URLSearchParams({
        target_symbol: proteinTarget,
        max_candidates: String(maxCandidates),
      });
      router.push(`/pipeline/protein?${params.toString()}`);
      return;
    }

    // Explore / Drug-Specific modes: route to the standard disease pipeline
    if (!cancerType) return;
    const params = new URLSearchParams({
      disease: cancerType,
      mode: focusMode,
      max_targets: String(maxTargets),
      max_candidates: String(maxCandidates),
    });
    router.push(`/pipeline?${params.toString()}`);
  };

  const showForm = status === 'idle' || status === 'error';
  const reset = () => { setStatus('idle'); setResults(null); };

  return (
    <div className={`relative w-screen bg-[#0a0b0f] ${status === 'done' ? 'min-h-screen' : 'h-screen overflow-hidden'}`}>
      {/* Shader background */}
      <div className="fixed inset-0 z-0 opacity-[0.55]">
        <WaveField speed={0.6} intensity={2.0} />
      </div>
      <div className="fixed inset-0 z-[1] bg-[#0a0b0f]/40" />

      {/* Navbar */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-5">
        <span className="text-[0.8rem] font-extralight tracking-[0.35em] uppercase text-white/60">repurpose</span>
      </nav>

      {/* Content */}
      <div className={`relative z-10 flex justify-center ${status === 'done' ? 'pt-8 pb-16' : 'items-start h-[calc(100vh-72px)] pt-[8vh]'}`}>
        <AnimatePresence mode="wait">

          {/* Form */}
          {showForm && (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-[560px] mx-4"
            >
              <div
                className="rounded-2xl border border-white/[0.08] p-8 backdrop-blur-xl"
                style={{
                  background: 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
                  boxShadow: '0 0 80px rgba(0,0,0,0.5), 0 0 1px rgba(255,255,255,0.05)',
                }}
              >
                <motion.h2 className="text-[1.35rem] font-extralight text-white/90 mb-6 tracking-wide"
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }}>
                  What cancer are you researching?
                </motion.h2>

                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.3 }}>
                  <SearchDropdown options={CANCER_TYPES} value={cancerType} onChange={setCancerType} placeholder="Search or select cancer type..." allowFreeText />
                </motion.div>

                {/* Error */}
                {status === 'error' && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-4 px-4 py-3 rounded-lg border border-red-500/20 bg-red-500/[0.05]">
                    <p className="text-xs text-red-400/80 font-light">{error}</p>
                  </motion.div>
                )}

                {/* Focus Mode */}
                <motion.div className="mt-7" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.4 }}>
                  <p className="text-[0.65rem] font-light tracking-[0.15em] uppercase text-white/25 mb-3">Focus Mode</p>
                  <div className="flex gap-2.5">
                    <FocusModeCard icon={ExploreIcon} label="Explore" subtitle="All repurposing candidates" selected={focusMode === 'explore'} onClick={() => setFocusMode('explore')} />
                    <FocusModeCard icon={TargetIcon} label="Target-Specific" subtitle="Test against a protein" selected={focusMode === 'target'} onClick={() => setFocusMode('target')} />
                  </div>
                </motion.div>

                {/* Conditional secondary inputs */}
                <AnimatePresence mode="wait">
                  {focusMode === 'target' && (
                    <motion.div key="target-input" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
                      <div className="mt-5">
                        <p className="text-[0.65rem] font-light tracking-[0.15em] uppercase text-white/25 mb-2.5">Protein Target</p>
                        <SearchDropdown
                          options={[
                            // Recent proteins from Supabase first; fall back to
                            // hardcoded list when the registry is empty.
                            ...recentProteins,
                            // Append hardcoded entries that aren't already in recent list
                            ...PROTEIN_TARGETS.filter((t) => !recentProteins.includes(t)),
                          ]}
                          value={proteinTarget}
                          onChange={setProteinTarget}
                          placeholder="Select protein target..."
                        />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Advanced Settings */}
                <motion.div className="mt-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.5 }}>
                  <button className="flex items-center gap-2 text-[0.65rem] font-light tracking-[0.15em] uppercase text-white/20 hover:text-white/40 transition-colors duration-300 cursor-pointer" onClick={() => setAdvancedOpen(!advancedOpen)}>
                    <motion.svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} animate={{ rotate: advancedOpen ? 90 : 0 }} transition={{ duration: 0.2 }}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </motion.svg>
                    Advanced Settings
                  </button>
                  <AnimatePresence>
                    {advancedOpen && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
                        <div className="mt-4 space-y-6 pl-1">

                          {/* Max Targets */}
                          <div>
                            <div className="flex items-center justify-between mb-2.5">
                              <p className="text-[0.6rem] font-light tracking-[0.12em] uppercase text-white/20">Max Targets</p>
                              <input
                                type="number"
                                min={1}
                                max={200}
                                value={maxTargets}
                                onChange={(e) => setMaxTargets(Math.min(200, Math.max(1, parseInt(e.target.value) || 1)))}
                                className="w-14 px-2 py-1 rounded-md border border-white/[0.08] bg-white/[0.03] text-xs font-mono text-white/60 text-center focus:outline-none focus:border-white/20 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
                              />
                            </div>
                            <input
                              type="range"
                              min={1}
                              max={200}
                              value={maxTargets}
                              onChange={(e) => setMaxTargets(parseInt(e.target.value))}
                              className="w-full h-0.5 appearance-none rounded-full cursor-pointer accent-blue-500"
                              style={{ background: `linear-gradient(to right, rgba(59,130,246,0.5) ${(maxTargets - 1) / 199 * 100}%, rgba(255,255,255,0.08) ${(maxTargets - 1) / 199 * 100}%)` }}
                            />
                            <div className="flex justify-between mt-1">
                              <span className="text-[0.5rem] text-white/15 font-mono">1</span>
                              <span className="text-[0.5rem] text-white/15 font-mono">200</span>
                            </div>
                          </div>

                          {/* Max Candidates */}
                          <div>
                            <div className="flex items-center justify-between mb-2.5">
                              <p className="text-[0.6rem] font-light tracking-[0.12em] uppercase text-white/20">Max Candidates to Dock</p>
                              <div className="flex items-center gap-2">
                                {maxCandidates !== 0 && (
                                  <input
                                    type="number"
                                    min={1}
                                    value={maxCandidates}
                                    onChange={(e) => setMaxCandidates(Math.max(1, parseInt(e.target.value) || 1))}
                                    className="w-14 px-2 py-1 rounded-md border border-white/[0.08] bg-white/[0.03] text-xs font-mono text-white/60 text-center focus:outline-none focus:border-white/20 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
                                  />
                                )}
                                <button
                                  onClick={() => setMaxCandidates(maxCandidates === 0 ? 25 : 0)}
                                  className={`px-3 py-1 rounded-md text-[0.6rem] font-light tracking-wide border transition-all duration-300 cursor-pointer ${maxCandidates === 0 ? 'border-blue-500/25 bg-blue-500/[0.08] text-blue-400/70' : 'border-white/[0.05] text-white/25 hover:text-white/40 hover:border-white/[0.1]'}`}
                                >
                                  Any
                                </button>
                              </div>
                            </div>
                            {maxCandidates !== 0 && (
                              <>
                                <input
                                  type="range"
                                  min={1}
                                  max={100}
                                  value={Math.min(maxCandidates, 100)}
                                  onChange={(e) => setMaxCandidates(parseInt(e.target.value))}
                                  className="w-full h-0.5 appearance-none rounded-full cursor-pointer accent-blue-500"
                                  style={{ background: `linear-gradient(to right, rgba(59,130,246,0.5) ${(Math.min(maxCandidates, 100) - 1) / 99 * 100}%, rgba(255,255,255,0.08) ${(Math.min(maxCandidates, 100) - 1) / 99 * 100}%)` }}
                                />
                                <div className="flex justify-between mt-1">
                                  <span className="text-[0.5rem] text-white/15 font-mono">1</span>
                                  <span className="text-[0.5rem] text-white/15 font-mono">100+</span>
                                </div>
                              </>
                            )}
                            {maxCandidates === 0 && (
                              <p className="text-[0.6rem] text-white/20 font-light mt-1">All available candidates will be docked</p>
                            )}
                          </div>

                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>

                {/* Run Analysis Button */}
                <motion.div
                  className="mt-8"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.6 }}
                >
                  <motion.button
                    className={`relative w-full py-4 rounded-xl text-base font-light tracking-[0.15em] uppercase overflow-hidden border ${
                      (focusMode === 'target' ? !!proteinTarget : !!cancerType)
                        ? 'text-white/90 cursor-pointer border-blue-500/20 bg-blue-500/[0.08]'
                        : 'text-white/45 cursor-not-allowed border-white/[0.06] bg-white/[0.02]'
                    }`}
                    whileHover={(focusMode === 'target' ? !!proteinTarget : !!cancerType) ? { scale: 1.005 } : undefined}
                    whileTap={(focusMode === 'target' ? !!proteinTarget : !!cancerType) ? { scale: 0.995 } : undefined}
                    style={
                      (focusMode === 'target' ? !!proteinTarget : !!cancerType)
                        ? { boxShadow: '0 0 30px rgba(59, 130, 246, 0.12), 0 0 60px rgba(59, 130, 246, 0.05)' }
                        : undefined
                    }
                    onClick={handleRunAnalysis}
                    disabled={!(focusMode === 'target' ? !!proteinTarget : !!cancerType)}
                  >
                    <span className="relative z-10">Run Analysis</span>
                    {(focusMode === 'target' ? !!proteinTarget : !!cancerType) && (
                      <div className="absolute inset-0 bg-gradient-to-r from-blue-600/10 via-blue-500/15 to-blue-600/10" />
                    )}
                  </motion.button>
                </motion.div>
              </div>
            </motion.div>
          )}

          {/* Loading */}
          {status === 'loading' && <LoadingPanel key="loading" />}

          {/* Results */}
          {status === 'done' && results && <ResultsPanel key="results" results={results} onReset={reset} />}

        </AnimatePresence>
      </div>
    </div>
  );
}
