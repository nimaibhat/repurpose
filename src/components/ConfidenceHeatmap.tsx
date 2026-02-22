'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

interface HeatmapProps {
  targets: string[];
  drugs: string[];
  scores: number[][];
  onCellClick?: (target: string, drug: string, score: number) => void;
}

const COLOR_STOPS: [number, [number, number, number]][] = [
  [0.0, [37, 99, 235]],
  [0.5, [20, 184, 166]],
  [1.0, [74, 222, 128]],
];

function scoreToColor(score: number): string {
  const s = Math.max(0, Math.min(1, score));
  let lower = COLOR_STOPS[0];
  let upper = COLOR_STOPS[COLOR_STOPS.length - 1];
  for (let i = 0; i < COLOR_STOPS.length - 1; i++) {
    if (s >= COLOR_STOPS[i][0] && s <= COLOR_STOPS[i + 1][0]) {
      lower = COLOR_STOPS[i];
      upper = COLOR_STOPS[i + 1];
      break;
    }
  }
  const t = upper[0] === lower[0] ? 0 : (s - lower[0]) / (upper[0] - lower[0]);
  const r = Math.round(lower[1][0] + t * (upper[1][0] - lower[1][0]));
  const g = Math.round(lower[1][1] + t * (upper[1][1] - lower[1][1]));
  const b = Math.round(lower[1][2] + t * (upper[1][2] - lower[1][2]));
  return `rgb(${r},${g},${b})`;
}

function confidenceLabel(score: number): string {
  if (score >= 0.7) return 'High';
  if (score >= 0.4) return 'Moderate';
  return 'Low';
}

export default function ConfidenceHeatmap({ targets, drugs, scores, onCellClick }: HeatmapProps) {
  const [selected, setSelected] = useState<{ target: string; drug: string } | null>(null);

  const groups = targets
    .map((target, ti) => {
      const pairs = drugs
        .map((drug, di) => ({ drug, score: scores[ti]?.[di] ?? 0 }))
        .filter((p) => p.score > 0)
        .sort((a, b) => b.score - a.score);
      return { target, pairs };
    })
    .filter((g) => g.pairs.length > 0);

  if (groups.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-white/20 font-light">
        No confidence scores available
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col gap-1"
    >
      {/* Header */}
      <div className="mb-3">
        <p className="text-xs font-medium text-white/70">Drug–Target Binding Confidence</p>
        <p className="text-[0.65rem] text-white/35 mt-0.5">
          How confidently each drug is predicted to bind its target. Click a row to inspect.
        </p>
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-2.5 mb-1 pl-[108px]">
        <span className="text-[0.55rem] text-white/25 uppercase tracking-widest flex-1">Binding strength (0 → 1)</span>
        <span className="text-[0.55rem] text-white/25 uppercase tracking-widest w-7 text-right">Score</span>
      </div>

      {groups.map(({ target, pairs }, gi) => (
        <div key={target} className="flex flex-col gap-1 mb-3">
          {/* Target header */}
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[0.6rem] font-semibold text-white/60 uppercase tracking-widest">
              Target:
            </span>
            <span className="text-[0.65rem] font-mono font-medium text-white/80">
              {target}
            </span>
            <span className="text-[0.55rem] text-white/25 ml-1">
              — {pairs.length} candidate{pairs.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Bars */}
          <div className="flex flex-col gap-1.5 pl-3 border-l border-white/[0.06]">
            {pairs.map(({ drug, score }) => {
              const color = scoreToColor(score);
              const isSelected = selected?.target === target && selected?.drug === drug;
              const label = confidenceLabel(score);

              return (
                <button
                  key={drug}
                  onClick={() => {
                    setSelected(isSelected ? null : { target, drug });
                    onCellClick?.(target, drug, score);
                  }}
                  className="flex items-center gap-2.5 text-left focus:outline-none"
                  title={`${drug} → ${target}: ${label} confidence (${score.toFixed(2)})`}
                >
                  {/* Drug name */}
                  <span
                    className="shrink-0 text-[0.65rem] font-light truncate transition-colors duration-150"
                    style={{
                      width: 100,
                      textAlign: 'right',
                      color: isSelected ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.5)',
                    }}
                  >
                    {drug}
                  </span>

                  {/* Bar track */}
                  <div className="relative flex-1 h-4 rounded overflow-hidden bg-white/[0.05]">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${score * 100}%` }}
                      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: gi * 0.05 }}
                      className="absolute inset-y-0 left-0 rounded flex items-center justify-end pr-1.5"
                      style={{
                        background: `linear-gradient(to right, ${scoreToColor(score * 0.5)}, ${color})`,
                        opacity: isSelected ? 1 : 0.8,
                        boxShadow: isSelected ? `0 0 10px ${color}44` : undefined,
                        minWidth: 28,
                      }}
                    >
                      {/* Confidence label inside bar */}
                      {score > 0.25 && (
                        <span className="text-[0.5rem] font-medium text-white/70 whitespace-nowrap">
                          {label}
                        </span>
                      )}
                    </motion.div>
                  </div>

                  {/* Numeric score */}
                  <span
                    className="shrink-0 text-[0.65rem] font-mono tabular-nums font-medium"
                    style={{ width: 28, color }}
                  >
                    {score.toFixed(2)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {/* Legend */}
      <div className="mt-2 pt-3 border-t border-white/[0.05] flex items-center gap-4">
        <span className="text-[0.55rem] text-white/20 uppercase tracking-widest">Confidence</span>
        {(['Low', 'Moderate', 'High'] as const).map((lvl) => {
          const score = lvl === 'Low' ? 0.2 : lvl === 'Moderate' ? 0.55 : 0.85;
          return (
            <div key={lvl} className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: scoreToColor(score) }} />
              <span className="text-[0.55rem] text-white/30">{lvl} (&lt;{lvl === 'Low' ? '0.4' : lvl === 'Moderate' ? '0.7' : '1.0'})</span>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
