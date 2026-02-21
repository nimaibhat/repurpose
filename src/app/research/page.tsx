'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';

const WaveField = dynamic(() => import('@/components/WaveField'), { ssr: false });

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

const DRUG_SUGGESTIONS = [
  'Imatinib', 'Sorafenib', 'Metformin', 'Thalidomide', 'Celecoxib',
  'Disulfiram', 'Chloroquine', 'Ivermectin', 'Niclosamide', 'Auranofin',
  'Mebendazole', 'Statins', 'Aspirin', 'Valproic Acid', 'Rapamycin',
];

type FocusMode = 'explore' | 'target' | 'drug';

// ─── Searchable Dropdown ─────────────────────────────────────────────────────

function SearchDropdown({
  options,
  value,
  onChange,
  placeholder,
  allowFreeText = false,
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

  const filtered = options.filter((o) =>
    o.toLowerCase().includes(query.toLowerCase()),
  );

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const select = useCallback(
    (v: string) => {
      onChange(v);
      setQuery('');
      setOpen(false);
    },
    [onChange],
  );

  return (
    <div ref={ref} className="relative">
      <div
        className="flex items-center gap-3 w-full px-4 py-3.5 rounded-lg border border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15] focus-within:border-white/20 transition-colors duration-300 cursor-text"
        onClick={() => {
          setOpen(true);
          inputRef.current?.focus();
        }}
      >
        <svg
          className="w-4 h-4 text-white/45 shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
          />
        </svg>
        <input
          ref={inputRef}
          type="text"
          className="flex-1 bg-transparent outline-none text-sm text-white/80 placeholder:text-white/45 font-light"
          placeholder={value || placeholder}
          value={open ? query : value}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!open) setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && allowFreeText && query.trim()) {
              select(query.trim());
            }
            if (e.key === 'Escape') {
              setOpen(false);
              inputRef.current?.blur();
            }
          }}
        />
        {value && (
          <button
            className="text-white/60 hover:text-white/50 transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onChange('');
              setQuery('');
            }}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
        <svg
          className={`w-3.5 h-3.5 text-white/60 transition-transform duration-200 shrink-0 ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 mt-1.5 w-full max-h-56 overflow-y-auto rounded-lg border border-white/[0.08] bg-[#0d0e13]/95 backdrop-blur-xl shadow-2xl"
          >
            {filtered.length > 0 ? (
              filtered.map((option) => (
                <button
                  key={option}
                  className={`w-full text-left px-4 py-2.5 text-sm font-light transition-colors duration-150 ${
                    option === value
                      ? 'text-white/90 bg-white/[0.06]'
                      : 'text-white/50 hover:text-white/80 hover:bg-white/[0.04]'
                  }`}
                  onClick={() => select(option)}
                >
                  {option}
                </button>
              ))
            ) : (
              <div className="px-4 py-3 text-sm text-white/45 font-light">
                {allowFreeText
                  ? 'Press Enter to use custom value'
                  : 'No results found'}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Focus Mode Icons ────────────────────────────────────────────────────────

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
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
      <line x1="12" y1="2" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="2" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="22" y2="12" />
    </svg>
  );
}

function PillIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.745 19.255a4.5 4.5 0 010-6.364l9.192-9.192a4.5 4.5 0 116.364 6.364l-9.192 9.192a4.5 4.5 0 01-6.364 0z" />
      <line x1="8.5" y1="8.5" x2="15.5" y2="15.5" strokeLinecap="round" />
    </svg>
  );
}

// ─── Focus Mode Card ─────────────────────────────────────────────────────────

function FocusModeCard({
  icon: Icon,
  label,
  subtitle,
  selected,
  onClick,
}: {
  icon: React.FC<{ className?: string }>;
  label: string;
  subtitle: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      className={`relative flex-1 flex flex-col items-center gap-2.5 px-4 py-5 rounded-xl border transition-colors duration-300 cursor-pointer ${
        selected
          ? 'border-blue-500/30 bg-blue-500/[0.06]'
          : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]'
      }`}
      whileTap={{ scale: 0.98 }}
    >
      {selected && (
        <motion.div
          layoutId="focus-glow"
          className="absolute inset-0 rounded-xl border border-blue-500/20"
          style={{
            boxShadow: '0 0 20px rgba(59, 130, 246, 0.08), inset 0 0 20px rgba(59, 130, 246, 0.03)',
          }}
          transition={{ type: 'spring', bounce: 0.2, duration: 0.6 }}
        />
      )}
      <Icon className={`w-5 h-5 transition-colors duration-300 ${selected ? 'text-blue-400/80' : 'text-white/50'}`} />
      <span className={`text-sm font-light tracking-wide transition-colors duration-300 ${selected ? 'text-white/90' : 'text-white/50'}`}>
        {label}
      </span>
      <span className={`text-xs font-light transition-colors duration-300 ${selected ? 'text-white/60' : 'text-white/60'}`}>
        {subtitle}
      </span>
    </motion.button>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function ResearchPage() {
  const router = useRouter();
  const [cancerType, setCancerType] = useState('');
  const [focusMode, setFocusMode] = useState<FocusMode>('explore');
  const [proteinTarget, setProteinTarget] = useState('');
  const [drugName, setDrugName] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [admetStrict, setAdmetStrict] = useState(true);
  const [maxTargets, setMaxTargets] = useState(5);
  const [maxCandidates, setMaxCandidates] = useState(25);

  const handleRunAnalysis = () => {
    if (!cancerType) return;
    const params = new URLSearchParams({
      disease: cancerType,
      mode: focusMode,
      max_targets: String(maxTargets),
      max_candidates: String(maxCandidates),
    });
    if (focusMode === 'target' && proteinTarget) {
      params.set('target_symbol', proteinTarget);
    }
    if (focusMode === 'drug' && drugName) {
      params.set('drug_name', drugName);
    }
    router.push(`/pipeline?${params.toString()}`);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#0a0b0f]">
      {/* Shader background — dimmed */}
      <div className="fixed inset-0 z-0 opacity-[0.55]">
        <WaveField speed={0.6} intensity={2.0} />
      </div>

      {/* Dark overlay to further tame the shader */}
      <div className="fixed inset-0 z-[1] bg-[#0a0b0f]/40" />

      {/* Navbar */}
      <nav className="relative z-10 flex items-center justify-between px-10 py-6">
        <span className="text-base font-extralight tracking-[0.35em] uppercase text-white/60">
          repurpose
        </span>
      </nav>

      {/* Center content */}
      <div className="relative z-10 flex items-start justify-center h-[calc(100vh-72px)] pt-[8vh]">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-2xl mx-4"
        >
          {/* Input Card */}
          <div
            className="rounded-2xl border border-white/[0.08] p-8 backdrop-blur-xl"
            style={{
              background: 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
              boxShadow: '0 0 80px rgba(0,0,0,0.5), 0 0 1px rgba(255,255,255,0.05)',
            }}
          >
            {/* Headline */}
            <motion.h2
              className="text-2xl font-extralight text-white/90 mb-6 tracking-wide"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
            >
              What cancer are you researching?
            </motion.h2>

            {/* Cancer type selector */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
            >
              <SearchDropdown
                options={CANCER_TYPES}
                value={cancerType}
                onChange={setCancerType}
                placeholder="Search or select cancer type..."
                allowFreeText
              />
            </motion.div>

            {/* Focus Mode */}
            <motion.div
              className="mt-7"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
            >
              <p className="text-sm font-light tracking-[0.15em] uppercase text-white/45 mb-3">
                Focus Mode
              </p>
              <div className="flex gap-2.5">
                <FocusModeCard
                  icon={ExploreIcon}
                  label="Explore"
                  subtitle="All repurposing candidates"
                  selected={focusMode === 'explore'}
                  onClick={() => setFocusMode('explore')}
                />
                <FocusModeCard
                  icon={TargetIcon}
                  label="Target-Specific"
                  subtitle="Test against a protein"
                  selected={focusMode === 'target'}
                  onClick={() => setFocusMode('target')}
                />
                <FocusModeCard
                  icon={PillIcon}
                  label="Drug-Specific"
                  subtitle="Test a drug on all targets"
                  selected={focusMode === 'drug'}
                  onClick={() => setFocusMode('drug')}
                />
              </div>
            </motion.div>

            {/* Conditional secondary inputs */}
            <AnimatePresence mode="wait">
              {focusMode === 'target' && (
                <motion.div
                  key="target-input"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <div className="mt-5">
                    <p className="text-sm font-light tracking-[0.15em] uppercase text-white/45 mb-2.5">
                      Protein Target
                    </p>
                    <SearchDropdown
                      options={PROTEIN_TARGETS}
                      value={proteinTarget}
                      onChange={setProteinTarget}
                      placeholder="Select protein target..."
                    />
                  </div>
                </motion.div>
              )}

              {focusMode === 'drug' && (
                <motion.div
                  key="drug-input"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <div className="mt-5">
                    <p className="text-sm font-light tracking-[0.15em] uppercase text-white/45 mb-2.5">
                      Drug Name
                    </p>
                    <SearchDropdown
                      options={DRUG_SUGGESTIONS}
                      value={drugName}
                      onChange={setDrugName}
                      placeholder="Enter drug name..."
                      allowFreeText
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Advanced Settings */}
            <motion.div
              className="mt-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.5 }}
            >
              <button
                className="flex items-center gap-2 text-sm font-light tracking-[0.15em] uppercase text-white/60 hover:text-white/60 transition-colors duration-300 cursor-pointer"
                onClick={() => setAdvancedOpen(!advancedOpen)}
              >
                <motion.svg
                  className="w-3 h-3"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                  animate={{ rotate: advancedOpen ? 90 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </motion.svg>
                Advanced Settings
              </button>

              <AnimatePresence>
                {advancedOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="mt-4 space-y-5 pl-1">
                      {/* ADMET Strictness */}
                      <div>
                        <p className="text-xs font-light tracking-[0.12em] uppercase text-white/60 mb-2.5">
                          ADMET Strictness
                        </p>
                        <div className="flex gap-2">
                          {(['Strict', 'Relaxed'] as const).map((opt) => {
                            const isActive = opt === 'Strict' ? admetStrict : !admetStrict;
                            return (
                              <button
                                key={opt}
                                className={`px-5 py-2.5 rounded-lg text-sm font-light tracking-wide border transition-all duration-300 cursor-pointer ${
                                  isActive
                                    ? 'border-white/15 bg-white/[0.06] text-white/70'
                                    : 'border-white/[0.05] bg-transparent text-white/45 hover:text-white/60 hover:border-white/[0.1]'
                                }`}
                                onClick={() => setAdmetStrict(opt === 'Strict')}
                              >
                                {opt}
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      {/* Max Targets */}
                      <div>
                        <p className="text-xs font-light tracking-[0.12em] uppercase text-white/60 mb-2.5">
                          Target Proteins to Fetch
                        </p>
                        <div className="flex items-center gap-2 mb-3">
                          {[3, 5, 10, 25].map((n) => (
                            <button
                              key={n}
                              className={`px-4 py-2 rounded-lg text-sm font-light tracking-wide border transition-all duration-300 cursor-pointer ${
                                maxTargets === n
                                  ? 'border-white/15 bg-white/[0.06] text-white/70'
                                  : 'border-white/[0.05] bg-transparent text-white/45 hover:text-white/60 hover:border-white/[0.1]'
                                }`}
                              onClick={() => setMaxTargets(n)}
                            >
                              {n}
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-3">
                          <input
                            type="range"
                            min={1}
                            max={200}
                            value={maxTargets}
                            onChange={(e) => setMaxTargets(parseInt(e.target.value, 10))}
                            className="flex-1 h-1 appearance-none bg-white/[0.08] rounded-full cursor-pointer accent-blue-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-400"
                          />
                          <span className="text-sm font-mono font-light text-white/50 tabular-nums w-8 text-right">
                            {maxTargets}
                          </span>
                        </div>
                      </div>

                      {/* Max Candidates */}
                      <div>
                        <p className="text-xs font-light tracking-[0.12em] uppercase text-white/60 mb-2.5">
                          Max Candidates to Dock
                        </p>
                        <div className="flex items-center gap-2 mb-3">
                          {[10, 25, 50, 100].map((n) => (
                            <button
                              key={n}
                              className={`px-4 py-2 rounded-lg text-sm font-light tracking-wide border transition-all duration-300 cursor-pointer ${
                                maxCandidates === n
                                  ? 'border-white/15 bg-white/[0.06] text-white/70'
                                  : 'border-white/[0.05] bg-transparent text-white/45 hover:text-white/60 hover:border-white/[0.1]'
                                }`}
                              onClick={() => setMaxCandidates(n)}
                            >
                              {n}
                            </button>
                          ))}
                          <button
                            className={`px-4 py-2 rounded-lg text-sm font-light tracking-wide border transition-all duration-300 cursor-pointer ${
                              maxCandidates === 9999
                                ? 'border-white/15 bg-white/[0.06] text-white/70'
                                : 'border-white/[0.05] bg-transparent text-white/45 hover:text-white/60 hover:border-white/[0.1]'
                              }`}
                            onClick={() => setMaxCandidates(9999)}
                          >
                            All
                          </button>
                        </div>
                        {maxCandidates !== 9999 && (
                          <div className="flex items-center gap-3">
                            <input
                              type="range"
                              min={5}
                              max={200}
                              value={maxCandidates}
                              onChange={(e) => setMaxCandidates(parseInt(e.target.value, 10))}
                              className="flex-1 h-1 appearance-none bg-white/[0.08] rounded-full cursor-pointer accent-blue-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-400"
                            />
                            <span className="text-sm font-mono font-light text-white/50 tabular-nums w-8 text-right">
                              {maxCandidates}
                            </span>
                          </div>
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
                  cancerType
                    ? 'text-white/90 cursor-pointer border-blue-500/20 bg-blue-500/[0.08]'
                    : 'text-white/45 cursor-not-allowed border-white/[0.06] bg-white/[0.02]'
                }`}
                whileHover={cancerType ? { scale: 1.005 } : undefined}
                whileTap={cancerType ? { scale: 0.995 } : undefined}
                style={
                  cancerType
                    ? { boxShadow: '0 0 30px rgba(59, 130, 246, 0.12), 0 0 60px rgba(59, 130, 246, 0.05)' }
                    : undefined
                }
                onClick={handleRunAnalysis}
                disabled={!cancerType}
              >
                <span className="relative z-10">Run Analysis</span>
                {cancerType && (
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-600/10 via-blue-500/15 to-blue-600/10" />
                )}
              </motion.button>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
