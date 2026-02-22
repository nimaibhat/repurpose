import asyncio
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
from services.admet import predict_admet_batch, build_admet_summary
from services.gnn_affinity import predict_binding_affinity
from services.novelty import check_novelty_batch
from config import get_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name"

# Create structures directory if it doesn't exist
STRUCTURES_DIR = Path(__file__).parent.parent / "data" / "structures"
STRUCTURES_DIR.mkdir(parents=True, exist_ok=True)


async def fetch_structure_for_symbol(symbol: str) -> dict | None:
    """Fetch structure for a single protein symbol."""
    try:
        # Try RCSB first
        pdb_id = await search_pdb(symbol)
        if pdb_id:
            pdb_text = await download_pdb(pdb_id)
            resolution = await get_resolution(pdb_id)

            # Save PDB file to disk
            pdb_file_path = STRUCTURES_DIR / f"{pdb_id}.pdb"
            pdb_file_path.write_text(pdb_text)

            return {
                "symbol": symbol,
                "pdb_id": pdb_id,
                "resolution": resolution,
                "source": "rcsb",
                "file_path": str(pdb_file_path),
            }
        else:
            # Fallback to AlphaFold
            uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
            af_id = f"AF-{uniprot_id}-F1"

            # Save AlphaFold PDB file to disk
            pdb_file_path = STRUCTURES_DIR / f"{af_id}.pdb"
            pdb_file_path.write_text(pdb_text)

            return {
                "symbol": symbol,
                "pdb_id": af_id,
                "resolution": None,
                "source": "alphafold",
                "file_path": str(pdb_file_path),
            }
    except Exception as e:
        print(f"Warning: Could not fetch structure for {symbol}: {e}")
        return None


async def fetch_drugs_for_symbol(symbol: str) -> list[dict]:
    """Fetch drugs for a single protein symbol."""
    try:
        target_chembl_id, drugs = await search_drugs(symbol, limit=50)
        # Add the symbol and target_chembl_id to each drug for tracking
        for drug in drugs:
            drug["target_symbol"] = symbol
            drug["target_chembl_id"] = target_chembl_id
        return drugs
    except Exception as e:
        print(f"Warning: Could not fetch drugs for {symbol}: {e}")
        return []


