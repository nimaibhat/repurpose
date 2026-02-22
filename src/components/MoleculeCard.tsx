'use client';

import { useState } from 'react';
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
  small:  { canvasW: 140, canvasH: 105 },
  medium: { canvasW: 120, canvasH: 96  },
  large:  { canvasW: 240, canvasH: 192 },
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
  return { label: 'Preclinical', classes: 'border-white/[0.08] bg-white/[0.03] text-white/60' };
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
  const [imgError, setImgError] = useState(false);
  const { canvasW, canvasH } = sizeConfig[size];

  const pubchemUrl = smiles
    ? `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smiles)}/PNG?record_type=2d&image_size=${canvasW}x${canvasH}`
    : null;

  const canvasEl = !pubchemUrl || imgError ? (
    <div
      className="flex items-center justify-center rounded-lg bg-white/[0.02]"
      style={{ width: canvasW, height: canvasH }}
    >
      <span className="text-xs font-light text-white/40">Structure unavailable</span>
    </div>
  ) : (
    <img
      src={pubchemUrl}
      alt={drugName || smiles}
      width={canvasW}
      height={canvasH}
      onError={() => setImgError(true)}
      className="rounded-lg"
      style={{ objectFit: 'contain', filter: 'invert(1) hue-rotate(180deg) brightness(0.85) contrast(1.1)' }}
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
          <span className="text-xs font-light text-white/60 text-center leading-tight truncate w-full">
            {drugName}
          </span>
        )}
        {confidence !== undefined && (
          <span className={`text-xs font-light tracking-wide ${scoreTextClass(confidence)}`}>
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
              <span className="text-xs font-mono font-light text-white/60">
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
                <span className={`text-xs font-mono font-light tabular-nums ${scoreTextClass(confidence)}`}>
                  {confidence.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Phase badge */}
          {pb && (
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`inline-block px-3 py-1 rounded text-xs font-light tracking-wide border ${pb.classes}`}
              >
                {pb.label}
              </span>
            </div>
          )}

          {/* Mechanism */}
          {mechanism && (
            <p className="mt-1.5 text-xs font-light text-white/50 leading-relaxed line-clamp-1">
              {mechanism}
            </p>
          )}
        </div>
      </div>
    </Tag>
  );
}
