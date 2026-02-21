import json as json_mod
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from fastapi import APIRouter, HTTPException, Depends

from config import Settings, get_settings
from models.schemas import PipelineRequest, PipelineResult
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb
from services.chembl import search_drugs
from services.nvidia_nim import run_diffdock_batch
from services.claude import generate_report
from config import get_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name"

# Create structures directory if it doesn't exist
STRUCTURES_DIR = Path(__file__).parent.parent / "data" / "structures"
STRUCTURES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/", response_model=PipelineResult)
async def run_pipeline(request: PipelineRequest, settings: Settings = Depends(get_settings)):

    # Step 1: Disease → top protein targets
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
            target_chembl_id, drugs = await search_drugs(symbol, limit=50)
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

    # Normalize DiffDock confidence scores from raw (negative, 0 = best)
    # to 0-1 range (1.0 = best). Linear map: 0 → 1.0, -5 → 0.0, clamped.
    for dr in all_docking_results:
        raw = dr["confidence_score"]
        dr["raw_confidence"] = raw
        dr["confidence_score"] = round(max(0.0, min(1.0, (raw + 5.0) / 5.0)), 4)

    # Sort all docking results by confidence
    all_docking_results.sort(key=lambda r: r["confidence_score"], reverse=True)

    # Step 6: Generate AI report using top target's docking results
    report_text = f"# Pipeline for {disease_info['name']}\n\nTarget symbols: {', '.join(target_symbols)}\n\nStructures found: {len(structures)}\n\nDrugs found: {len(all_drugs)}\n\nSuccessful dockings: {len(all_docking_results)}"

    if all_docking_results and settings.anthropic_api_key:
        try:
            # Build drug-to-metadata lookup
            drug_meta = {}
            for d in all_drugs:
                if d.get("name"):
                    drug_meta[d["name"]] = d

            # Use top target for the report (highest-scoring target with docking results)
            top_target = targets[0] if targets else {"symbol": "Unknown", "name": "Unknown"}

            # Build report input from top docking results (up to 10)
            report_input = []
            for dr in all_docking_results[:10]:
                meta = drug_meta.get(dr.get("drug_name", ""), {})
                report_input.append({
                    "drug_name": dr.get("drug_name"),
                    "smiles": dr["smiles"],
                    "confidence_score": dr["confidence_score"],
                    "mechanism": meta.get("mechanism"),
                    "max_phase": meta.get("max_phase"),
                })

            report_result = generate_report(
                api_key=settings.anthropic_api_key,
                disease=disease_info["name"],
                target={"symbol": top_target["symbol"], "name": top_target["name"]},
                results=report_input,
            )

            report_text = report_result["report_text"]

            # Enrich docking results with explanations from the report
            explanation_map = {
                c["drug_name"]: c for c in report_result.get("candidates", [])
            }
            for dr in all_docking_results:
                expl = explanation_map.get(dr.get("drug_name"), {})
                dr["explanation"] = expl.get("explanation", "")
                dr["risk_benefit"] = expl.get("risk_benefit", "")
                dr["priority_rank"] = expl.get("priority_rank")

        except Exception as e:
            print(f"Warning: Report generation failed: {e}")
            # Keep the fallback report_text

    return PipelineResult(
        disease=disease_info["name"],
        targets=targets,
        structures=structures,
        drugs=all_drugs,
        docking_results=all_docking_results,
        report=report_text,
    )


# ─── SSE Streaming Endpoint ─────────────────────────────────────────────────

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json_mod.dumps(data, default=str)}\n\n"


