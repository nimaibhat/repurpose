from pathlib import Path
from fastapi import APIRouter, HTTPException

from models.schemas import PipelineRequest, PipelineResult
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb
from services.chembl import search_drugs
from services.nvidia_nim import run_diffdock_batch
from config import get_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# Create structures directory if it doesn't exist
STRUCTURES_DIR = Path(__file__).parent.parent / "data" / "structures"
STRUCTURES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/", response_model=PipelineResult)
async def run_pipeline(request: PipelineRequest):
    # Step 1: Get targets from Open Targets
    try:
        disease_info = await search_disease(request.disease)
        targets = await get_associated_targets(disease_info["id"])
    except OpenTargetsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Targets API error: {e}")
    
    # Step 2: Extract target symbols
    target_symbols = [target["symbol"] for target in targets]
    
    # Step 3: For each symbol, get structures from RCSB
    structures = []
    for symbol in target_symbols:
        try:
            # Try RCSB first
            pdb_id = await search_pdb(symbol)
            if pdb_id:
                pdb_text = await download_pdb(pdb_id)
                resolution = await get_resolution(pdb_id)
                
                # Save PDB file to disk
                pdb_file_path = STRUCTURES_DIR / f"{pdb_id}.pdb"
                pdb_file_path.write_text(pdb_text)
                
                structures.append({
                    "symbol": symbol,
                    "pdb_id": pdb_id,
                    "resolution": resolution,
                    "source": "rcsb",
                    "file_path": str(pdb_file_path),
                })
            else:
                # Fallback to AlphaFold
                uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
                af_id = f"AF-{uniprot_id}-F1"
                
                # Save AlphaFold PDB file to disk
                pdb_file_path = STRUCTURES_DIR / f"{af_id}.pdb"
                pdb_file_path.write_text(pdb_text)
                
                structures.append({
                    "symbol": symbol,
                    "pdb_id": af_id,
                    "resolution": None,
                    "source": "alphafold",
                    "file_path": str(pdb_file_path),
                })
        except Exception as e:
            # Skip this target if structure retrieval fails
            print(f"Warning: Could not fetch structure for {symbol}: {e}")
            continue
    
    # Step 4: For each symbol, get compounds from ChEMBL
    all_drugs = []
    for symbol in target_symbols:
        try:
            target_chembl_id, drugs = await search_drugs(symbol, limit=20)
            # Add the symbol and target_chembl_id to each drug for tracking
            for drug in drugs:
                drug["target_symbol"] = symbol
                drug["target_chembl_id"] = target_chembl_id
            all_drugs.extend(drugs)
        except Exception as e:
            print(f"Warning: Could not fetch drugs for {symbol}: {e}")
            continue
    
    # Step 5: Run docking simulations
    settings = get_settings()
    if not settings.nvidia_nim_api_key:
        raise HTTPException(status_code=500, detail="NVIDIA NIM API key not configured")
    
    all_docking_results = []
    for structure in structures:
        symbol = structure["symbol"]
        pdb_id = structure["pdb_id"]
        
        # Find drugs for this target
        target_drugs = [d for d in all_drugs if d["target_symbol"] == symbol]
        if not target_drugs:
            print(f"Warning: No drugs found for {symbol}, skipping docking")
            continue
        
        # Load PDB file
        pdb_file_path = Path(structure["file_path"])
        if not pdb_file_path.exists():
            print(f"Warning: PDB file not found for {symbol}: {pdb_file_path}")
            continue
        
        pdb_text = pdb_file_path.read_text()
        
        # Run docking for this structure with all its drugs
        try:
            docking_results = await run_diffdock_batch(
                api_key=settings.nvidia_nim_api_key,
                pdb_text=pdb_text,
                drugs=target_drugs,
            )
            
            # Add structure info to each result
            for result in docking_results:
                result["pdb_id"] = pdb_id
                result["target_symbol"] = symbol
            
            all_docking_results.extend(docking_results)
            print(f"Docked {len(docking_results)} compounds successfully for {symbol} ({pdb_id})")
        except Exception as e:
            print(f"Warning: Docking failed for {symbol}: {e}")
            continue
    
    # Sort all docking results by confidence
    all_docking_results.sort(key=lambda r: r["confidence_score"], reverse=True)
    
    # TODO: Step 6: Generate report
    
    return PipelineResult(
        disease=disease_info["name"],
        targets=targets,
        structures=structures,
        drugs=all_drugs,
        docking_results=all_docking_results,
        report=f"# Pipeline for {disease_info['name']}\n\nTarget symbols: {', '.join(target_symbols)}\n\nStructures found: {len(structures)}\n\nDrugs found: {len(all_drugs)}\n\nSuccessful dockings: {len(all_docking_results)}",
    )
