'use client';

import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DashboardViewer from '@/components/DashboardViewer';
import type { DashboardViewerHandle, ProteinStyle } from '@/components/DashboardViewer';

const WaveField = dynamic(() => import('@/components/WaveField'), { ssr: false });
const MoleculeCard = dynamic(() => import('@/components/MoleculeCard'), { ssr: false });
const ConfidenceHeatmap = dynamic(() => import('@/components/ConfidenceHeatmap'), { ssr: false });

// ─── Types ──────────────────────────────────────────────────────────────────

interface Candidate {
  rank: number;
  drug_name: string;
  smiles: string;
  confidence_score: number;
  mechanism?: string;
  explanation?: string;
  risk_benefit?: string;
  max_phase?: number;
}

interface DockingEntry {
  drug_name: string;
  ligand_sdf: string;
}

interface DockingResultFull {
  drug_name: string | null;
  smiles: string;
  confidence_score: number;
  ligand_sdf: string;
  pdb_id: string;
  target_symbol: string;
}

interface ResultsData {
  disease: string;
  target: { symbol: string; name: string; pdb_id: string };
  candidates: Candidate[];
  docking_data: DockingEntry[];
  pdb_text: string;
  report: string;
  // Multi-target data (optional — present when from batch pipeline)
  all_targets?: { symbol: string; name: string; score: number }[];
  all_docking_results?: DockingResultFull[];
}

type SortMode = 'confidence' | 'alphabetical' | 'phase';
type DetailTab = 'explanation' | 'mechanism' | 'report';
type ViewMode = 'list' | 'heatmap';

// ─── Constants ──────────────────────────────────────────────────────────────

const ease = [0.16, 1, 0.3, 1] as const;

