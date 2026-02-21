"""
Target-First pipeline: accepts a protein target symbol directly,
skipping the Cancer-to-Protein mapping stage.

Route prefix: /pipeline/protein
Full endpoints (with /api prefix in main.py):
  POST /api/pipeline/protein/stream  — SSE streaming
"""
import json as json_mod
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from config import get_settings
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb
from services.chembl import search_drugs
from services.nvidia_nim import run_diffdock_batch
from services.claude import generate_report
from services.admet import predict_admet_batch, build_admet_summary
from services.registry import save_protein, save_drugs

router = APIRouter(prefix="/pipeline/protein", tags=["pipeline-protein"])

STRUCTURES_DIR = Path(__file__).parent.parent / "data" / "structures"
STRUCTURES_DIR.mkdir(parents=True, exist_ok=True)


class ProteinPipelineRequest(BaseModel):
    target_id: str          # protein symbol, e.g. "EGFR"
    max_candidates: int = 25


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json_mod.dumps(data, default=str)}\n\n"


async def _protein_pipeline_stream(
    request: ProteinPipelineRequest,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    symbol = request.target_id.strip().upper()

    # ── Step 1: Target ────────────────────────────────────────────────────────
    yield _sse_event("step", {"step": 1, "status": "running"})
    yield _sse_event("step", {
        "step": 1,
        "status": "complete",
        "data": {
            "disease": f"{symbol} Target Analysis",
            "targets": [{
                "ensembl_id": symbol,
                "symbol": symbol,
                "name": symbol,
                "score": 1.0,
            }],
        },
    })

    # ── Step 2: Structures ────────────────────────────────────────────────────
    yield _sse_event("step", {"step": 2, "status": "running"})
    structures: list[dict] = []
    try:
        pdb_id = await search_pdb(symbol)
        if pdb_id:
            pdb_text = await download_pdb(pdb_id)
            resolution = await get_resolution(pdb_id)
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
            uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
            af_id = f"AF-{uniprot_id}-F1"
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
        yield _sse_event("step", {
            "step": 2,
            "status": "error",
            "message": f"Could not fetch structure for {symbol}: {e}",
        })
        return

    yield _sse_event("step", {"step": 2, "status": "complete", "data": {"structures": structures}})

    # ── Step 3: Drugs ─────────────────────────────────────────────────────────
    yield _sse_event("step", {"step": 3, "status": "running"})
    all_drugs: list[dict] = []
    try:
        target_chembl_id, drugs = await search_drugs(symbol, limit=50)
        for drug in drugs:
            drug["target_symbol"] = symbol
            drug["target_chembl_id"] = target_chembl_id
        all_drugs.extend(drugs)
    except Exception as e:
        print(f"Warning: Could not fetch drugs for {symbol}: {e}")

    # Persist to Supabase registry
    save_protein(settings, symbol, symbol)
    save_drugs(settings, all_drugs)

    yield _sse_event("step", {"step": 3, "status": "complete", "data": {"drugs": all_drugs}})

    # Deduplicate and cap
    seen: set[str] = set()
    capped_drugs: list[dict] = []
    for d in all_drugs:
        key = d.get("name") or d.get("smiles", "")
        if key not in seen:
            seen.add(key)
            capped_drugs.append(d)
    if len(capped_drugs) > request.max_candidates:
        capped_drugs = capped_drugs[: request.max_candidates]
    print(f"Capped drugs from {len(all_drugs)} to {len(capped_drugs)}")

    # ── Step 4: Docking ───────────────────────────────────────────────────────
    yield _sse_event("step", {"step": 4, "status": "running"})
    if not settings.nvidia_nim_api_key:
        yield _sse_event("step", {
            "step": 4,
            "status": "error",
            "message": "NVIDIA NIM API key not configured",
        })
        return

    all_docking_results: list[dict] = []
    if structures and capped_drugs:
        structure = structures[0]
        pdb_file_path = Path(structure["file_path"])
        if pdb_file_path.exists():
            pdb_text_for_docking = pdb_file_path.read_text()
            try:
                docking_results = await run_diffdock_batch(
                    api_key=settings.nvidia_nim_api_key,
                    pdb_text=pdb_text_for_docking,
                    drugs=capped_drugs,
                )
                for result in docking_results:
                    result["pdb_id"] = structure["pdb_id"]
                    result["target_symbol"] = symbol
                all_docking_results.extend(docking_results)
                print(f"Docked {len(docking_results)} compounds for {symbol}")
            except Exception as e:
                print(f"Warning: Docking failed for {symbol}: {e}")

    # Normalize DiffDock confidence scores (raw 0 = best, -5 = worst → 0-1)
    for dr in all_docking_results:
        raw = dr["confidence_score"]
        dr["raw_confidence"] = raw
        dr["confidence_score"] = round(max(0.0, min(1.0, (raw + 5.0) / 5.0)), 4)
    all_docking_results.sort(key=lambda r: r["confidence_score"], reverse=True)

    top_name = all_docking_results[0].get("drug_name", "Unknown") if all_docking_results else "N/A"
    top_score = all_docking_results[0]["confidence_score"] if all_docking_results else 0
    yield _sse_event("step", {
        "step": 4,
        "status": "complete",
        "message": f"Docked {len(all_docking_results)} compounds. Top: {top_name} ({top_score})",
        "data": {"docking_results": all_docking_results},
    })

    # ── Step 5: ADMET ─────────────────────────────────────────────────────────
    yield _sse_event("step", {
        "step": 5,
        "status": "running",
        "message": f"Running ADMET safety analysis on {len(all_docking_results)} docked compounds...",
    })
    admet_smiles = [dr["smiles"] for dr in all_docking_results]
    admet_names = [dr.get("drug_name") for dr in all_docking_results]
    admet_raw = predict_admet_batch(admet_smiles, drug_names=admet_names)

    for dr, raw in zip(all_docking_results, admet_raw):
        dr["admet"] = build_admet_summary(raw)

    for dr in all_docking_results:
        dr["combined_score"] = round(
            dr["confidence_score"] * 0.6 + dr["admet"]["overall_score"] * 0.4, 4
        )
    all_docking_results.sort(key=lambda r: r["combined_score"], reverse=True)

    n_pass = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "pass")
    n_warn = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "warn")
    n_fail = sum(1 for dr in all_docking_results if dr["admet"]["pass_fail"] == "fail")
    admet_results = [{"drug_name": dr.get("drug_name"), **dr["admet"]} for dr in all_docking_results]

    yield _sse_event("step", {
        "step": 5,
        "status": "complete",
        "message": f"{n_pass} safe, {n_warn} caution, {n_fail} risk detected",
        "data": {"admet_results": admet_results},
    })

    # ── Step 6: Report ────────────────────────────────────────────────────────
    yield _sse_event("step", {
        "step": 6,
        "status": "running",
        "message": "Generating research report with safety analysis...",
    })

    report_text = (
        f"# {symbol} Target Analysis\n\n"
        f"Structures found: {len(structures)}\n\n"
        f"Drugs found: {len(all_drugs)}\n\n"
        f"Successful dockings: {len(all_docking_results)}"
    )

    if all_docking_results and settings.anthropic_api_key:
        try:
            drug_meta = {d["name"]: d for d in all_drugs if d.get("name")}
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
                })

            report_result = generate_report(
                api_key=settings.anthropic_api_key,
                disease=f"{symbol} Target Analysis",
                target={"symbol": symbol, "name": symbol},
                results=report_input,
            )
            report_text = report_result["report_text"]

            explanation_map = {c["drug_name"]: c for c in report_result.get("candidates", [])}
            for dr in all_docking_results:
                expl = explanation_map.get(dr.get("drug_name"), {})
                dr["explanation"] = expl.get("explanation", "")
                dr["risk_benefit"] = expl.get("risk_benefit", "")
                dr["priority_rank"] = expl.get("priority_rank")
        except Exception as e:
            print(f"Warning: Report generation failed: {e}")

    # Build final candidates list
    candidates = []
    drug_meta_final = {d.get("name"): d for d in all_drugs if d.get("name")}
    for rank, dr in enumerate(all_docking_results, 1):
        meta = drug_meta_final.get(dr.get("drug_name"), {})
        candidates.append({
            "rank": rank,
            "drug_name": dr.get("drug_name"),
            "smiles": dr["smiles"],
            "confidence_score": dr["confidence_score"],
            "combined_score": dr["combined_score"],
            "mechanism": meta.get("mechanism"),
            "explanation": dr.get("explanation", ""),
            "admet": dr["admet"],
        })

    yield _sse_event("done", {
        "step": 6,
        "status": "complete",
        "data": {
            "report": report_text,
            "candidates": candidates,
            "docking_results": all_docking_results,
            "admet_results": admet_results,
        },
    })


@router.post("/stream")
async def stream_protein_pipeline(request: ProteinPipelineRequest):
    return StreamingResponse(
        _protein_pipeline_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
