'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';

const ModelViewer = dynamic(() => import('@/components/ModelViewer'), { ssr: false });
const Orb = dynamic(() => import('@/components/Orb'), { ssr: false });
const SplashCursor = dynamic(() => import('@/components/SplashCursor'), { ssr: false });
const WaveField = dynamic(() => import('@/components/WaveField'), { ssr: false });

function LoadingScreen(): React.ReactNode {
  return (
    <motion.div
      className="fixed inset-0 bg-black z-[9999] flex items-center justify-center"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.8 } }}
    >
      <div className="w-6 h-6 border border-white/20 border-t-white/60 rounded-full animate-spin" />
    </motion.div>
  );
}

function HeroContent(): React.ReactNode {
  const router = useRouter();

  return (
    <motion.div
      className="w-screen h-screen overflow-hidden flex flex-col items-center justify-center relative"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1 }}
    >
      <SplashCursor SPLAT_RADIUS={0.04} SIM_RESOLUTION={64} DYE_RESOLUTION={1024} />

      <div className="fixed inset-0 z-0">
        <WaveField speed={0.8} intensity={2.5} />
      </div>

      <motion.div
        className="z-[1] w-[min(520px,70vw)] h-[min(520px,70vw)] -mt-4"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, delay: 0.2 }}
      >
        <Orb hoverIntensity={0.6}>
          <ModelViewer
            url="/pilltablet.glb"
            width={500}
            height={500}
            defaultZoom={1.67}
            modelXOffset={0.035}
            defaultRotationX={-50}
            defaultRotationY={20}
            autoRotate
            enableManualRotation
            environmentPreset="none"
            keyLightIntensity={2.5}
            rimLightIntensity={1.5}
            enableMouseParallax
            enableHoverRotation
          />
        </Orb>
      </motion.div>

      <div className="z-[1] flex flex-col items-center mt-4">
        <motion.h1
          className="text-[5rem] font-extralight tracking-[0.35em] uppercase leading-none"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5 }}
        >
          repurpose
        </motion.h1>
        <motion.div
          className="w-12 h-px bg-white/20 mt-5 mb-4"
          initial={{ opacity: 0, scaleX: 0 }}
          animate={{ opacity: 1, scaleX: 1 }}
          transition={{ duration: 0.6, delay: 0.8 }}
        />
        <motion.p
          className="text-sm tracking-[0.25em] uppercase text-white/35 font-extralight"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.9 }}
        >
          hack/ai 2026
        </motion.p>
        <motion.button
          className="mt-10 px-8 py-4 rounded-md border border-white/10 bg-white/[0.02] text-white/40 text-sm font-extralight tracking-[0.25em] uppercase hover:bg-white/[0.06] hover:text-white/60 hover:border-white/20 transition-all duration-500 cursor-pointer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, y: [0, -4, 0] }}
          transition={{
            opacity: { duration: 0.8, delay: 1.2 },
            y: { duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 1.2 },
          }}
          onClick={() => router.push('/research')}
        >
          get started
        </motion.button>
      </div>
    </motion.div>
  );
}

export default function Home() {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 1200);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <AnimatePresence>
        {isLoading && <LoadingScreen />}
      </AnimatePresence>
      {!isLoading && <HeroContent />}
    </>
  );
}
