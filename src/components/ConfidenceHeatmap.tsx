'use client';

import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// ─── Props ──────────────────────────────────────────────────────────────────

interface HeatmapProps {
  targets: string[];
  drugs: string[];
  scores: number[][];
  onCellClick?: (target: string, drug: string, score: number) => void;
}

// ─── Color Scale ────────────────────────────────────────────────────────────

const COLOR_STOPS: [number, [number, number, number]][] = [
  [0.0, [10, 22, 50]],     // dark navy
  [0.3, [37, 99, 235]],    // blue
  [0.5, [20, 184, 166]],   // teal
  [0.7, [34, 197, 94]],    // green
  [1.0, [74, 222, 128]],   // bright green
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

  const range = upper[0] - lower[0];
  const t = range === 0 ? 0 : (s - lower[0]) / range;

  const r = Math.round(lower[1][0] + t * (upper[1][0] - lower[1][0]));
  const g = Math.round(lower[1][1] + t * (upper[1][1] - lower[1][1]));
  const b = Math.round(lower[1][2] + t * (upper[1][2] - lower[1][2]));

  return `rgb(${r},${g},${b})`;
}

// CSS gradient string for the legend bar
const LEGEND_GRADIENT = `linear-gradient(to right, ${
  COLOR_STOPS.map(([stop, [r, g, b]]) => `rgb(${r},${g},${b}) ${stop * 100}%`).join(', ')
})`;

// ─── Constants ──────────────────────────────────────────────────────────────

const CELL_W = 60;
const CELL_H = 40;
const ease = [0.16, 1, 0.3, 1] as const;

// ─── Component ──────────────────────────────────────────────────────────────

export default function ConfidenceHeatmap({
  targets,
  drugs,
  scores,
  onCellClick,
}: HeatmapProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<{
    ti: number;
    di: number;
    x: number;
    y: number;
  } | null>(null);
  const [selected, setSelected] = useState<{ ti: number; di: number } | null>(null);

  const handleMouseEnter = useCallback(
    (ti: number, di: number, e: React.MouseEvent) => {
      const rect = gridRef.current?.getBoundingClientRect();
      if (!rect) return;
      setHovered({
        ti,
        di,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    },
    [],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!hovered || !gridRef.current) return;
      const rect = gridRef.current.getBoundingClientRect();
      setHovered((prev) =>
        prev ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top } : null,
      );
    },
    [hovered],
  );

  const handleClick = useCallback(
    (ti: number, di: number) => {
      setSelected((prev) =>
        prev?.ti === ti && prev?.di === di ? null : { ti, di },
      );
      const score = scores[ti]?.[di] ?? 0;
      onCellClick?.(targets[ti], drugs[di], score);
    },
    [scores, targets, drugs, onCellClick],
  );

  // Label column width adapts to longest target name
  const labelColW = Math.max(
    60,
    ...targets.map((t) => t.length * 7.5 + 16),
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease }}
      className="flex flex-col gap-4"
    >
      {/* Grid container */}
      <div
        ref={gridRef}
        className="relative overflow-x-auto scrollbar-thin"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHovered(null)}
      >
        {/* Drug name headers (rotated 45 deg) */}
        <div
          className="flex"
          style={{ paddingLeft: labelColW, marginBottom: 8 }}
        >
          {drugs.map((drug, di) => (
            <div
              key={di}
              className="relative shrink-0"
              style={{ width: CELL_W, height: 56 }}
            >
              <span
                className="absolute bottom-0 left-1/2 origin-bottom-left text-[0.55rem] font-light text-white/40 whitespace-nowrap select-none"
                style={{
                  transform: 'rotate(-45deg) translateX(-50%)',
                  maxWidth: 90,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {drug}
              </span>
            </div>
          ))}
        </div>

        {/* Rows: target label + cells */}
        {targets.map((target, ti) => (
          <div key={ti} className="flex items-center">
            {/* Target label */}
            <div
              className="shrink-0 pr-3 text-right"
              style={{ width: labelColW }}
            >
              <span className="text-[0.6rem] font-mono font-light text-white/50 tracking-wide truncate block">
                {target}
              </span>
            </div>

            {/* Cells */}
            {drugs.map((drug, di) => {
              const score = scores[ti]?.[di] ?? 0;
              const isHovered = hovered?.ti === ti && hovered?.di === di;
              const isSelected = selected?.ti === ti && selected?.di === di;

              return (
                <button
                  key={di}
                  onClick={() => handleClick(ti, di)}
                  onMouseEnter={(e) => handleMouseEnter(ti, di, e)}
                  className="shrink-0 relative transition-all duration-200 focus:outline-none"
                  style={{
                    width: CELL_W,
                    height: CELL_H,
                    padding: 1.5,
                  }}
                >
                  <div
                    className="w-full h-full rounded-[4px] flex items-center justify-center transition-all duration-200"
                    style={{
                      backgroundColor: scoreToColor(score),
                      opacity: isHovered ? 1 : 0.85,
                      filter: isHovered ? 'brightness(1.3)' : 'none',
                      boxShadow: isSelected
                        ? '0 0 0 1.5px rgba(255,255,255,0.8), 0 0 12px rgba(255,255,255,0.15)'
                        : isHovered
                        ? '0 0 8px rgba(255,255,255,0.08)'
                        : 'none',
                    }}
                  >
                    <span
                      className="text-[0.55rem] font-mono font-light tabular-nums select-none"
                      style={{
                        color: score > 0.45
                          ? 'rgba(255,255,255,0.9)'
                          : 'rgba(255,255,255,0.55)',
                      }}
                    >
                      {score.toFixed(2)}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        ))}

        {/* Tooltip */}
        <AnimatePresence>
          {hovered && (
            <motion.div
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.92 }}
              transition={{ duration: 0.15 }}
              className="absolute z-50 pointer-events-none px-3 py-2 rounded-lg bg-black/80 backdrop-blur-md border border-white/[0.1] shadow-xl"
              style={{
                left: hovered.x + 14,
                top: hovered.y - 36,
              }}
            >
              <span className="text-[0.6rem] font-light text-white/80 whitespace-nowrap">
                <span className="text-white/50">{drugs[hovered.di]}</span>
                <span className="text-white/20 mx-1.5">&rarr;</span>
                <span className="text-blue-400/80">{targets[hovered.ti]}</span>
                <span className="text-white/20 mx-1.5">:</span>
                <span
                  className="font-mono tabular-nums"
                  style={{ color: scoreToColor(scores[hovered.ti]?.[hovered.di] ?? 0) }}
                >
                  {(scores[hovered.ti]?.[hovered.di] ?? 0).toFixed(2)}
                </span>
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 pl-1">
        <span className="text-[0.5rem] font-light text-white/25 tracking-wide uppercase shrink-0">
          Confidence
        </span>
        <div className="flex items-center gap-2 flex-1 max-w-[280px]">
          <span className="text-[0.5rem] font-mono font-light text-white/30 tabular-nums">
            0.0
          </span>
          <div
            className="flex-1 h-2.5 rounded-full"
            style={{ background: LEGEND_GRADIENT }}
          />
          <span className="text-[0.5rem] font-mono font-light text-white/30 tabular-nums">
            1.0
          </span>
        </div>
      </div>
    </motion.div>
  );
}
