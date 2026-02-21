'use client';

import { useEffect, useRef, useState, useCallback, useReducer, useMemo, Suspense } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams, useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';

import PipelineStepper from '@/components/PipelineStepper';

const WaveField = dynamic(() => import('@/components/WaveField'), { ssr: false });
const MolViewer = dynamic(() => import('@/components/MolViewer'), { ssr: false });
const MoleculeCard = dynamic(() => import('@/components/MoleculeCard'), { ssr: false });

// ─── Types ──────────────────────────────────────────────────────────────────

interface TargetHit {
  ensembl_id: string;
  symbol: string;
  name: string;
  score: number;
}

interface Structure {
  symbol: string;
  pdb_id: string;
  resolution: number | null;
  source: string;
  file_path: string;
}

interface Drug {
  name: string | null;
  smiles: string;
  max_phase: number;
  mechanism: string | null;
  target_symbol: string;
  target_chembl_id?: string;
}

interface DockingResult {
  drug_name: string | null;
  smiles: string;
  confidence_score: number;
  ligand_sdf: string;
  num_poses?: number;
  pdb_id: string;
  target_symbol: string;
  explanation?: string;
  risk_benefit?: string;
  priority_rank?: number;
}

interface PipelineResponse {
  disease: string;
  targets: TargetHit[];
  structures: Structure[];
  drugs: Drug[];
  docking_results: DockingResult[];
  report: string;
}

// ─── SSE Reducer ────────────────────────────────────────────────────────────

type StepStatus = 'pending' | 'running' | 'complete' | 'error';

interface PipelineState {
  stepStatuses: StepStatus[];
  stepData: Array<Record<string, any> | null>;
  error: string | null;
  isDone: boolean;
}

type PipelineAction =
  | { type: 'STEP_RUNNING'; step: number }
  | { type: 'STEP_COMPLETE'; step: number; data: Record<string, any> }
  | { type: 'STEP_ERROR'; step: number; message: string }
  | { type: 'DONE'; step: number; data: Record<string, any> }
  | { type: 'FETCH_ERROR'; message: string };

const initialState: PipelineState = {
  stepStatuses: ['pending', 'pending', 'pending', 'pending', 'pending'],
  stepData: [null, null, null, null, null],
  error: null,
  isDone: false,
};

function pipelineReducer(state: PipelineState, action: PipelineAction): PipelineState {
  switch (action.type) {
    case 'STEP_RUNNING': {
      const stepStatuses = [...state.stepStatuses];
      stepStatuses[action.step - 1] = 'running';
      return { ...state, stepStatuses };
    }
    case 'STEP_COMPLETE': {
      const stepStatuses = [...state.stepStatuses];
      const stepData = [...state.stepData];
      stepStatuses[action.step - 1] = 'complete';
      stepData[action.step - 1] = action.data;
      return { ...state, stepStatuses, stepData };
    }
    case 'STEP_ERROR': {
      const stepStatuses = [...state.stepStatuses];
      stepStatuses[action.step - 1] = 'error';
      return { ...state, stepStatuses, error: action.message };
    }
    case 'DONE': {
      const stepStatuses = [...state.stepStatuses];
      const stepData = [...state.stepData];
      stepStatuses[action.step - 1] = 'complete';
      stepData[action.step - 1] = action.data;
      return { ...state, stepStatuses, stepData, isDone: true };
    }
    case 'FETCH_ERROR':
      return { ...state, error: action.message };
    default:
      return state;
  }
}

// ─── Constants ──────────────────────────────────────────────────────────────

const STEP_LABELS = ['Targets', 'Structures', 'Drugs', 'Docking', 'Report'];
const STEP_ICONS = ['crosshair', 'box', 'pill', 'flask-conical', 'file-text'];
const STEP_SUB_MESSAGES: string[][] = [
  ['Querying Open Targets database...', 'Ranking disease-gene associations...'],
  ['Searching RCSB PDB database...', 'Downloading protein structures...', 'Trying AlphaFold fallback...'],
  ['Querying ChEMBL database...', 'Finding approved compounds...', 'Extracting molecular data...'],
  ['Preparing protein-ligand pairs...', 'Running DiffDock simulations...', 'Scoring binding poses...', 'Computing confidence scores...'],
  ['Analyzing top docking results...', 'Generating AI-powered report...', 'Formatting recommendations...'],
];

const ease = [0.16, 1, 0.3, 1] as const;

const glassStyle = {
  background: 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
  boxShadow: '0 0 80px rgba(0,0,0,0.5), 0 0 1px rgba(255,255,255,0.05)',
};

// ─── SSE Parser ─────────────────────────────────────────────────────────────

