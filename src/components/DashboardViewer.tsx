'use client';

import { useRef, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';

export type ProteinStyle = 'cartoon' | 'surface' | 'ballstick';

export interface DashboardViewerHandle {
  setLigand: (sdf: string | null) => void;
  setProteinStyle: (style: ProteinStyle) => void;
  setLigandVisible: (visible: boolean) => void;
  resetView: () => void;
}

interface DashboardViewerProps {
  pdbText: string;
  initialLigandSdf?: string;
  initialProteinStyle?: ProteinStyle;
  height?: number | string;
}

const DashboardViewer = forwardRef<DashboardViewerHandle, DashboardViewerProps>(
  function DashboardViewer(
    { pdbText, initialLigandSdf, initialProteinStyle = 'cartoon', height = '100%' },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const viewerRef = useRef<any>(null);
    const $3DmolRef = useRef<any>(null);
    const proteinModelRef = useRef<any>(null);   // stable ref to protein model
    const ligandModelRef = useRef<any>(null);
    const surfaceRef = useRef<any>(null);
    const proteinStyleRef = useRef<ProteinStyle>(initialProteinStyle);
    const ligandVisibleRef = useRef(true);
    const currentLigandSdf = useRef<string | null>(initialLigandSdf || null);
    const readyRef = useRef(false);

    // Apply protein style using model object reference (not fragile index)
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
          // Slightly transparent cartoon so ligand is visible through it
          viewer.setStyle(sel, {
            cartoon: { color: 'spectrum', opacity: 0.75 },
          });
          break;
        case 'surface':
          viewer.setStyle(sel, {
            cartoon: { color: 'spectrum', opacity: 0.3 },
          });
          surfaceRef.current = viewer.addSurface($3Dmol.SurfaceType.VDW, {
            opacity: 0.6,
            color: 'lightblue',
          }, sel);
          break;
        case 'ballstick':
          viewer.setStyle(sel, {
            stick: { radius: 0.1, colorscheme: 'Jmol' },
            sphere: { scale: 0.25, colorscheme: 'Jmol' },
          });
          break;
      }

      proteinStyleRef.current = style;
      viewer.render();
    }, []);

    // Style the ligand model
    const styleLigand = useCallback((model: any) => {
      if (!model) return;
      model.setStyle({}, {
        stick: { colorscheme: 'greenCarbon', radius: 0.18 },
        sphere: { colorscheme: 'greenCarbon', scale: 0.22 },
      });
    }, []);

    // Add or swap ligand; zoom to binding site when ligand is present
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

        // Zoom to the ligand binding site so it's clearly visible
        viewer.zoomTo({ model: model }, 1000);
      } else {
        // No ligand — zoom to whole protein
        viewer.zoomTo({ model: proteinModelRef.current });
      }

      viewer.render();
    }, [styleLigand]);

    const setLigandVisible = useCallback((visible: boolean) => {
      const viewer = viewerRef.current;
      ligandVisibleRef.current = visible;

      if (visible && currentLigandSdf.current) {
        // Re-add ligand
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
          // Re-apply protein style after model removal to keep it correct
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
      // Re-style ligand after protein style change to ensure it stays visible
      if (ligandModelRef.current && ligandVisibleRef.current) {
        styleLigand(ligandModelRef.current);
        viewerRef.current?.render();
      }
    }, [applyProteinStyle, styleLigand]);

    useImperativeHandle(ref, () => ({
      setLigand,
      setProteinStyle,
      setLigandVisible,
      resetView,
    }), [setLigand, setProteinStyle, setLigandVisible, resetView]);

    // Initialize viewer once
    useEffect(() => {
      if (!containerRef.current || !pdbText || readyRef.current) return;

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

        // Add protein — store model reference
        proteinModelRef.current = viewer.addModel(pdbText, 'pdb');
        applyProteinStyle(proteinStyleRef.current);

        if (initialLigandSdf) {
          const ligand = viewer.addModel(initialLigandSdf, 'sdf');
          styleLigand(ligand);
          ligandModelRef.current = ligand;
          currentLigandSdf.current = initialLigandSdf;
          // Zoom to ligand so binding site is in focus
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

    // Resize on container change
    useEffect(() => {
      const viewer = viewerRef.current;
      if (viewer) {
        viewer.resize();
        viewer.render();
      }
    }, [height]);

    return (
      <div
        ref={containerRef}
        className="w-full rounded-xl border border-white/[0.06] bg-black/40 overflow-hidden"
        style={{ height, position: 'relative' }}
      />
    );
  },
);

export default DashboardViewer;
