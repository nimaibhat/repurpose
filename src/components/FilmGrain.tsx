'use client';

import { useEffect, useRef } from 'react';

interface FilmGrainProps {
  opacity?: number;
}

export default function FilmGrain({ opacity = 0.04 }: FilmGrainProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let animId: number;
    let w: number, h: number;

    function resize() {
      w = canvas!.width = window.innerWidth / 2;
      h = canvas!.height = window.innerHeight / 2;
    }
    resize();
    window.addEventListener('resize', resize);

    function draw() {
      const imageData = ctx!.createImageData(w, h);
      const data = imageData.data;
      for (let i = 0, len = data.length; i < len; i += 4) {
        const v = (Math.random() * 255) | 0;
        data[i] = v;
        data[i + 1] = v;
        data[i + 2] = v;
        data[i + 3] = 255;
      }
      ctx!.putImageData(imageData, 0, 0);
      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{
        zIndex: 9998,
        width: '100vw',
        height: '100vh',
        opacity,
        mixBlendMode: 'overlay',
      }}
    />
  );
}
