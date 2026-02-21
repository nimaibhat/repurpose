'use client';

import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';

// ─── Props ──────────────────────────────────────────────────────────────────

interface MoleculeCardProps {
  smiles: string;
  drugName?: string;
  confidence?: number;
  phase?: number;
  selected?: boolean;
  onClick?: () => void;
  size?: 'small' | 'medium' | 'large';
  rank?: number;
  mechanism?: string;
}

// ─── Size Config ────────────────────────────────────────────────────────────

const sizeConfig = {
  small:  { canvasW: 120, canvasH: 90  },
  medium: { canvasW: 100, canvasH: 80  },
  large:  { canvasW: 200, canvasH: 160 },
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function scoreBgClass(score: number): string {
  if (score >= 0.7) return 'bg-emerald-500';
  if (score >= 0.4) return 'bg-yellow-500';
  return 'bg-red-500';
}

function scoreTextClass(score: number): string {
  if (score >= 0.7) return 'text-emerald-400/80';
  if (score >= 0.4) return 'text-yellow-400/80';
  return 'text-red-400/80';
}

function phaseLabel(phase?: number): { label: string; classes: string } {
  if (phase === 4) return { label: 'FDA Approved', classes: 'border-emerald-500/20 bg-emerald-500/[0.08] text-emerald-400/80' };
  if (phase === 3) return { label: 'Phase 3',      classes: 'border-yellow-500/20 bg-yellow-500/[0.08] text-yellow-400/80' };
  if (phase === 2) return { label: 'Phase 2',      classes: 'border-blue-500/20 bg-blue-500/[0.08] text-blue-400/80' };
  if (phase === 1) return { label: 'Phase 1',      classes: 'border-purple-500/20 bg-purple-500/[0.08] text-purple-400/80' };
  return { label: 'Preclinical', classes: 'border-white/[0.08] bg-white/[0.03] text-white/40' };
}

const ease = [0.16, 1, 0.3, 1] as const;

// ─── Component ──────────────────────────────────────────────────────────────

export default function MoleculeCard({
  smiles,
  drugName,
  confidence,
  phase,
  selected = false,
  onClick,
  size = 'medium',
  rank,
  mechanism,
}: MoleculeCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [parseError, setParseError] = useState(false);

  const { canvasW, canvasH } = sizeConfig[size];

  // ── SmilesDrawer rendering ──
  useEffect(() => {
    if (!canvasRef.current || !smiles) return;
    setParseError(false);

    let mounted = true;

    (async () => {
      const SmilesDrawer = (await import('smiles-drawer')).default;
      if (!mounted || !canvasRef.current) return;

      const drawer = new SmilesDrawer.Drawer({
        width: canvasW,
        height: canvasH,
        bondThickness: 1.2,
        bondLength: 15,
        shortBondLength: 0.8,
        bondSpacing: 4,
        atomVisualization: 'default',
        isomeric: true,
        debug: false,
        terminalCarbons: false,
        explicitHydrogens: false,
        overlapSensitivity: 0.42,
        overlapResolutionIterations: 1,
        compactDrawing: true,
        fontSizeLarge: 6,
        fontSizeSmall: 4,
        padding: 16,
        themes: {
          dark: {
            C: '#cccccc',
            O: '#ff4444',
            N: '#4488ff',
            S: '#ffcc00',
            F: '#44ff44',
            Cl: '#44ff44',
            Br: '#cc6633',
            I: '#aa44ff',
            P: '#ff8800',
            H: '#999999',
            BACKGROUND: 'transparent',
          },
        },
      });

      SmilesDrawer.parse(
        smiles,
        (tree: any) => {
          if (!mounted || !canvasRef.current) return;
          drawer.draw(tree, canvasRef.current, 'dark');
        },
        () => {
          if (mounted) setParseError(true);
        },
      );
    })();

    return () => { mounted = false; };
  }, [smiles, canvasW, canvasH]);

  // ── Canvas / fallback element ──
  const canvasEl = parseError ? (
    <div
      className="flex items-center justify-center rounded-lg bg-white/[0.02]"
      style={{ width: canvasW, height: canvasH }}
    >
      <span className="text-[0.5rem] font-light text-white/20">
        Structure unavailable
      </span>
    </div>
  ) : (
    <canvas
      ref={canvasRef}
      width={canvasW}
      height={canvasH}
      className="rounded-lg"
      style={{ width: canvasW, height: canvasH }}
    />
  );

  // ── Small layout: vertical card for grids ──
  if (size === 'small') {
    const Tag = onClick ? motion.button : ('div' as const);
    return (
      <Tag
        {...(onClick && { onClick, whileTap: { scale: 0.97 } })}
        className={`rounded-xl border p-3 flex flex-col items-center gap-2 transition-all duration-300 ${
          selected
            ? 'border-blue-500/25 bg-blue-500/[0.04]'
            : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1] hover:bg-white/[0.03]'
        }`}
      >
        {canvasEl}
        {drugName && (
          <span className="text-[0.6rem] font-light text-white/60 text-center leading-tight truncate w-full">
            {drugName}
          </span>
        )}
        {confidence !== undefined && (
          <span className={`text-[0.5rem] font-light tracking-wide ${scoreTextClass(confidence)}`}>
            Score: {confidence.toFixed(2)}
          </span>
        )}
      </Tag>
    );
  }

  // ── Medium / Large layout: horizontal card ──
  const Tag = onClick ? motion.button : ('div' as const);
  const pb = phase !== undefined ? phaseLabel(phase) : null;

  return (
    <Tag
      {...(onClick && { onClick, whileTap: { scale: 0.995 } })}
      className={`w-full text-left rounded-xl border transition-all duration-300 relative ${
        size === 'large' ? 'p-5' : 'p-4'
      } ${
        selected
          ? 'border-blue-500/25 bg-blue-500/[0.04]'
          : 'border-white/[0.05] bg-white/[0.015] hover:border-white/[0.1] hover:bg-white/[0.03]'
      }`}
      {...(onClick && { layout: true })}
    >
      {/* Blue left accent bar when selected */}
      {selected && (
        <motion.div
          layoutId="drug-selected-bar"
          className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-blue-500/60"
          transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
        />
      )}

      <div className="flex gap-3">
        {/* 2D Molecule canvas */}
        <div className="shrink-0 rounded-lg border border-white/[0.04] bg-black/30 overflow-hidden">
          {canvasEl}
        </div>

        {/* Info column */}
        <div className="flex-1 min-w-0">
          {/* Rank + Name */}
          <div className="flex items-center gap-2 mb-1">
            {rank !== undefined && (
              <span className="text-[0.55rem] font-mono font-light text-white/20">
                #{rank}
              </span>
            )}
            {drugName && (
              <span className={`font-light text-white/85 truncate ${size === 'large' ? 'text-base' : 'text-sm'}`}>
                {drugName}
              </span>
            )}
          </div>

          {/* Confidence bar */}
          {confidence !== undefined && (
            <div className="mb-2">
              <div className="flex items-center gap-2.5 w-full">
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full ${scoreBgClass(confidence)}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(Math.max(confidence * 100, 0), 100)}%` }}
                    transition={{ duration: 0.8, ease }}
                  />
                </div>
                <span className={`text-[0.6rem] font-mono font-light tabular-nums ${scoreTextClass(confidence)}`}>
                  {confidence.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Phase badge */}
          {pb && (
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`inline-block px-1.5 py-0.5 rounded text-[0.5rem] font-light tracking-wide border ${pb.classes}`}
              >
                {pb.label}
              </span>
            </div>
          )}

          {/* Mechanism */}
          {mechanism && (
            <p className="mt-1.5 text-[0.6rem] font-light text-white/30 leading-relaxed line-clamp-1">
              {mechanism}
            </p>
          )}
        </div>
      </div>
    </Tag>
  );
}