@router.post("/", response_model=PipelineResult)
async def run_pipeline(request: PipelineRequest, settings: Settings = Depends(get_settings)):

    # Step 1: Disease → top protein targets
    try:
        disease_info = await search_disease(request.disease)
        targets = await get_associated_targets(disease_info["id"], max_targets=request.max_targets)
    except OpenTargetsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Targets API error: {e}")

    # Step 2: Extract target symbols
    target_symbols = [target["symbol"] for target in targets]

    # Step 3: Fetch structures in parallel (batches of 10)
    print(f"Fetching structures for {len(target_symbols)} targets...")
    structures = []
    batch_size = 10
    for i in range(0, len(target_symbols), batch_size):
        batch = target_symbols[i:i + batch_size]
        batch_results = await asyncio.gather(*[fetch_structure_for_symbol(s) for s in batch])
        structures.extend([s for s in batch_results if s is not None])
        print(f"Processed {min(i + batch_size, len(target_symbols))}/{len(target_symbols)} structures")

    # Step 4: Fetch drugs in parallel (batches of 10)
    print(f"Fetching drugs for {len(target_symbols)} targets...")
    all_drugs = []
    for i in range(0, len(target_symbols), batch_size):
        batch = target_symbols[i:i + batch_size]
        batch_results = await asyncio.gather(*[fetch_drugs_for_symbol(s) for s in batch])
        for drugs_list in batch_results:
            all_drugs.extend(drugs_list)
        print(f"Processed {min(i + batch_size, len(target_symbols))}/{len(target_symbols)} drug searches")

    # Deduplicate drugs by name and cap to max_candidates
    seen_drug_names: set[str] = set()
    capped_drugs: list[dict] = []
    for d in all_drugs:
        key = d.get("name") or d.get("smiles", "")
        if key not in seen_drug_names:
            seen_drug_names.add(key)
            capped_drugs.append(d)
    if request.max_candidates > 0 and len(capped_drugs) > request.max_candidates:
        capped_drugs = capped_drugs[:request.max_candidates]
    print(f"Capped drugs from {len(all_drugs)} to {len(capped_drugs)} (max_candidates={request.max_candidates or 'unlimited'})")

    # Step 5: Run docking simulations
    settings = get_settings()
    if not settings.nvidia_nim_api_key:
        raise HTTPException(status_code=500, detail="NVIDIA NIM API key not configured")

    all_docking_results = []
    for structure in structures:
        symbol = structure["symbol"]
        pdb_id = structure["pdb_id"]

        # Find drugs for this target
        target_drugs = [d for d in capped_drugs if d["target_symbol"] == symbol]
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
                pdb_id=pdb_id,
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

    # GNN binding affinity predictions
    affinity_count = 0
    for dr in all_docking_results:
        pdb_path = STRUCTURES_DIR / f"{dr['pdb_id']}.pdb"
        has_sdf = bool(dr.get("ligand_sdf"))
        if pdb_path.exists() and has_sdf:
            affinity = predict_binding_affinity(pdb_path.read_text(), dr["ligand_sdf"])
            dr["predicted_pkd"] = affinity["predicted_pkd"] if affinity else None
            dr["predicted_kd_nm"] = affinity["predicted_kd_nm"] if affinity else None
            if affinity:
                dr["affinity_score"] = round(max(0.0, min(1.0, (affinity["predicted_pkd"] - 2) / 10)), 4)
                affinity_count += 1
                print(f"  GNN {dr.get('drug_name')}: pKd={affinity['predicted_pkd']}, Kd={affinity['predicted_kd_nm']} nM, score={dr['affinity_score']}")
            else:
                dr["affinity_score"] = None
                print(f"  GNN {dr.get('drug_name')}: featurization failed (pdb={dr['pdb_id']}, sdf_len={len(dr['ligand_sdf'])})")
        else:
            dr["predicted_pkd"] = None
            dr["predicted_kd_nm"] = None
            dr["affinity_score"] = None
            print(f"  GNN skip {dr.get('drug_name')}: pdb_exists={pdb_path.exists()}, has_sdf={has_sdf}")
    print(f"GNN affinity: {affinity_count}/{len(all_docking_results)} predicted")

    # Step 5: ADMET predictions
    admet_smiles = [dr["smiles"] for dr in all_docking_results]
    admet_names = [dr.get("drug_name") for dr in all_docking_results]
    admet_raw = predict_admet_batch(admet_smiles, drug_names=admet_names)

    # Attach flat ADMET summary to each docking result
    for dr, raw in zip(all_docking_results, admet_raw):
        dr["admet"] = build_admet_summary(raw)

    # Compute combined score and re-sort
    for dr in all_docking_results:
        if dr.get("affinity_score") is not None:
            dr["combined_score"] = round(
                dr["confidence_score"] * 0.40
                + dr["affinity_score"] * 0.15
                + dr["admet"]["overall_score"] * 0.45, 4
            )
        else:
            dr["combined_score"] = round(
                dr["confidence_score"] * 0.55 + dr["admet"]["overall_score"] * 0.45, 4
            )
    all_docking_results.sort(key=lambda r: r["combined_score"], reverse=True)

    # Step 6: Novelty check
    if settings.anthropic_api_key and all_docking_results:
        try:
            novelty_candidates = [
                {"drug_name": dr.get("drug_name", "Unknown"), "mechanism": dr.get("mechanism")}
                for dr in all_docking_results
            ]
            novelty_results = await check_novelty_batch(
                settings.anthropic_api_key, disease_info["name"], novelty_candidates
            )
            for dr, nr in zip(all_docking_results, novelty_results):
                dr["novelty_status"] = nr["novelty_status"]
                dr["novelty_detail"] = nr["novelty_detail"]
        except Exception as e:
            print(f"Warning: Novelty check failed: {e}")
            for dr in all_docking_results:
                dr["novelty_status"] = "unknown"
                dr["novelty_detail"] = ""
    else:
        for dr in all_docking_results:
            dr["novelty_status"] = "unknown"
            dr["novelty_detail"] = ""

    # Step 7: Generate AI report
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
                    "admet": dr["admet"],
                    "combined_score": dr["combined_score"],
                    "predicted_pkd": dr.get("predicted_pkd"),
                    "predicted_kd_nm": dr.get("predicted_kd_nm"),
                    "affinity_score": dr.get("affinity_score"),
                    "novelty_status": dr.get("novelty_status"),
                    "novelty_detail": dr.get("novelty_detail"),
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

    # Build candidates list with combined ranking
    candidates = []
    for rank, dr in enumerate(all_docking_results, 1):
        meta = {}
        for d in all_drugs:
            if d.get("name") == dr.get("drug_name"):
                meta = d
                break
        candidates.append({
            "rank": rank,
            "drug_name": dr.get("drug_name"),
            "smiles": dr["smiles"],
            "confidence_score": dr["confidence_score"],
            "combined_score": dr["combined_score"],
            "mechanism": meta.get("mechanism"),
            "explanation": dr.get("explanation", ""),
            "admet": dr["admet"],
            "predicted_pkd": dr.get("predicted_pkd"),
            "predicted_kd_nm": dr.get("predicted_kd_nm"),
            "affinity_score": dr.get("affinity_score"),
            "novelty_status": dr.get("novelty_status"),
            "novelty_detail": dr.get("novelty_detail"),
        })

    return PipelineResult(
        disease=disease_info["name"],
        targets=targets,
        structures=structures,
        drugs=all_drugs,
        docking_results=all_docking_results,
        candidates=candidates,
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
        targets = await get_associated_targets(disease_info["id"], max_targets=request.max_targets)
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

    # Deduplicate drugs by name and cap to max_candidates
    seen_drug_names: set[str] = set()
    capped_drugs: list[dict] = []
    for d in all_drugs:
        key = d.get("name") or d.get("smiles", "")
        if key not in seen_drug_names:
            seen_drug_names.add(key)
            capped_drugs.append(d)
    if request.max_candidates > 0 and len(capped_drugs) > request.max_candidates:
        capped_drugs = capped_drugs[:request.max_candidates]
    print(f"Capped drugs from {len(all_drugs)} to {len(capped_drugs)} (max_candidates={request.max_candidates or 'unlimited'})")

    # Step 4: Docking
    yield _sse_event("step", {"step": 4, "status": "running"})
    if not settings.nvidia_nim_api_key:
        yield _sse_event("step", {"step": 4, "status": "error", "message": "NVIDIA NIM API key not configured"})
        return

    all_docking_results = []
    for structure in structures:
        symbol = structure["symbol"]
        pdb_id = structure["pdb_id"]
        target_drugs = [d for d in capped_drugs if d["target_symbol"] == symbol]
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
                pdb_id=pdb_id,
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

    # GNN binding affinity predictions
    affinity_count = 0
    for dr in all_docking_results:
        pdb_path = STRUCTURES_DIR / f"{dr['pdb_id']}.pdb"
        has_sdf = bool(dr.get("ligand_sdf"))
        if pdb_path.exists() and has_sdf:
            affinity = predict_binding_affinity(pdb_path.read_text(), dr["ligand_sdf"])
            dr["predicted_pkd"] = affinity["predicted_pkd"] if affinity else None
            dr["predicted_kd_nm"] = affinity["predicted_kd_nm"] if affinity else None
            if affinity:
                dr["affinity_score"] = round(max(0.0, min(1.0, (affinity["predicted_pkd"] - 2) / 10)), 4)
                affinity_count += 1
                print(f"  GNN {dr.get('drug_name')}: pKd={affinity['predicted_pkd']}, Kd={affinity['predicted_kd_nm']} nM, score={dr['affinity_score']}")
            else:
                dr["affinity_score"] = None
                print(f"  GNN {dr.get('drug_name')}: featurization failed (pdb={dr['pdb_id']}, sdf_len={len(dr['ligand_sdf'])})")
        else:
            dr["predicted_pkd"] = None
            dr["predicted_kd_nm"] = None
            dr["affinity_score"] = None
            print(f"  GNN skip {dr.get('drug_name')}: pdb_exists={pdb_path.exists()}, has_sdf={has_sdf}")
    print(f"GNN affinity: {affinity_count}/{len(all_docking_results)} predicted")

    top_drug_name = all_docking_results[0].get("drug_name", "Unknown") if all_docking_results else "N/A"
    top_drug_score = all_docking_results[0]["confidence_score"] if all_docking_results else 0
    affinity_msg = f" | Affinity: {affinity_count} predicted" if affinity_count else ""
    yield _sse_event("step", {"step": 4, "status": "complete",
        "message": f"Docked {len(all_docking_results)} compounds. Top: {top_drug_name} ({top_drug_score}){affinity_msg}",
        "data": {"docking_results": all_docking_results},
    })

    # Step 5: ADMET
    yield _sse_event("step", {"step": 5, "status": "running",
        "message": f"Running ADMET safety analysis on {len(all_docking_results)} docked compounds...",
    })
    admet_smiles = [dr["smiles"] for dr in all_docking_results]
    admet_names = [dr.get("drug_name") for dr in all_docking_results]
    admet_raw = predict_admet_batch(admet_smiles, drug_names=admet_names)

    # Attach flat ADMET summary to each docking result
    for dr, raw in zip(all_docking_results, admet_raw):
        dr["admet"] = build_admet_summary(raw)

    # Compute combined score and re-sort
    for dr in all_docking_results:
        if dr.get("affinity_score") is not None:
            dr["combined_score"] = round(
                dr["confidence_score"] * 0.40
                + dr["affinity_score"] * 0.15
                + dr["admet"]["overall_score"] * 0.45, 4
            )
        else:
            dr["combined_score"] = round(
                dr["confidence_score"] * 0.55 + dr["admet"]["overall_score"] * 0.45, 4
            )
    all_docking_results.sort(key=lambda r: r["combined_score"], reverse=True)

    n_pass = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "pass")
    n_warn = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "warn")
    n_fail = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "fail")
    admet_results = [{"drug_name": dr.get("drug_name"), **dr["admet"]} for dr in all_docking_results]

    yield _sse_event("step", {"step": 5, "status": "complete",
        "message": f"{n_pass} safe, {n_warn} caution, {n_fail} risk detected",
        "data": {"admet_results": admet_results},
    })

    # Step 6: Novelty
    yield _sse_event("step", {"step": 6, "status": "running",
        "message": "Checking drug novelty for this disease...",
    })
    if settings.anthropic_api_key and all_docking_results:
        try:
            novelty_candidates = [
                {"drug_name": dr.get("drug_name", "Unknown"), "mechanism": dr.get("mechanism")}
                for dr in all_docking_results
            ]
            novelty_results = await check_novelty_batch(
                settings.anthropic_api_key, disease_info["name"], novelty_candidates
            )
            for dr, nr in zip(all_docking_results, novelty_results):
                dr["novelty_status"] = nr["novelty_status"]
                dr["novelty_detail"] = nr["novelty_detail"]
            n_novel = sum(1 for nr in novelty_results if nr["novelty_status"] == "novel")
            n_known = sum(1 for nr in novelty_results if nr["novelty_status"] in ("approved", "in_trials"))
            yield _sse_event("step", {"step": 6, "status": "complete",
                "message": f"{n_novel} novel, {n_known} known candidates identified",
            })
        except Exception as e:
            print(f"Warning: Novelty check failed: {e}")
            for dr in all_docking_results:
                dr["novelty_status"] = "unknown"
                dr["novelty_detail"] = ""
            yield _sse_event("step", {"step": 6, "status": "complete",
                "message": "Novelty check skipped",
            })
    else:
        for dr in all_docking_results:
            dr["novelty_status"] = "unknown"
            dr["novelty_detail"] = ""
        yield _sse_event("step", {"step": 6, "status": "complete",
            "message": "Novelty check skipped (no API key)",
        })

    # Step 7: Report
    yield _sse_event("step", {"step": 7, "status": "running",
        "message": "Generating research report with safety analysis...",
    })
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
                    "admet": dr["admet"],
                    "combined_score": dr["combined_score"],
                    "predicted_pkd": dr.get("predicted_pkd"),
                    "predicted_kd_nm": dr.get("predicted_kd_nm"),
                    "affinity_score": dr.get("affinity_score"),
                    "novelty_status": dr.get("novelty_status"),
                    "novelty_detail": dr.get("novelty_detail"),
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

    # Build candidates list with combined ranking
    candidates = []
    for rank, dr in enumerate(all_docking_results, 1):
        meta = {}
        for d in all_drugs:
            if d.get("name") == dr.get("drug_name"):
                meta = d
                break
        candidates.append({
            "rank": rank,
            "drug_name": dr.get("drug_name"),
            "smiles": dr["smiles"],
            "confidence_score": dr["confidence_score"],
            "combined_score": dr["combined_score"],
            "mechanism": meta.get("mechanism"),
            "explanation": dr.get("explanation", ""),
            "admet": dr["admet"],
            "predicted_pkd": dr.get("predicted_pkd"),
            "predicted_kd_nm": dr.get("predicted_kd_nm"),
            "affinity_score": dr.get("affinity_score"),
            "novelty_status": dr.get("novelty_status"),
            "novelty_detail": dr.get("novelty_detail"),
        })

    yield _sse_event("done", {"step": 7, "status": "complete", "data": {
        "report": report_text,
        "candidates": candidates,
        "docking_results": all_docking_results,
        "admet_results": admet_results,
    }})


@router.post("/stream")
async def stream_pipeline(request: PipelineRequest):
    return StreamingResponse(
        _pipeline_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
