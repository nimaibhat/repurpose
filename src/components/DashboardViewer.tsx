'use client';

import { useRef, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';

export type ProteinStyle = 'cartoon' | 'surface' | 'ballstick' | 'hidden';

export interface DashboardViewerHandle {
  setLigand: (sdf: string | null) => void;
  setProteinStyle: (style: ProteinStyle) => void;
  setLigandVisible: (visible: boolean) => void;
  resetView: () => void;
}

interface DashboardViewerProps {
  pdbText?: string;
  initialLigandSdf?: string;
  initialProteinStyle?: ProteinStyle;
  height?: number | string;
}

const DashboardViewer = forwardRef<DashboardViewerHandle, DashboardViewerProps>(
  function DashboardViewer(
    { pdbText, initialLigandSdf, initialProteinStyle = 'cartoon', height = '100%' },
    ref,
  ) {
    const wrapperRef = useRef<HTMLDivElement>(null);   // outer — captures wheel events
    const containerRef = useRef<HTMLDivElement>(null); // inner — 3Dmol canvas
    const viewerRef = useRef<any>(null);
    const $3DmolRef = useRef<any>(null);
    const proteinModelRef = useRef<any>(null);
    const ligandModelRef = useRef<any>(null);
    const surfaceRef = useRef<any>(null);
    const proteinStyleRef = useRef<ProteinStyle>(initialProteinStyle);
    const ligandVisibleRef = useRef(true);
    const currentLigandSdf = useRef<string | null>(initialLigandSdf || null);
    const readyRef = useRef(false);

    const applyProteinStyle = useCallback((style: ProteinStyle) => {
      const viewer = viewerRef.current;
      const $3Dmol = $3DmolRef.current;
      const proteinModel = proteinModelRef.current;
      if (!viewer || !$3Dmol || !proteinModel) return;

      viewer.removeAllSurfaces();
      surfaceRef.current = null;

      const sel = { model: proteinModel };

      switch (style) {
        case 'cartoon':
          viewer.setStyle(sel, { cartoon: { color: 'spectrum', opacity: 0.75 } });
          break;
        case 'surface':
          viewer.setStyle(sel, { cartoon: { color: 'spectrum', opacity: 0.3 } });
          surfaceRef.current = viewer.addSurface($3Dmol.SurfaceType.VDW, {
            opacity: 0.6, color: 'lightblue',
          }, sel);
          break;
        case 'ballstick':
          viewer.setStyle(sel, {
            stick: { radius: 0.1, colorscheme: 'Jmol' },
            sphere: { scale: 0.25, colorscheme: 'Jmol' },
          });
          break;
        case 'hidden':
          viewer.setStyle(sel, {});
          break;
      }

      proteinStyleRef.current = style;
      viewer.render();
    }, []);

    const styleLigand = useCallback((model: any) => {
      if (!model) return;
      model.setStyle({}, {
        stick: { colorscheme: 'greenCarbon', radius: 0.18 },
        sphere: { colorscheme: 'greenCarbon', scale: 0.22 },
      });
    }, []);

    const setLigand = useCallback((sdf: string | null) => {
      const viewer = viewerRef.current;
      if (!viewer) return;

      if (ligandModelRef.current) {
        viewer.removeModel(ligandModelRef.current);
        ligandModelRef.current = null;
      }

      currentLigandSdf.current = sdf;

      if (sdf && ligandVisibleRef.current) {
        const model = viewer.addModel(sdf, 'sdf');
        styleLigand(model);
        ligandModelRef.current = model;
        viewer.zoomTo({ model: model }, 1000);
      } else if (proteinModelRef.current) {
        viewer.zoomTo({ model: proteinModelRef.current });
      } else {
        viewer.zoomTo();
      }

      viewer.render();
    }, [styleLigand]);

    const setLigandVisible = useCallback((visible: boolean) => {
      const viewer = viewerRef.current;
      ligandVisibleRef.current = visible;

      if (visible && currentLigandSdf.current) {
        if (ligandModelRef.current) {
          viewer?.removeModel(ligandModelRef.current);
          ligandModelRef.current = null;
        }
        if (viewer) {
          const model = viewer.addModel(currentLigandSdf.current, 'sdf');
          styleLigand(model);
          ligandModelRef.current = model;
          viewer.zoomTo({ model: model }, 800);
          viewer.render();
        }
      } else if (!visible) {
        if (viewer && ligandModelRef.current) {
          viewer.removeModel(ligandModelRef.current);
          ligandModelRef.current = null;
          applyProteinStyle(proteinStyleRef.current);
          viewer.zoomTo({ model: proteinModelRef.current });
          viewer.render();
        }
      }
    }, [styleLigand, applyProteinStyle]);

    const resetView = useCallback(() => {
      const viewer = viewerRef.current;
      if (!viewer) return;
      if (ligandModelRef.current) {
        viewer.zoomTo({ model: ligandModelRef.current });
      } else {
        viewer.zoomTo();
      }
      viewer.spin('y', 0.3);
      viewer.render();
    }, []);

    const setProteinStyle = useCallback((style: ProteinStyle) => {
      applyProteinStyle(style);
      if (ligandModelRef.current && ligandVisibleRef.current) {
        styleLigand(ligandModelRef.current);
        viewerRef.current?.render();
      }
    }, [applyProteinStyle, styleLigand]);

    // Zoom helpers exposed to buttons
    const zoomIn = useCallback(() => {
      const viewer = viewerRef.current;
      if (!viewer) return;
      viewer.zoom(1.2, 200);
      viewer.render();
    }, []);

    const zoomOut = useCallback(() => {
      const viewer = viewerRef.current;
      if (!viewer) return;
      viewer.zoom(0.8, 200);
      viewer.render();
    }, []);

    useImperativeHandle(ref, () => ({
      setLigand,
      setProteinStyle,
      setLigandVisible,
      resetView,
    }), [setLigand, setProteinStyle, setLigandVisible, resetView]);

    // Cursor-centric wheel zoom — intercept in capture phase before 3Dmol's listener
    useEffect(() => {
      const wrapper = wrapperRef.current;
      const container = containerRef.current;
      if (!wrapper || !container) return;

      const onWheel = (e: WheelEvent) => {
        const viewer = viewerRef.current;
        if (!viewer) return;

        e.preventDefault();
        e.stopPropagation();

        const rect = container.getBoundingClientRect();
        // Cursor offset from canvas centre (screen coords)
        const cx = e.clientX - rect.left - rect.width / 2;
        const cy = e.clientY - rect.top - rect.height / 2;

        // Normalise delta so touchpad (small values) and mouse wheel behave similarly
        const rawDelta = e.deltaY !== 0 ? e.deltaY : -e.deltaX;
        const clamped = Math.sign(rawDelta) * Math.min(Math.abs(rawDelta), 100);
        const factor = 1 - clamped * 0.005; // ~0.5 % per pixel of scroll

        // Cursor-centric: shift scene toward cursor, zoom, done.
        // After zooming by k, a point at (cx,cy) would move to (cx*k, cy*k).
        // To keep it under the cursor we translate by -(cx*(k-1), -cy*(k-1)).
        // 3Dmol's y axis points up so we negate cy.
        const k = factor;
        viewer.translate(-cx * (k - 1), cy * (k - 1), 0);
        viewer.zoom(k, 0);
        viewer.render();
      };

      // capture:true so we fire before 3Dmol's bubble-phase canvas listener
      wrapper.addEventListener('wheel', onWheel, { passive: false, capture: true });
      return () => wrapper.removeEventListener('wheel', onWheel, { capture: true });
    }, []);

    // Initialize viewer once
    useEffect(() => {
      if (!containerRef.current || (!pdbText && !initialLigandSdf) || readyRef.current) return;

      let mounted = true;

      (async () => {
        const $3Dmol = await import('3dmol');
        if (!mounted || !containerRef.current) return;
        $3DmolRef.current = $3Dmol;

        const viewer = $3Dmol.createViewer(containerRef.current, {
          backgroundColor: 'black',
          antialias: true,
        });
        viewerRef.current = viewer;

        if (pdbText) {
          proteinModelRef.current = viewer.addModel(pdbText, 'pdb');
          applyProteinStyle(proteinStyleRef.current);
        }

        if (initialLigandSdf) {
          const ligand = viewer.addModel(initialLigandSdf, 'sdf');
          styleLigand(ligand);
          ligandModelRef.current = ligand;
          currentLigandSdf.current = initialLigandSdf;
          viewer.zoomTo({ model: ligand });
        } else {
          viewer.zoomTo();
        }

        viewer.spin('y', 0.3);
        viewer.render();
        readyRef.current = true;
      })();

      return () => {
        mounted = false;
        if (viewerRef.current) {
          viewerRef.current.clear();
          viewerRef.current = null;
        }
        proteinModelRef.current = null;
        ligandModelRef.current = null;
        readyRef.current = false;
      };
    }, [pdbText, initialLigandSdf, applyProteinStyle, styleLigand]);

    useEffect(() => {
      const viewer = viewerRef.current;
      if (viewer) { viewer.resize(); viewer.render(); }
    }, [height]);

    return (
      <div ref={wrapperRef} className="relative w-full">
        <div
          ref={containerRef}
          className="w-full rounded-xl border border-white/[0.06] bg-black/40 overflow-hidden"
          style={{ height, position: 'relative' }}
        />

        {/* Zoom buttons */}
        <div className="absolute bottom-3 right-3 flex flex-col gap-1 z-10">
          <button
            onClick={zoomIn}
            className="w-7 h-7 flex items-center justify-center rounded-md border border-white/[0.08] bg-black/60 backdrop-blur-sm text-white/50 hover:text-white/80 hover:border-white/20 transition-all duration-150 text-sm font-light select-none"
            title="Zoom in"
          >
            +
          </button>
          <button
            onClick={zoomOut}
            className="w-7 h-7 flex items-center justify-center rounded-md border border-white/[0.08] bg-black/60 backdrop-blur-sm text-white/50 hover:text-white/80 hover:border-white/20 transition-all duration-150 text-sm font-light select-none"
            title="Zoom out"
          >
            −
          </button>
        </div>
      </div>
    );
  },
);

export default DashboardViewer;