const glassStyle = {
  background: 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
  boxShadow: '0 0 80px rgba(0,0,0,0.5), 0 0 1px rgba(255,255,255,0.05)',
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function scoreLargeTextClass(score: number): string {
  if (score >= 0.7) return 'text-emerald-400';
  if (score >= 0.4) return 'text-yellow-400';
  return 'text-red-400';
}

function scoreBg(score: number): string {
  if (score >= 0.7) return 'bg-emerald-500';
  if (score >= 0.4) return 'bg-yellow-500';
  return 'bg-red-500';
}

function sortCandidates(candidates: Candidate[], mode: SortMode): Candidate[] {
  const sorted = [...candidates];
  switch (mode) {
    case 'confidence':
      return sorted.sort((a, b) => b.confidence_score - a.confidence_score);
    case 'alphabetical':
      return sorted.sort((a, b) => (a.drug_name || '').localeCompare(b.drug_name || ''));
    case 'phase':
      return sorted.sort((a, b) => (b.max_phase || 0) - (a.max_phase || 0));
  }
}

// ─── Mechanism Flow Diagram ─────────────────────────────────────────────────

function MechanismFlow({
  drugName,
  targetSymbol,
  mechanism,
  disease,
}: {
  drugName: string;
  targetSymbol: string;
  mechanism?: string;
  disease: string;
}) {
  const nodes = [
    { label: drugName, color: 'blue', sub: 'Drug' },
    { label: targetSymbol, color: 'emerald', sub: 'Protein Target' },
    { label: mechanism || 'Signaling Pathway', color: 'orange', sub: 'Pathway' },
    { label: disease, color: 'red', sub: 'Cancer' },
  ];

  const edges = ['inhibits', 'part of', 'drives'];

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-4 px-2">
      {nodes.map((node, i) => (
        <div key={i} className="contents">
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: i * 0.12, ease }}
            className="shrink-0 flex flex-col items-center gap-1.5"
          >
            <div
              className={`px-4 py-3 rounded-xl border text-center min-w-[100px] ${
                node.color === 'blue'
                  ? 'border-blue-500/25 bg-blue-500/[0.08]'
                  : node.color === 'emerald'
                  ? 'border-emerald-500/25 bg-emerald-500/[0.08]'
                  : node.color === 'orange'
                  ? 'border-orange-500/25 bg-orange-500/[0.08]'
                  : 'border-red-500/25 bg-red-500/[0.08]'
              }`}
            >
              <p
                className={`text-xs font-light truncate max-w-[120px] ${
                  node.color === 'blue'
                    ? 'text-blue-400/90'
                    : node.color === 'emerald'
                    ? 'text-emerald-400/90'
                    : node.color === 'orange'
                    ? 'text-orange-400/90'
                    : 'text-red-400/90'
                }`}
              >
                {node.label}
              </p>
            </div>
            <span className="text-xs font-light text-white/20 tracking-wide uppercase">
              {node.sub}
            </span>
          </motion.div>

          {i < nodes.length - 1 && (
            <motion.div
              initial={{ opacity: 0, scaleX: 0 }}
              animate={{ opacity: 1, scaleX: 1 }}
              transition={{ duration: 0.3, delay: i * 0.12 + 0.2, ease }}
              className="shrink-0 flex flex-col items-center gap-0.5 mx-1"
            >
              <svg className="w-8 h-4 text-white/15" viewBox="0 0 32 16" fill="none">
                <path d="M0 8h24m0 0l-6-5m6 5l-6 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-xs font-light text-white/15 italic">{edges[i]}</span>
            </motion.div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Viewer Controls ────────────────────────────────────────────────────────

function ViewerControls({
  proteinStyle,
  onStyleChange,
  ligandVisible,
  onToggleLigand,
  onReset,
}: {
  proteinStyle: ProteinStyle;
  onStyleChange: (s: ProteinStyle) => void;
  ligandVisible: boolean;
  onToggleLigand: () => void;
  onReset: () => void;
}) {
  const styles: { value: ProteinStyle; label: string }[] = [
    { value: 'cartoon', label: 'Cartoon' },
    { value: 'surface', label: 'Surface' },
    { value: 'ballstick', label: 'Ball & Stick' },
  ];

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Protein style toggles */}
      {styles.map((s) => (
        <button
          key={s.value}
          onClick={() => onStyleChange(s.value)}
          className={`px-3.5 py-2 rounded-lg text-xs font-light tracking-wide border transition-all duration-300 ${
            proteinStyle === s.value
              ? 'border-blue-500/25 bg-blue-500/[0.08] text-blue-400/80'
              : 'border-white/[0.06] bg-white/[0.02] text-white/30 hover:text-white/50 hover:border-white/[0.1]'
          }`}
        >
          {s.label}
        </button>
      ))}

      <div className="w-px h-4 bg-white/[0.06] mx-1" />

      {/* Ligand toggle */}
      <button
        onClick={onToggleLigand}
        className={`px-3.5 py-2 rounded-lg text-xs font-light tracking-wide border transition-all duration-300 ${
          ligandVisible
            ? 'border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-400/70'
            : 'border-white/[0.06] bg-white/[0.02] text-white/30 hover:text-white/50'
        }`}
      >
        {ligandVisible ? 'Hide Ligand' : 'Show Ligand'}
      </button>

      {/* Reset view */}
      <button
        onClick={onReset}
        className="px-3.5 py-2 rounded-lg text-xs font-light tracking-wide border border-white/[0.06] bg-white/[0.02] text-white/30 hover:text-white/50 hover:border-white/[0.1] transition-all duration-300"
      >
        Reset View
      </button>
    </div>
  );
}

// ─── Tab Bar ────────────────────────────────────────────────────────────────

function TabBar({ active, onChange }: { active: DetailTab; onChange: (t: DetailTab) => void }) {
  const tabs: { value: DetailTab; label: string }[] = [
    { value: 'explanation', label: 'Explanation' },
    { value: 'mechanism', label: 'Mechanism' },
    { value: 'report', label: 'Full Report' },
  ];

  return (
    <div className="flex gap-1 p-1 rounded-lg bg-white/[0.02] border border-white/[0.05]">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={`relative px-5 py-2.5 rounded-md text-sm font-light tracking-wide transition-all duration-300 ${
            active === t.value
              ? 'text-white/80'
              : 'text-white/30 hover:text-white/50'
          }`}
        >
          {active === t.value && (
            <motion.div
              layoutId="active-tab"
              className="absolute inset-0 rounded-md bg-white/[0.06] border border-white/[0.08]"
              transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
            />
          )}
          <span className="relative z-10">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

// ─── Results Content ────────────────────────────────────────────────────────

function ResultsContent() {
  const router = useRouter();
  const viewerRef = useRef<DashboardViewerHandle>(null);
  const [data, setData] = useState<ResultsData | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [sortMode, setSortMode] = useState<SortMode>('confidence');
  const [proteinStyle, setProteinStyle] = useState<ProteinStyle>('cartoon');
  const [ligandVisible, setLigandVisible] = useState(true);
  const [activeTab, setActiveTab] = useState<DetailTab>('explanation');
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('list');

  // Load data from sessionStorage
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('pipeline_results');
      if (!raw) {
        router.replace('/research');
        return;
      }
      const parsed = JSON.parse(raw) as ResultsData;
      if (!parsed.candidates?.length) {
        router.replace('/research');
        return;
      }
      setData(parsed);
    } catch {
      router.replace('/research');
    }
  }, [router]);

  // Sorted candidates
  const sorted = data ? sortCandidates(data.candidates, sortMode) : [];
  const selected = sorted[selectedIdx] || sorted[0];

  // Find docking data for selected candidate
  const selectedDocking = data?.docking_data?.find(
    (d) => d.drug_name === selected?.drug_name,
  );

  // Update viewer ligand when selection changes
  const handleSelect = useCallback((idx: number) => {
    setSelectedIdx(idx);
    const candidate = sorted[idx];
    if (!candidate || !data) return;
    const docking = data.docking_data?.find((d) => d.drug_name === candidate.drug_name);
    viewerRef.current?.setLigand(docking?.ligand_sdf || null);
  }, [sorted, data]);

  // Viewer controls
  const handleStyleChange = useCallback((style: ProteinStyle) => {
    setProteinStyle(style);
    viewerRef.current?.setProteinStyle(style);
  }, []);

  const handleToggleLigand = useCallback(() => {
    const next = !ligandVisible;
    setLigandVisible(next);
    viewerRef.current?.setLigandVisible(next);
  }, [ligandVisible]);

  const handleReset = useCallback(() => {
    viewerRef.current?.resetView();
  }, []);

  // Copy report to clipboard
  const handleCopyReport = useCallback(async () => {
    if (!data?.report) return;
    try {
      await navigator.clipboard.writeText(data.report);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    } catch {
      // Fallback
    }
  }, [data?.report]);

  // Download report as text (PDF would require a server-side library)
  const handleDownloadReport = useCallback(() => {
    if (!data?.report) return;
    const blob = new Blob([data.report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `repurpose-report-${data.disease.toLowerCase().replace(/\s+/g, '-')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [data]);

  // Heatmap cell click — find matching candidate and select it
  const handleHeatmapClick = useCallback(
    (_target: string, drug: string) => {
      const idx = sorted.findIndex((c) => c.drug_name === drug);
      if (idx >= 0) handleSelect(idx);
    },
    [sorted, handleSelect],
  );

  // Derive heatmap data — use multi-target data when available
  const heatmapTargets = data?.all_targets?.length
    ? data.all_targets.map((t) => t.symbol)
    : data ? [data.target.symbol] : [];

  // Build a unique drug list from docking results (preserving order by best score)
  const allDockingResults = data?.all_docking_results || [];
  const seenDrugs = new Set<string>();
  const heatmapDrugs: string[] = [];
  if (allDockingResults.length > 0) {
    for (const dr of allDockingResults) {
      const name = dr.drug_name || 'Unknown';
      if (!seenDrugs.has(name)) {
        seenDrugs.add(name);
        heatmapDrugs.push(name);
      }
    }
  } else {
    sorted.forEach((c) => heatmapDrugs.push(c.drug_name || 'Unknown'));
  }

  // Build 2D score matrix: scores[targetIdx][drugIdx]
  const heatmapScores: number[][] = heatmapTargets.map((target) =>
    heatmapDrugs.map((drug) => {
      if (allDockingResults.length > 0) {
        const match = allDockingResults.find(
          (dr) => dr.target_symbol === target && (dr.drug_name || 'Unknown') === drug,
        );
        return match?.confidence_score ?? 0;
      }
      // Fallback: single-target mode
      const candidate = sorted.find((c) => (c.drug_name || 'Unknown') === drug);
      return candidate?.confidence_score ?? 0;
    }),
  );

  if (!data) {
    return (
      <div className="w-screen h-screen bg-[#0a0b0f] flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#0a0b0f]">
      {/* Shader background — very dim for dense UI */}
      <div className="fixed inset-0 z-0 opacity-[0.25]">
        <WaveField speed={0.2} intensity={1.2} />
      </div>
      <div className="fixed inset-0 z-[1] bg-[#0a0b0f]/60" />

      {/* Layout */}
      <div className="relative z-10 flex flex-col h-screen">
        {/* ── Top Bar ── */}
        <motion.nav
          className="flex items-center justify-between px-6 py-4 border-b border-white/[0.05] shrink-0"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease }}
        >
          {/* Left: back */}
          <button
            onClick={() => router.push('/research')}
            className="flex items-center gap-2 text-sm font-light tracking-[0.15em] uppercase text-white/35 hover:text-white/60 transition-colors duration-300"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            New Search
          </button>

          {/* Center: title */}
          <div className="flex items-center gap-2">
            <span className="text-base font-light text-white/70">{data.disease}</span>
            <span className="text-white/15">&mdash;</span>
            <span className="text-base font-light text-blue-400/70">{data.target.symbol}</span>
            <span className="text-xs font-light text-white/25">({data.target.name})</span>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadReport}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-white/[0.08] bg-white/[0.03] text-xs font-light tracking-wide text-white/40 hover:text-white/60 hover:border-white/[0.15] transition-all duration-300"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
              Export Report
            </button>
            <button
              onClick={handleCopyReport}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-white/[0.08] bg-white/[0.03] text-xs font-light tracking-wide text-white/40 hover:text-white/60 hover:border-white/[0.15] transition-all duration-300"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
              </svg>
              {copyFeedback ? 'Copied!' : 'Share'}
            </button>
          </div>
        </motion.nav>

        {/* ── Main Content ── */}
        <div className="flex-1 flex overflow-hidden">
          {/* ── LEFT PANEL: Candidate List ── */}
          <motion.aside
            className="w-[35%] min-w-[320px] max-w-[440px] border-r border-white/[0.05] flex flex-col"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease }}
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/[0.04] shrink-0">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <h2 className="text-base font-light text-white/70">Drug Candidates</h2>
                  <span className="px-3 py-1 rounded-full bg-white/[0.05] text-xs font-light text-white/35 tabular-nums">
                    {data.candidates.length} results
                  </span>
                </div>

                {/* View toggle: List / Heatmap */}
                <div className="flex gap-1 p-0.5 rounded-md bg-white/[0.02] border border-white/[0.05]">
                  {(['list', 'heatmap'] as ViewMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      className={`relative px-3.5 py-1.5 rounded text-xs font-light capitalize tracking-wide transition-all duration-300 ${
                        viewMode === mode ? 'text-white/70' : 'text-white/25 hover:text-white/40'
                      }`}
                    >
                      {viewMode === mode && (
                        <motion.div
                          layoutId="view-mode-bg"
                          className="absolute inset-0 rounded bg-white/[0.06] border border-white/[0.08]"
                          transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                        />
                      )}
                      <span className="relative z-10">{mode}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Sort — only visible in list mode */}
              {viewMode === 'list' && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-light text-white/20 tracking-wide uppercase">Sort by:</span>
                  {(['confidence', 'alphabetical', 'phase'] as SortMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => { setSortMode(mode); setSelectedIdx(0); }}
                      className={`px-3 py-1.5 rounded-md text-xs font-light capitalize transition-all duration-300 ${
                        sortMode === mode
                          ? 'bg-white/[0.06] text-white/60 border border-white/[0.1]'
                          : 'text-white/25 hover:text-white/40 border border-transparent'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Content: Card list or Heatmap */}
            <div className="flex-1 overflow-y-auto px-4 py-3 scrollbar-thin">
              <AnimatePresence mode="wait">
                {viewMode === 'list' ? (
                  <motion.div
                    key="list-view"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-2"
                  >
                    {sorted.map((c, i) => (
                      <motion.div
                        key={c.drug_name || c.rank}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3, delay: i * 0.03, ease }}
                        layout
                      >
                        <MoleculeCard
                          smiles={c.smiles}
                          drugName={c.drug_name || 'Unknown Drug'}
                          confidence={c.confidence_score}
                          phase={c.max_phase}
                          rank={c.rank}
                          mechanism={c.mechanism}
                          selected={i === selectedIdx}
                          onClick={() => handleSelect(i)}
                          size="medium"
                        />
                      </motion.div>
                    ))}
                  </motion.div>
                ) : (
                  <motion.div
                    key="heatmap-view"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <ConfidenceHeatmap
                      targets={heatmapTargets}
                      drugs={heatmapDrugs}
                      scores={heatmapScores}
                      onCellClick={handleHeatmapClick}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.aside>

          {/* ── RIGHT PANEL: Detail View ── */}
          <motion.main
            className="flex-1 flex flex-col overflow-hidden"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease }}
          >
            {/* Section 1: 3D Viewer */}
            <div className="shrink-0 p-5 pb-3">
              <div
                className="rounded-2xl border border-white/[0.06] p-4 backdrop-blur-sm"
                style={glassStyle}
              >
                {/* Viewer + Confidence badge */}
                <div className="relative">
                  {data.pdb_text && (
                    <div className="w-full aspect-[3/2]">
                      <DashboardViewer
                        ref={viewerRef}
                        pdbText={data.pdb_text}
                        initialLigandSdf={selectedDocking?.ligand_sdf}
                        initialProteinStyle={proteinStyle}
                        height="100%"
                      />
                    </div>
                  )}

                  {/* Confidence overlay badge */}
                  {selected && (
                    <div className="absolute top-3 right-3 flex items-center gap-2 px-3 py-2 rounded-xl bg-black/60 backdrop-blur-md border border-white/[0.08]">
                      <span className="text-xs font-light text-white/35 tracking-wide uppercase">
                        Binding Confidence
                      </span>
                      <span
                        className={`text-lg font-light tabular-nums ${scoreLargeTextClass(selected.confidence_score)}`}
                      >
                        {selected.confidence_score.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="mt-3">
                  <ViewerControls
                    proteinStyle={proteinStyle}
                    onStyleChange={handleStyleChange}
                    ligandVisible={ligandVisible}
                    onToggleLigand={handleToggleLigand}
                    onReset={handleReset}
                  />
                </div>
              </div>
            </div>

            {/* Section 2: AI Explanation */}
            <div className="flex-1 overflow-hidden px-5 pb-5 flex flex-col">
              <div
                className="flex-1 rounded-2xl border border-white/[0.06] backdrop-blur-sm flex flex-col overflow-hidden"
                style={glassStyle}
              >
                {/* Tab bar */}
                <div className="px-4 pt-4 pb-3 shrink-0 flex items-center justify-between">
                  <TabBar active={activeTab} onChange={setActiveTab} />

                  {/* Drug name label */}
                  {selected && (
                    <motion.div
                      key={selected.drug_name}
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="flex items-center gap-2"
                    >
                      <span className="text-sm font-light text-white/50">{selected.drug_name}</span>
                      <span className={`w-1.5 h-1.5 rounded-full ${scoreBg(selected.confidence_score)}`} />
                    </motion.div>
                  )}
                </div>

                {/* Tab content */}
                <div className="flex-1 overflow-y-auto px-5 pb-5">
                  <AnimatePresence mode="wait">
                    {activeTab === 'explanation' && selected && (
                      <motion.div
                        key={`explanation-${selected.drug_name}`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.3, ease }}
                      >
                        {/* Explanation text */}
                        <div className="text-base font-light text-white/60 leading-relaxed">
                          {selected.explanation ? (
                            <p>{selected.explanation}</p>
                          ) : (
                            <p className="text-white/25 italic">No AI explanation available for this candidate.</p>
                          )}
                        </div>

                        {/* Risk/Benefit section */}
                        {selected.risk_benefit && (
                          <div className="mt-5 pt-4 border-t border-white/[0.05]">
                            <p className="text-xs font-light tracking-[0.15em] uppercase text-white/25 mb-3">
                              Risk / Benefit Summary
                            </p>
                            <div className="text-base font-light text-white/50 leading-relaxed">
                              {selected.risk_benefit}
                            </div>
                          </div>
                        )}
                      </motion.div>
                    )}

                    {activeTab === 'mechanism' && selected && (
                      <motion.div
                        key={`mechanism-${selected.drug_name}`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.3, ease }}
                      >
                        <p className="text-xs font-light tracking-[0.15em] uppercase text-white/25 mb-2">
                          Interaction Pathway
                        </p>
                        <MechanismFlow
                          drugName={selected.drug_name}
                          targetSymbol={data.target.symbol}
                          mechanism={selected.mechanism}
                          disease={data.disease}
                        />
                        {selected.mechanism && (
                          <div className="mt-4 p-3 rounded-xl border border-white/[0.05] bg-white/[0.015]">
                            <p className="text-xs font-light text-white/25 uppercase tracking-wide mb-1.5">
                              Mechanism of Action
                            </p>
                            <p className="text-sm font-light text-white/50 leading-relaxed">
                              {selected.mechanism}
                            </p>
                          </div>
                        )}
                      </motion.div>
                    )}

                    {activeTab === 'report' && (
                      <motion.div
                        key="report"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.3, ease }}
                      >
                        {/* Action buttons */}
                        <div className="flex items-center gap-2 mb-4">
                          <button
                            onClick={handleCopyReport}
                            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-white/[0.08] bg-white/[0.03] text-xs font-light text-white/35 hover:text-white/55 hover:border-white/[0.12] transition-all duration-300"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                            </svg>
                            {copyFeedback ? 'Copied!' : 'Copy Report'}
                          </button>
                          <button
                            onClick={handleDownloadReport}
                            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-white/[0.08] bg-white/[0.03] text-xs font-light text-white/35 hover:text-white/55 hover:border-white/[0.12] transition-all duration-300"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                            </svg>
                            Download as Markdown
                          </button>
                        </div>

                        {/* Markdown rendered report */}
                        <div className="prose prose-invert prose-sm max-w-none
                          prose-headings:font-light prose-headings:text-white/70 prose-headings:tracking-wide
                          prose-p:text-white/50 prose-p:font-light prose-p:leading-relaxed
                          prose-strong:text-white/70 prose-strong:font-normal
                          prose-li:text-white/50 prose-li:font-light
                          prose-code:text-blue-400/70 prose-code:bg-white/[0.04] prose-code:rounded prose-code:px-1 prose-code:py-0.5
                          prose-hr:border-white/[0.06]
                          prose-a:text-blue-400/70 prose-a:no-underline hover:prose-a:text-blue-400
                          prose-th:text-white/50 prose-th:font-light prose-th:border-white/[0.08]
                          prose-td:text-white/40 prose-td:font-light prose-td:border-white/[0.06]
                        ">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {data.report || '*No report generated.*'}
                          </ReactMarkdown>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            </div>
          </motion.main>
        </div>
      </div>
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="w-screen h-screen bg-[#0a0b0f] flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
        </div>
      }
    >
      <ResultsContent />
    </Suspense>
  );
}
