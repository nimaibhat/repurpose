'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from 'recharts';

// ─── Props ──────────────────────────────────────────────────────────────────

interface ADMETRadarProps {
  scores: {
    absorption: number;
    distribution: number;
    metabolism: number;
    excretion: number;
    toxicity: number;
    drug_likeness: number;
  };
  flags: string[];
  passFail: 'pass' | 'warn' | 'fail';
  drugName: string;
  size?: 'small' | 'large';
}

// ─── Theme Config ───────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  pass: { color: '#10b981', label: '✓ Safe',    border: 'border-emerald-500/20', bg: 'bg-emerald-500/[0.08]', text: 'text-emerald-400' },
  warn: { color: '#eab308', label: '⚠ Caution', border: 'border-yellow-500/20',  bg: 'bg-yellow-500/[0.08]',  text: 'text-yellow-400'  },
  fail: { color: '#ef4444', label: '✗ Risk',    border: 'border-red-500/20',     bg: 'bg-red-500/[0.08]',     text: 'text-red-400'     },
} as const;

const DIMENSIONS = { small: 200, large: 350 } as const;

// ─── Component ──────────────────────────────────────────────────────────────

export default function ADMETRadar({
  scores,
  flags,
  passFail,
  drugName,
  size = 'small',
}: ADMETRadarProps) {
  const [animated, setAnimated] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const config = STATUS_CONFIG[passFail];
  const dim = DIMENSIONS[size];

  const data = [
    { property: 'Absorption',     score: scores.absorption,     fullMark: 1 },
    { property: 'Distribution',   score: scores.distribution,   fullMark: 1 },
    { property: 'Metabolism',     score: scores.metabolism,      fullMark: 1 },
    { property: 'Excretion',     score: scores.excretion,       fullMark: 1 },
    { property: 'Toxicity',      score: scores.toxicity,        fullMark: 1 },
    { property: 'Drug-likeness', score: scores.drug_likeness,   fullMark: 1 },
  ];

  const animatedData = data.map((d) => ({
    ...d,
    score: animated ? d.score : 0,
  }));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center"
    >
      {/* Radar chart */}
      <div style={{ width: dim, height: dim }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart
            data={animatedData}
            cx="50%"
            cy="50%"
            outerRadius={size === 'small' ? '65%' : '70%'}
          >
            <PolarGrid stroke="rgba(255,255,255,0.1)" />
            <PolarAngleAxis
              dataKey="property"
              tick={{
                fill: '#9ca3af',
                fontSize: size === 'small' ? 9 : 11,
                fontWeight: 300,
              }}
            />
            <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
            <Radar
              name="ADMET"
              dataKey="score"
              stroke={config.color}
              fill={config.color}
              fillOpacity={0.3}
              strokeWidth={1.5}
              animationDuration={600}
              animationEasing="ease-out"
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Drug name */}
      <p className={`font-light text-white/80 text-center truncate max-w-full ${
        size === 'small' ? 'text-xs mt-1' : 'text-sm mt-2'
      }`}>
        {drugName}
      </p>

      {/* Pass/fail badge */}
      <span className={`inline-block mt-1.5 px-3 py-0.5 rounded text-xs font-light tracking-wide border ${config.border} ${config.bg} ${config.text}`}>
        {config.label}
      </span>

      {/* Flags — large size only */}
      {size === 'large' && flags.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1.5 mt-2 max-w-[320px]">
          {flags.map((flag) => (
            <span
              key={flag}
              className="px-2 py-0.5 rounded-full text-[10px] font-light tracking-wide border border-white/[0.08] bg-white/[0.03] text-white/50"
            >
              {flag}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}
