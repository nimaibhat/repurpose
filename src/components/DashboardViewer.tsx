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
  height?: number;
}

const DashboardViewer = forwardRef<DashboardViewerHandle, DashboardViewerProps>(
  function DashboardViewer(
    { pdbText, initialLigandSdf, initialProteinStyle = 'cartoon', height = 400 },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const viewerRef = useRef<any>(null);
    const $3DmolRef = useRef<any>(null);
    const ligandModelRef = useRef<any>(null);
    const surfaceRef = useRef<any>(null);
    const proteinStyleRef = useRef<ProteinStyle>(initialProteinStyle);
    const ligandVisibleRef = useRef(true);
    const currentLigandSdf = useRef<string | null>(initialLigandSdf || null);
    const readyRef = useRef(false);

    // Apply protein style to the viewer (model 0 is always protein)
    const applyProteinStyle = useCallback((style: ProteinStyle) => {
      const viewer = viewerRef.current;
      const $3Dmol = $3DmolRef.current;
      if (!viewer || !$3Dmol) return;

      // Remove existing surfaces
      viewer.removeAllSurfaces();
      surfaceRef.current = null;

      switch (style) {
        case 'cartoon':
          viewer.setStyle({ model: 0 }, {
            cartoon: { color: 'spectrum', opacity: 0.9 },
          });
          // Add a very subtle translucent surface
          surfaceRef.current = viewer.addSurface($3Dmol.SurfaceType.VDW, {
            opacity: 0.08,
            color: 'white',
          }, { model: 0 });
          break;
        case 'surface':
          viewer.setStyle({ model: 0 }, {
            cartoon: { color: 'spectrum', opacity: 0.3 },
          });
          surfaceRef.current = viewer.addSurface($3Dmol.SurfaceType.VDW, {
            opacity: 0.6,
            color: 'lightblue',
          }, { model: 0 });
          break;
        case 'ballstick':
          viewer.setStyle({ model: 0 }, {
            stick: { radius: 0.1, colorscheme: 'Jmol' },
            sphere: { scale: 0.25, colorscheme: 'Jmol' },
          });
          surfaceRef.current = viewer.addSurface($3Dmol.SurfaceType.VDW, {
            opacity: 0.08,
            color: 'white',
          }, { model: 0 });
          break;
      }

      proteinStyleRef.current = style;
      viewer.render();
    }, []);

    // Add or remove ligand
    const setLigand = useCallback((sdf: string | null) => {
      const viewer = viewerRef.current;
      if (!viewer) return;

      // Remove existing ligand model
      if (ligandModelRef.current) {
        viewer.removeModel(ligandModelRef.current);
        ligandModelRef.current = null;
      }

      currentLigandSdf.current = sdf;

      if (sdf && ligandVisibleRef.current) {
        ligandModelRef.current = viewer.addModel(sdf, 'sdf');
        ligandModelRef.current.setStyle({}, {
          stick: { colorscheme: 'greenCarbon', radius: 0.15 },
        });
      }

      viewer.render();
    }, []);

    const setLigandVisible = useCallback((visible: boolean) => {
      ligandVisibleRef.current = visible;
      if (visible && currentLigandSdf.current) {
        setLigand(currentLigandSdf.current);
      } else if (!visible) {
        const viewer = viewerRef.current;
        if (viewer && ligandModelRef.current) {
          viewer.removeModel(ligandModelRef.current);
          ligandModelRef.current = null;
          viewer.render();
        }
      }
    }, [setLigand]);

    const resetView = useCallback(() => {
      const viewer = viewerRef.current;
      if (!viewer) return;
      viewer.zoomTo();
      viewer.spin('y', 0.3);
      viewer.render();
    }, []);

    const setProteinStyle = useCallback((style: ProteinStyle) => {
      applyProteinStyle(style);
      // Re-add ligand since surface operations can affect model indices
      if (currentLigandSdf.current && ligandVisibleRef.current) {
        const viewer = viewerRef.current;
        if (viewer && ligandModelRef.current) {
          // Re-style ligand in case indices shifted
          ligandModelRef.current.setStyle({}, {
            stick: { colorscheme: 'greenCarbon', radius: 0.15 },
          });
          viewer.render();
        }
      }
    }, [applyProteinStyle]);

    // Expose imperative handle
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
          backgroundColor: 'transparent',
          antialias: true,
        });
        viewerRef.current = viewer;

        // Add protein model (always index 0)
        viewer.addModel(pdbText, 'pdb');
        applyProteinStyle(proteinStyleRef.current);

        // Add initial ligand if provided
        if (initialLigandSdf) {
          ligandModelRef.current = viewer.addModel(initialLigandSdf, 'sdf');
          ligandModelRef.current.setStyle({}, {
            stick: { colorscheme: 'greenCarbon', radius: 0.15 },
          });
          currentLigandSdf.current = initialLigandSdf;
        }

        viewer.zoomTo();
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
        readyRef.current = false;
      };
    }, [pdbText, initialLigandSdf, applyProteinStyle]);

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
