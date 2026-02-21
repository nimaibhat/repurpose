'use client';

import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Crosshair,
  Box,
  Pill,
  FlaskConical,
  FileText,
  Search,
  Dna,
  Atom,
  Activity,
  Beaker,
  Check,
  X,
  type LucideIcon,
} from 'lucide-react';

// ─── Icon Registry ──────────────────────────────────────────────────────────

const ICON_MAP: Record<string, LucideIcon> = {
  crosshair: Crosshair,
  box: Box,
  pill: Pill,
  'flask-conical': FlaskConical,
  'file-text': FileText,
  search: Search,
  dna: Dna,
  atom: Atom,
  activity: Activity,
  beaker: Beaker,
};

function resolveIcon(name: string): LucideIcon {
  return ICON_MAP[name] ?? Crosshair;
}

// ─── Types ──────────────────────────────────────────────────────────────────

type StepStatus = 'pending' | 'running' | 'complete' | 'error';

interface StepDef {
  name: string;
  icon: string;
  status: StepStatus;
  message?: string;
}

interface PipelineStepperProps {
  steps: StepDef[];
}

// ─── Constants ──────────────────────────────────────────────────────────────

const NODE_SIZE = 56;
const ICON_SIZE = 22;
const ease = [0.16, 1, 0.3, 1] as const;

// ─── Connector Line ─────────────────────────────────────────────────────────

function ConnectorLine({
  leftStatus,
  rightStatus,
}: {
  leftStatus: StepStatus;
  rightStatus: StepStatus;
}) {
  // Determine line variant
  const isLeftDone = leftStatus === 'complete' || leftStatus === 'error';
  const isRightRunning = rightStatus === 'running';
  const isRightDone = rightStatus === 'complete' || rightStatus === 'error';
  const isActive = isLeftDone && (isRightRunning || isRightDone);
  const isFull = isLeftDone && isRightDone;

  return (
    <div
      className="flex-1 relative self-center mx-0.5"
      style={{ height: 3, marginTop: -(NODE_SIZE / 2 + 8) }}
    >
      {/* Track */}
      <div className="absolute inset-0 rounded-full bg-white/[0.06]" />

      {/* Fill */}
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full"
        initial={{ width: '0%' }}
        animate={{ width: isActive ? '100%' : '0%' }}
        transition={{ duration: 0.5, ease }}
        style={{
          background: isFull
            ? 'linear-gradient(to right, rgba(34,197,94,0.5), rgba(34,197,94,0.3))'
            : 'linear-gradient(to right, rgba(34,197,94,0.5), rgba(59,130,246,0.4))',
        }}
      />

      {/* Shimmer for active-but-not-done */}
      {isActive && !isFull && (
        <motion.div
          className="absolute inset-y-0 rounded-full"
          style={{
            width: '30%',
            background:
              'linear-gradient(to right, transparent, rgba(59,130,246,0.3), transparent)',
          }}
          animate={{ left: ['0%', '70%', '0%'] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
    </div>
  );
}

// ─── Step Node ──────────────────────────────────────────────────────────────

function StepNode({
  step,
  index,
}: {
  step: StepDef;
  index: number;
}) {
  const Icon = resolveIcon(step.icon);

  // Status-specific styles
  const ringClasses: Record<StepStatus, string> = {
    pending: 'border-gray-700 bg-gray-800',
    running: 'border-blue-500 bg-blue-900/50',
    complete: 'border-emerald-500 bg-emerald-900/30',
    error: 'border-red-500 bg-red-900/30',
  };

  const labelClasses: Record<StepStatus, string> = {
    pending: 'text-white/20',
    running: 'text-white/80',
    complete: 'text-white/70',
    error: 'text-red-400/80',
  };

  const iconColor: Record<StepStatus, string> = {
    pending: 'text-gray-500',
    running: 'text-blue-400',
    complete: 'text-emerald-400',
    error: 'text-red-400',
  };

  return (
    <motion.div
      className="flex flex-col items-center gap-2.5 shrink-0 relative z-10"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.07, ease }}
    >
      {/* Circle */}
      <div className="relative">
        {/* Blue glow for running */}
        {step.status === 'running' && (
          <motion.div
            className="absolute -inset-1 rounded-full"
            style={{ boxShadow: '0 0 20px rgba(59,130,246,0.3)' }}
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
        )}

        {/* Pulse ring */}
        {step.status === 'running' && (
          <motion.div
            className="absolute inset-0 rounded-full border border-blue-500/40"
            animate={{ scale: [1, 1.7], opacity: [0.6, 0] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
          />
        )}

        {/* Main circle */}
        <motion.div
          className={`flex items-center justify-center rounded-full border-[1.5px] transition-colors duration-500 ${ringClasses[step.status]}`}
          style={{ width: NODE_SIZE, height: NODE_SIZE }}
          animate={
            step.status === 'running'
              ? { scale: [1, 1.1, 1] }
              : { scale: 1 }
          }
          transition={
            step.status === 'running'
              ? { duration: 2, repeat: Infinity, ease: 'easeInOut' }
              : { duration: 0.3 }
          }
        >
          <AnimatePresence mode="wait">
            {step.status === 'complete' ? (
              <motion.div
                key="check"
                initial={{ scale: 0, rotate: -90 }}
                animate={{ scale: 1, rotate: 0 }}
                exit={{ scale: 0 }}
                transition={{ duration: 0.25, ease }}
              >
                <Check size={ICON_SIZE} className="text-emerald-400" strokeWidth={2.5} />
              </motion.div>
            ) : step.status === 'error' ? (
              <motion.div
                key="error"
                initial={{ scale: 0, rotate: 90 }}
                animate={{ scale: 1, rotate: 0 }}
                exit={{ scale: 0 }}
                transition={{ duration: 0.25, ease }}
              >
                <X size={ICON_SIZE} className="text-red-400" strokeWidth={2.5} />
              </motion.div>
            ) : (
              <motion.div
                key="icon"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                exit={{ scale: 0 }}
                transition={{ duration: 0.25, ease }}
              >
                <Icon size={ICON_SIZE} className={iconColor[step.status]} strokeWidth={1.5} />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Label — hides on small screens */}
      <span
        className={`text-xs font-light tracking-[0.15em] uppercase transition-colors duration-500 hidden sm:block ${labelClasses[step.status]}`}
      >
        {step.name}
      </span>

      {/* Message — only when complete */}
      {step.status === 'complete' && step.message && (
        <motion.span
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1, ease }}
          className="text-xs font-light text-white/30 text-center max-w-[120px] leading-snug hidden sm:block"
        >
          {step.message}
        </motion.span>
      )}
    </motion.div>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function PipelineStepper({ steps }: PipelineStepperProps) {
  // Memoize the interleaved nodes + connectors
  const elements = useMemo(() => {
    const els: React.ReactNode[] = [];
    steps.forEach((step, i) => {
      els.push(<StepNode key={`node-${i}`} step={step} index={i} />);
      if (i < steps.length - 1) {
        els.push(
          <ConnectorLine
            key={`line-${i}`}
            leftStatus={step.status}
            rightStatus={steps[i + 1].status}
          />,
        );
      }
    });
    return els;
  }, [steps]);

  return (
    <div className="flex items-start w-full">
      {elements}
    </div>
  );
}
