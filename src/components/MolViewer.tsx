'use client';

import { useRef, useEffect, useCallback } from 'react';

interface MolViewerProps {
  proteinPdb: string;
  ligandSdf?: string;
  width?: string;
  height?: string;
  proteinStyle?: 'cartoon' | 'surface' | 'ball_and_stick';
  showSurface?: boolean;
  autoRotate?: boolean;
  onReady?: () => void;
}

export default function MolViewer({
  proteinPdb,
  ligandSdf,
  width = '100%',
  height = '400px',
  proteinStyle = 'cartoon',
  showSurface = false,
  autoRotate = false,
  onReady,
}: MolViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const $3DmolRef = useRef<any>(null);
  const ligandModelRef = useRef<any>(null);
  const surfaceIdRef = useRef<any>(null);
  const readyRef = useRef(false);

  // ── Apply protein style to model 0 ──
  const applyProteinStyle = useCallback(
    (viewer: any, $3Dmol: any, style: string, addSurface: boolean) => {
      // Remove existing surface overlay
      if (surfaceIdRef.current !== null) {
        try {
          viewer.removeAllSurfaces();
        } catch {
          // surface may already be gone
        }
        surfaceIdRef.current = null;
      }

      switch (style) {
        case 'cartoon':
          viewer.setStyle({ model: 0 }, { cartoon: { color: 'spectrum' } });
          break;
        case 'surface':
          viewer.setStyle({ model: 0 }, {
            surface: { opacity: 0.85, color: 'white' },
          });
          break;
        case 'ball_and_stick':
          viewer.setStyle({ model: 0 }, {
            stick: { colorscheme: 'Jmol' },
            sphere: { scale: 0.3, colorscheme: 'Jmol' },
          });
          break;
      }

      if (addSurface) {
        surfaceIdRef.current = viewer.addSurface(
          $3Dmol.SurfaceType.VDW,
          { opacity: 0.08, color: 'white' },
          { model: 0 },
        );
      }
    },
    [],
  );

  // ── Initialize viewer ONCE when proteinPdb becomes available ──
  useEffect(() => {
    if (!containerRef.current || !proteinPdb) return;
    // Guard against double-init (StrictMode / HMR)
    if (readyRef.current) return;

    let mounted = true;

    (async () => {
      const $3Dmol = await import('3dmol');
      if (!mounted || !containerRef.current) return;
      $3DmolRef.current = $3Dmol;

      // Wipe the container in case a previous viewer left DOM artifacts
      containerRef.current.innerHTML = '';

      const viewer = $3Dmol.createViewer(containerRef.current, {
        backgroundColor: 'black',
        antialias: true,
      });
      viewerRef.current = viewer;

      // Protein model — always model index 0
      viewer.addModel(proteinPdb, 'pdb');
      applyProteinStyle(viewer, $3Dmol, proteinStyle, showSurface);

      // Initial ligand, if present
      if (ligandSdf) {
        const model = viewer.addModel(ligandSdf, 'sdf');
        model.setStyle({}, {
          stick: { colorscheme: 'greenCarbon', radius: 0.15 },
        });
        ligandModelRef.current = model;
      }

      viewer.zoomTo();
      viewer.render();

      if (autoRotate) {
        viewer.spin('y', 1);
      }

      readyRef.current = true;
      onReady?.();
    })();

    return () => {
      mounted = false;
      if (viewerRef.current) {
        viewerRef.current.clear();
        viewerRef.current = null;
      }
      ligandModelRef.current = null;
      surfaceIdRef.current = null;
      readyRef.current = false;
    };
    // Only re-run when the protein PDB itself changes (new protein = new viewer).
    // ligandSdf changes are handled by the dedicated effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proteinPdb]);

  // ── Swap ligand WITHOUT reinitializing the viewer ──
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !readyRef.current) return;

    // Remove old ligand model
    if (ligandModelRef.current) {
      viewer.removeModel(ligandModelRef.current);
      ligandModelRef.current = null;
    }

    // Add new ligand if provided
    if (ligandSdf) {
      const model = viewer.addModel(ligandSdf, 'sdf');
      model.setStyle({}, {
        stick: { colorscheme: 'greenCarbon', radius: 0.15 },
      });
      ligandModelRef.current = model;
    }

    viewer.zoomTo();
    viewer.render();
  }, [ligandSdf]);

  // ── React to proteinStyle / showSurface changes ──
  useEffect(() => {
    const viewer = viewerRef.current;
    const $3Dmol = $3DmolRef.current;
    if (!viewer || !$3Dmol || !readyRef.current) return;

    applyProteinStyle(viewer, $3Dmol, proteinStyle, showSurface);

    // Re-style ligand in case surface operations altered render state
    if (ligandModelRef.current) {
      ligandModelRef.current.setStyle({}, {
        stick: { colorscheme: 'greenCarbon', radius: 0.15 },
      });
    }

    viewer.render();
  }, [proteinStyle, showSurface, applyProteinStyle]);

  // ── React to autoRotate changes ──
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !readyRef.current) return;

    if (autoRotate) {
      viewer.spin('y', 1);
    } else {
      viewer.spin(false);
    }
  }, [autoRotate]);

  // ── Loading placeholder ──
  if (!proteinPdb) {
    return (
      <div
        className="rounded-xl border border-white/[0.06] bg-black/40 flex items-center justify-center"
        style={{ width, height }}
      >
        <span className="text-xs font-light text-white/20 tracking-wide">
          Loading structure…
        </span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="rounded-xl border border-white/[0.06] bg-black/40 overflow-hidden"
      style={{ width, height, position: 'relative' }}
    />
  );
}