async def _pipeline_stream(request: PipelineRequest) -> AsyncGenerator[str, None]:
    settings = get_settings()

    # Step 1: Targets
    yield _sse_event("step", {"step": 1, "status": "running"})
    try:
        disease_info = await search_disease(request.disease)
        targets = await get_associated_targets(disease_info["id"])
    except OpenTargetsError as e:
        yield _sse_event("step", {"step": 1, "status": "error", "message": str(e)})
        return
    except Exception as e:
        yield _sse_event("step", {"step": 1, "status": "error", "message": f"Open Targets API error: {e}"})
        return
    yield _sse_event("step", {"step": 1, "status": "complete", "data": {
        "disease": disease_info["name"],
        "targets": targets,
    }})

    target_symbols = [t["symbol"] for t in targets]

    # Step 2: Structures
    yield _sse_event("step", {"step": 2, "status": "running"})
    structures = []
    for symbol in target_symbols:
        try:
            pdb_id = await search_pdb(symbol)
            if pdb_id:
                pdb_text = await download_pdb(pdb_id)
                resolution = await get_resolution(pdb_id)
                pdb_file_path = STRUCTURES_DIR / f"{pdb_id}.pdb"
                pdb_file_path.write_text(pdb_text)
                structures.append({
                    "symbol": symbol, "pdb_id": pdb_id,
                    "resolution": resolution, "source": "rcsb",
                    "file_path": str(pdb_file_path),
                })
            else:
                uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
                af_id = f"AF-{uniprot_id}-F1"
                pdb_file_path = STRUCTURES_DIR / f"{af_id}.pdb"
                pdb_file_path.write_text(pdb_text)
                structures.append({
                    "symbol": symbol, "pdb_id": af_id,
                    "resolution": None, "source": "alphafold",
                    "file_path": str(pdb_file_path),
                })
        except Exception as e:
            print(f"Warning: Could not fetch structure for {symbol}: {e}")
            continue
    yield _sse_event("step", {"step": 2, "status": "complete", "data": {
        "structures": structures,
    }})

    # Step 3: Drugs
    yield _sse_event("step", {"step": 3, "status": "running"})
    all_drugs = []
    for symbol in target_symbols:
        try:
            target_chembl_id, drugs = await search_drugs(symbol, limit=20)
            for drug in drugs:
                drug["target_symbol"] = symbol
                drug["target_chembl_id"] = target_chembl_id
            all_drugs.extend(drugs)
        except Exception as e:
            print(f"Warning: Could not fetch drugs for {symbol}: {e}")
            continue
    yield _sse_event("step", {"step": 3, "status": "complete", "data": {
        "drugs": all_drugs,
    }})

    # Step 4: Docking
    yield _sse_event("step", {"step": 4, "status": "running"})
    if not settings.nvidia_nim_api_key:
        yield _sse_event("step", {"step": 4, "status": "error", "message": "NVIDIA NIM API key not configured"})
        return

    all_docking_results = []
    for structure in structures:
        symbol = structure["symbol"]
        pdb_id = structure["pdb_id"]
        target_drugs = [d for d in all_drugs if d["target_symbol"] == symbol]
        if not target_drugs:
            print(f"Warning: No drugs found for {symbol}, skipping docking")
            continue
        pdb_file_path = Path(structure["file_path"])
        if not pdb_file_path.exists():
            print(f"Warning: PDB file not found for {symbol}: {pdb_file_path}")
            continue
        pdb_text = pdb_file_path.read_text()
        try:
            docking_results = await run_diffdock_batch(
                api_key=settings.nvidia_nim_api_key,
                pdb_text=pdb_text,
                drugs=target_drugs,
            )
            for result in docking_results:
                result["pdb_id"] = pdb_id
                result["target_symbol"] = symbol
            all_docking_results.extend(docking_results)
            print(f"Docked {len(docking_results)} compounds successfully for {symbol} ({pdb_id})")
        except Exception as e:
            print(f"Warning: Docking failed for {symbol}: {e}")
            continue

    # Normalize confidence scores
    for dr in all_docking_results:
        raw = dr["confidence_score"]
        dr["raw_confidence"] = raw
        dr["confidence_score"] = round(max(0.0, min(1.0, (raw + 5.0) / 5.0)), 4)
    all_docking_results.sort(key=lambda r: r["confidence_score"], reverse=True)

    yield _sse_event("step", {"step": 4, "status": "complete", "data": {
        "docking_results": all_docking_results,
    }})

    # Step 5: Report
    yield _sse_event("step", {"step": 5, "status": "running"})
    report_text = (
        f"# Pipeline for {disease_info['name']}\n\n"
        f"Target symbols: {', '.join(target_symbols)}\n\n"
        f"Structures found: {len(structures)}\n\n"
        f"Drugs found: {len(all_drugs)}\n\n"
        f"Successful dockings: {len(all_docking_results)}"
    )

    if all_docking_results and settings.anthropic_api_key:
        try:
            drug_meta = {}
            for d in all_drugs:
                if d.get("name"):
                    drug_meta[d["name"]] = d

            top_target = targets[0] if targets else {"symbol": "Unknown", "name": "Unknown"}
            report_input = []
            for dr in all_docking_results[:10]:
                meta = drug_meta.get(dr.get("drug_name", ""), {})
                report_input.append({
                    "drug_name": dr.get("drug_name"),
                    "smiles": dr["smiles"],
                    "confidence_score": dr["confidence_score"],
                    "mechanism": meta.get("mechanism"),
                    "max_phase": meta.get("max_phase"),
                })

            report_result = generate_report(
                api_key=settings.anthropic_api_key,
                disease=disease_info["name"],
                target={"symbol": top_target["symbol"], "name": top_target["name"]},
                results=report_input,
            )

            report_text = report_result["report_text"]

            explanation_map = {
                c["drug_name"]: c for c in report_result.get("candidates", [])
            }
            for dr in all_docking_results:
                expl = explanation_map.get(dr.get("drug_name"), {})
                dr["explanation"] = expl.get("explanation", "")
                dr["risk_benefit"] = expl.get("risk_benefit", "")
                dr["priority_rank"] = expl.get("priority_rank")

        except Exception as e:
            print(f"Warning: Report generation failed: {e}")

    yield _sse_event("done", {"step": 5, "status": "complete", "data": {
        "report": report_text,
        "docking_results": all_docking_results,
    }})


@router.post("/stream")
async def stream_pipeline(request: PipelineRequest):
    return StreamingResponse(
        _pipeline_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