async function consumeSSEStream(
  response: Response,
  dispatch: React.Dispatch<PipelineAction>,
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on double-newline boundaries (SSE event delimiter)
    const parts = buffer.split('\n\n');
    buffer = parts.pop()!; // keep incomplete trailing chunk

    for (const part of parts) {
      if (!part.trim()) continue;

      let eventType = 'message';
      let dataStr = '';

      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          dataStr += line.slice(6);
        }
      }

      if (!dataStr) continue;

      let payload: any;
      try {
        payload = JSON.parse(dataStr);
      } catch {
        continue;
      }

      const { step, status, data, message } = payload;

      if (eventType === 'done') {
        dispatch({ type: 'DONE', step, data });
      } else if (status === 'running') {
        dispatch({ type: 'STEP_RUNNING', step });
      } else if (status === 'complete') {
        dispatch({ type: 'STEP_COMPLETE', step, data });
      } else if (status === 'error') {
        dispatch({ type: 'STEP_ERROR', step, message });
      }
    }
  }
}

// ─── Step Card Shell ────────────────────────────────────────────────────────

function StepCard({
  label,
  index,
  status,
  message,
  children,
}: {
  label: string;
  index: number;
  status: 'pending' | 'running' | 'complete' | 'error';
  message: string;
  children?: React.ReactNode;
}) {
  if (status === 'pending') return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.1, ease }}
      className="rounded-2xl border border-white/[0.08] p-6 backdrop-blur-xl"
      style={glassStyle}
    >
      <div className="flex items-center gap-3 mb-3">
        <div
          className={`w-6 h-6 rounded-full flex items-center justify-center text-[0.55rem] font-light ${
            status === 'running'
              ? 'bg-blue-500/[0.12] text-blue-400'
              : status === 'complete'
              ? 'bg-emerald-500/[0.1] text-emerald-400'
              : 'bg-red-500/[0.1] text-red-400'
          }`}
        >
          {index + 1}
        </div>
        <span className="text-[0.65rem] font-light tracking-[0.15em] uppercase text-white/40">
          {label}
        </span>
        {status === 'running' && (
          <motion.div
            className="ml-auto flex items-center gap-1.5"
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          >
            <div className="w-1 h-1 rounded-full bg-blue-400" />
            <span className="text-[0.6rem] font-light text-blue-400/70">Processing</span>
          </motion.div>
        )}
      </div>
      <p className="text-sm font-light text-white/60 leading-relaxed">{message}</p>
      {children && <div className="mt-4">{children}</div>}
    </motion.div>
  );
}

// ─── Pipeline Content ───────────────────────────────────────────────────────

function PipelineContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // Parse params
  const disease = searchParams.get('disease') || '';
  const mode = searchParams.get('mode') || 'explore';
  const targetSymbol = searchParams.get('target_symbol') || '';
  const drugName = searchParams.get('drug_name') || '';
  const maxCandidates = parseInt(searchParams.get('max_candidates') || '25', 10);

  // SSE-driven state
  const [state, dispatch] = useReducer(pipelineReducer, initialState);

  // UI state
  const [pdbText, setPdbText] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [selectedDocking, setSelectedDocking] = useState(0);
  const [subMsgIndex, setSubMsgIndex] = useState(0);

  const hasStarted = useRef(false);
  const startTimeRef = useRef(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasStoredResults = useRef(false);

  // Redirect if missing params
  useEffect(() => {
    if (!disease) router.replace('/research');
  }, [disease, router]);

  // Elapsed timer
  useEffect(() => {
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  // Stop timer when done or errored
  useEffect(() => {
    if ((state.isDone || state.error) && timerRef.current) clearInterval(timerRef.current);
  }, [state.isDone, state.error]);

  // Cycle sub-messages for running steps
  useEffect(() => {
    if (state.isDone || state.error) return;
    const interval = setInterval(() => setSubMsgIndex((i) => i + 1), 4000);
    return () => clearInterval(interval);
  }, [state.isDone, state.error]);

  // SSE stream fetch
  useEffect(() => {
    if (!disease || hasStarted.current) return;
    hasStarted.current = true;

    const abortController = new AbortController();

    (async () => {
      try {
        const resp = await fetch('http://localhost:8000/api/pipeline/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            disease,
            mode,
            target_symbol: targetSymbol || undefined,
            drug_name: drugName || undefined,
            max_candidates: maxCandidates,
          }),
          signal: abortController.signal,
        });

        if (!resp.ok) {
          const detail = await resp.text().catch(() => '');
          dispatch({ type: 'FETCH_ERROR', message: `Server error ${resp.status}: ${detail}` });
          return;
        }

        await consumeSSEStream(resp, dispatch);
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          dispatch({ type: 'FETCH_ERROR', message: err.message || 'Connection failed' });
        }
      }
    })();

    return () => {
      abortController.abort();
      hasStarted.current = false;
    };
  }, [disease, mode, targetSymbol, drugName, maxCandidates]);

  // Reconstruct full result from accumulated step data
  const result = useMemo<PipelineResponse | null>(() => {
    if (!state.isDone) return null;
    const [s1, s2, s3, s4, s5] = state.stepData;
    if (!s1 || !s2 || !s3 || !s4 || !s5) return null;
    return {
      disease: s1.disease,
      targets: s1.targets,
      structures: s2.structures,
      drugs: s3.drugs,
      // Step 5 (done) returns enriched docking_results with explanations
      docking_results: s5.docking_results || s4.docking_results,
      report: s5.report,
    };
  }, [state.isDone, state.stepData]);

  // Fetch PDB text from RCSB when structures arrive
  const fetchPdb = useCallback(async (pdbId: string) => {
    const url = pdbId.startsWith('AF-')
      ? `https://alphafold.ebi.ac.uk/files/${pdbId}-model_v4.pdb`
      : `https://files.rcsb.org/download/${pdbId}.pdb`;
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`PDB fetch failed: ${resp.status}`);
      setPdbText(await resp.text());
    } catch {
      // Best-effort — 3D viewer just won't show
    }
  }, []);

  // Trigger PDB fetch as soon as structures step completes
  useEffect(() => {
    if (pdbText) return;
    const structData = state.stepData[1];
    if (!structData?.structures?.length) return;
    const topStructure = structData.structures[0];
    if (topStructure?.pdb_id) fetchPdb(topStructure.pdb_id);
  }, [state.stepData, pdbText, fetchPdb]);

  // Step status & message helpers
  const stepStatus = (i: number): StepStatus => state.stepStatuses[i];

  const stepMessage = (i: number): string => {
    const s = stepStatus(i);
    if (s === 'error') return state.error || 'An error occurred';
    if (s === 'running') {
      const msgs = STEP_SUB_MESSAGES[i];
      return msgs[subMsgIndex % msgs.length];
    }
    if (s === 'complete') {
      const d = state.stepData[i];
      if (d) {
        switch (i) {
          case 0: return `Found ${d.targets.length} target${d.targets.length !== 1 ? 's' : ''}: ${d.targets.map((t: any) => t.symbol).join(', ')}`;
          case 1: return `Retrieved ${d.structures.length} structure${d.structures.length !== 1 ? 's' : ''}`;
          case 2: return `Found ${d.drugs.length} drug candidate${d.drugs.length !== 1 ? 's' : ''}`;
          case 3: return `Docked ${d.docking_results.length} compound${d.docking_results.length !== 1 ? 's' : ''} successfully`;
          case 4: return 'Report generated';
        }
      }
      return 'Complete';
    }
    return '';
  };

  // Progressive data accessors — render from stepData as it arrives
  const targetsData: TargetHit[] = state.stepData[0]?.targets || [];
  const structuresData: Structure[] = state.stepData[1]?.structures || [];
  const drugsData: Drug[] = state.stepData[2]?.drugs || [];
  const dockingData: DockingResult[] = (state.stepData[4]?.docking_results || state.stepData[3]?.docking_results || []);

  // Build candidates from progressive data
  const drugMap = useMemo(() => {
    const m = new Map<string, Drug>();
    drugsData.forEach((d) => { if (d.name) m.set(d.name, d); });
    return m;
  }, [drugsData]);

  const candidates = useMemo(() => {
    return dockingData.map((dr: DockingResult, i: number) => {
      const drug = drugMap.get(dr.drug_name || '');
      return {
        rank: i + 1,
        drug_name: dr.drug_name || 'Unknown',
        smiles: dr.smiles,
        confidence_score: dr.confidence_score,
        mechanism: drug?.mechanism || undefined,
        max_phase: drug?.max_phase,
        explanation: dr.explanation || '',
        risk_benefit: dr.risk_benefit || '',
      };
    });
  }, [dockingData, drugMap]);

  const dockingViewData = useMemo(() => {
    return dockingData.map((dr: DockingResult) => ({
      drug_name: dr.drug_name || 'Unknown',
      ligand_sdf: dr.ligand_sdf,
    }));
  }, [dockingData]);

  // Store results in sessionStorage for the results page
  useEffect(() => {
    if (!result || hasStoredResults.current) return;
    hasStoredResults.current = true;

    const topTarget = result.targets[0];
    const topStructure = result.structures[0];

    const payload = {
      disease: result.disease,
      target: {
        symbol: topTarget?.symbol || '',
        name: topTarget?.name || '',
        pdb_id: topStructure?.pdb_id || '',
      },
      candidates,
      docking_data: dockingViewData,
      pdb_text: pdbText || '',
      report: result.report,
      all_targets: result.targets,
      all_structures: result.structures,
      all_drugs: result.drugs,
      all_docking_results: result.docking_results,
    };

    try {
      sessionStorage.setItem('pipeline_results', JSON.stringify(payload));
    } catch {
      // sessionStorage might be full; best-effort
    }
  }, [result, pdbText, candidates, dockingViewData]);

  // Re-store when pdbText arrives (it may come after the result)
  useEffect(() => {
    if (!result || !pdbText || !hasStoredResults.current) return;
    try {
      const raw = sessionStorage.getItem('pipeline_results');
      if (raw) {
        const data = JSON.parse(raw);
        data.pdb_text = pdbText;
        sessionStorage.setItem('pipeline_results', JSON.stringify(data));
      }
    } catch { /* best-effort */ }
  }, [pdbText, result]);

  // Timer string
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const timerStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  const isDone = state.isDone || !!state.error;

  if (!disease) return null;

  return (
    <div className="relative w-screen min-h-screen bg-[#0a0b0f]">
      {/* Shader background */}
      <div className="fixed inset-0 z-0 opacity-[0.55]">
        <WaveField speed={0.6} intensity={2.0} />
      </div>
      <div className="fixed inset-0 z-[1] bg-[#0a0b0f]/40" />

      {/* Content */}
      <div className="relative z-10 min-h-screen">
        {/* Top Bar */}
        <motion.nav
          className="flex items-center justify-between px-8 py-5"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease }}
        >
          <button
            onClick={() => router.push('/research')}
            className="flex items-center gap-2 text-[0.7rem] font-light tracking-[0.15em] uppercase text-white/40 hover:text-white/70 transition-colors duration-300"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            New Search
          </button>

          <div className="flex items-center gap-4">
            <span className="px-3 py-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] text-[0.6rem] font-light text-white/50 tracking-wide">
              {disease}
              {mode !== 'explore' && (
                <span className="text-white/25 ml-1.5">
                  {mode === 'target' ? `/ ${targetSymbol}` : `/ ${drugName}`}
                </span>
              )}
            </span>
            <span
              className={`font-mono text-sm font-light tabular-nums ${
                isDone ? 'text-white/30' : 'text-blue-400/70'
              }`}
            >
              {timerStr}
            </span>
          </div>
        </motion.nav>

        {/* Stepper Row */}
        <motion.div
          className="max-w-2xl mx-auto px-8 mt-4 mb-10"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <PipelineStepper
            steps={STEP_LABELS.map((name, i) => ({
              name,
              icon: STEP_ICONS[i],
              status: stepStatus(i),
              message: stepStatus(i) === 'complete' ? stepMessage(i) : undefined,
            }))}
          />
        </motion.div>

        {/* Error */}
        {state.error && (
          <motion.div
            className="max-w-2xl mx-auto px-8 mb-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="rounded-2xl border border-red-500/20 bg-red-500/[0.05] p-6 backdrop-blur-xl text-center">
              <p className="text-sm font-light text-red-400/80 mb-4">{state.error}</p>
              <button
                onClick={() => window.location.reload()}
                className="px-5 py-2 rounded-lg border border-red-500/20 bg-red-500/[0.08] text-xs font-light tracking-[0.1em] uppercase text-red-400/80 hover:bg-red-500/[0.15] transition-colors duration-300"
              >
                Retry
              </button>
            </div>
          </motion.div>
        )}

        {/* Step Cards */}
        <div className="max-w-2xl mx-auto px-8 pb-16 space-y-4">
          <AnimatePresence mode="popLayout">
            {/* Step 1: Targets */}
            {stepStatus(0) !== 'pending' && (
              <StepCard key="step-1" label={STEP_LABELS[0]} index={0} status={stepStatus(0)} message={stepMessage(0)}>
                {stepStatus(0) === 'complete' && targetsData.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, ease }}
                    className="flex flex-wrap gap-2"
                  >
                    {targetsData.map((t) => (
                      <div
                        key={t.symbol}
                        className="inline-flex items-center gap-3 px-4 py-2.5 rounded-xl border border-blue-500/15 bg-blue-500/[0.05]"
                      >
                        <span className="text-lg font-light text-blue-400">{t.symbol}</span>
                        <span className="text-xs font-light text-white/35">{t.name}</span>
                        <span className="text-[0.5rem] font-mono font-light text-white/20">
                          {t.score.toFixed(3)}
                        </span>
                      </div>
                    ))}
                  </motion.div>
                )}
              </StepCard>
            )}

            {/* Step 2: Structures */}
            {stepStatus(1) !== 'pending' && (
              <StepCard key="step-2" label={STEP_LABELS[1]} index={1} status={stepStatus(1)} message={stepMessage(1)}>
                {stepStatus(1) === 'complete' && pdbText && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, ease }}
                  >
                    <MolViewer
                      proteinPdb={pdbText}
                      width="300px"
                      height="200px"
                      proteinStyle="cartoon"
                      autoRotate
                    />
                    {structuresData.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-3">
                        {structuresData.map((s) => (
                          <span key={s.pdb_id} className="text-[0.6rem] font-light text-white/25 tracking-wide">
                            {s.symbol}: {s.pdb_id}
                            {s.resolution && ` (${s.resolution}\u00C5)`}
                            {` \u2022 ${s.source}`}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}
              </StepCard>
            )}

            {/* Step 3: Drugs */}
            {stepStatus(2) !== 'pending' && (
              <StepCard key="step-3" label={STEP_LABELS[2]} index={2} status={stepStatus(2)} message={stepMessage(2)}>
                {stepStatus(2) === 'complete' && candidates.length > 0 && (
                  <motion.div
                    className="grid grid-cols-3 gap-3 mt-2"
                    initial="hidden"
                    animate="visible"
                    variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
                  >
                    {candidates.slice(0, 9).map((c, i) => (
                      <motion.div
                        key={c.drug_name || i}
                        variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                        transition={{ duration: 0.4, ease }}
                      >
                        <MoleculeCard
                          smiles={c.smiles}
                          drugName={c.drug_name}
                          confidence={c.confidence_score}
                          size="small"
                        />
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </StepCard>
            )}

            {/* Step 4: Docking */}
            {stepStatus(3) !== 'pending' && (
              <StepCard key="step-4" label={STEP_LABELS[3]} index={3} status={stepStatus(3)} message={stepMessage(3)}>
                {stepStatus(3) === 'complete' && pdbText && dockingViewData.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, ease }}
                  >
                    {dockingViewData.length > 1 && (
                      <div className="flex items-center gap-2 mb-3 flex-wrap">
                        <span className="text-[0.6rem] font-light text-white/25 tracking-wide uppercase">
                          Viewing:
                        </span>
                        {dockingViewData.slice(0, 8).map((d, i) => (
                          <button
                            key={i}
                            onClick={() => setSelectedDocking(i)}
                            className={`px-2.5 py-1 rounded-md text-[0.6rem] font-light transition-all duration-300 ${
                              selectedDocking === i
                                ? 'border border-blue-500/25 bg-blue-500/[0.08] text-blue-400/80'
                                : 'border border-white/[0.05] text-white/30 hover:text-white/50'
                            }`}
                          >
                            {d.drug_name}
                          </button>
                        ))}
                      </div>
                    )}
                    <MolViewer
                      proteinPdb={pdbText}
                      ligandSdf={dockingViewData[selectedDocking]?.ligand_sdf}
                      width="600px"
                      height="400px"
                      proteinStyle="surface"
                      autoRotate
                    />
                  </motion.div>
                )}
              </StepCard>
            )}

            {/* Step 5: Report */}
            {stepStatus(4) !== 'pending' && (
              <StepCard key="step-5" label={STEP_LABELS[4]} index={4} status={stepStatus(4)} message={stepMessage(4)}>
                {state.isDone && result && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.4, ease }}
                  >
                    <button
                      onClick={() => router.push('/results')}
                      className="relative w-full py-3 rounded-xl text-sm font-light tracking-[0.1em] uppercase text-white/80 overflow-hidden border border-blue-500/20 bg-blue-500/[0.06] hover:bg-blue-500/[0.1] transition-colors duration-300 cursor-pointer"
                      style={{
                        boxShadow: '0 0 25px rgba(59, 130, 246, 0.1), 0 0 50px rgba(59, 130, 246, 0.04)',
                      }}
                    >
                      View Full Results {'\u2192'}
                    </button>
                  </motion.div>
                )}
              </StepCard>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

// ─── Page Wrapper ───────────────────────────────────────────────────────────

export default function PipelinePage() {
  return (
    <Suspense
      fallback={
        <div className="w-screen h-screen bg-[#0a0b0f] flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
        </div>
      }
    >
      <PipelineContent />
    </Suspense>
  );
}
