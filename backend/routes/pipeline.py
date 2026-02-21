import json
import logging
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from models.schemas import PipelineRequest
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb, RCSBError
from services.chembl import search_drugs, ChEMBLError
from services.nvidia_nim import run_diffdock_batch
from services.claude import generate_report
from config import Settings, get_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = logging.getLogger(__name__)

PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name"


def _sse(step: int, status: str, message: str, data: dict | None = None) -> str:
    payload = {"step": step, "status": status, "message": message}
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload)}\n\n"


async def _fetch_pubchem_smiles(drug_name: str) -> str | None:
    """Fallback: fetch SMILES from PubChem by drug name."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{PUBCHEM_URL}/{drug_name}/property/CanonicalSMILES/JSON"
            )
            resp.raise_for_status()
            props = resp.json().get("PropertyTable", {}).get("Properties", [])
            if props:
                return props[0].get("CanonicalSMILES")
    except Exception as e:
        logger.warning("PubChem lookup failed for %s: %s", drug_name, e)
    return None


async def _run_pipeline(request: PipelineRequest, settings: Settings) -> AsyncGenerator[str, None]:
    # Accumulate partial results
    partial: dict = {"status": "running", "disease": {}, "target": {}, "candidates": [], "report": None, "docking_data": []}

    # ── Step 1: Discover targets ──
    yield _sse(1, "running", "Discovering protein targets...")
    try:
        if request.mode == "target" and request.target_symbol:
            symbol = request.target_symbol
            target_name = request.target_symbol
            disease_id = "user-provided"
            disease_name = request.disease
            target_score = None
        else:
            disease_info = await search_disease(request.disease)
            disease_id = disease_info["id"]
            disease_name = disease_info["name"]
            raw_targets = await get_associated_targets(disease_id)
            if not raw_targets:
                yield _sse(1, "error", "No targets found for this disease")
                partial["status"] = "partial"
                yield _sse(0, "done", "Pipeline completed with errors", partial)
                return

            top = raw_targets[0]
            symbol = top["symbol"]
            target_name = top["name"]
            target_score = top["score"]

        partial["disease"] = {"name": disease_name, "id": disease_id}
        targets_data = {"symbol": symbol, "name": target_name}
        yield _sse(1, "complete", f"Top target: {symbol} ({target_name})", targets_data)
    except (OpenTargetsError, Exception) as e:
        yield _sse(1, "error", f"Target discovery failed: {e}")
        partial["status"] = "partial"
        yield _sse(0, "done", "Pipeline completed with errors", partial)
        return

    # ── Step 2: Fetch protein structure ──
    yield _sse(2, "running", f"Retrieving protein structure for {symbol}...")
    try:
        pdb_id = await search_pdb(symbol)
        if pdb_id:
            pdb_text = await download_pdb(pdb_id)
            resolution = await get_resolution(pdb_id)
            source = "rcsb"
        else:
            uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
            pdb_id = f"AF-{uniprot_id}-F1"
            resolution = None
            source = "alphafold"

        partial["target"] = {
            "symbol": symbol,
            "name": target_name,
            "pdb_id": pdb_id,
            "score": target_score if request.mode != "target" else None,
        }
        struct_msg = f"Found {pdb_id} ({source}"
        if resolution:
            struct_msg += f", {resolution}Å"
        struct_msg += ")"
        yield _sse(2, "complete", struct_msg, {"pdb_id": pdb_id, "source": source, "resolution": resolution})
    except (RCSBError, Exception) as e:
        yield _sse(2, "error", f"Structure retrieval failed: {e}")
        partial["status"] = "partial"
        yield _sse(0, "done", "Pipeline completed with errors", partial)
        return

    # ── Step 3: Find drug candidates ──
    yield _sse(3, "running", f"Searching for drug candidates targeting {symbol}...")
    try:
        _target_chembl_id, raw_drugs = await search_drugs(symbol, limit=request.max_candidates)

        # Build drug list with mechanism info
        drug_list = []
        mech_map: dict[str, str | None] = {}
        phase_map: dict[str, int] = {}

        for d in raw_drugs:
            drug_list.append({"name": d["name"], "smiles": d["smiles"]})
            mech_map[d.get("name") or d["smiles"]] = d.get("mechanism")
            phase_map[d.get("name") or d["smiles"]] = d.get("max_phase", 0)

        # Mode: drug — filter or fetch from PubChem
        if request.mode == "drug" and request.drug_name:
            match = [d for d in drug_list if d["name"] and d["name"].upper() == request.drug_name.upper()]
            if match:
                drug_list = match
            else:
                # PubChem fallback
                smiles = await _fetch_pubchem_smiles(request.drug_name)
                if smiles:
                    drug_list = [{"name": request.drug_name, "smiles": smiles}]
                    mech_map[request.drug_name] = None
                    phase_map[request.drug_name] = 0
                else:
                    yield _sse(3, "error", f"Drug '{request.drug_name}' not found in ChEMBL or PubChem")
                    partial["status"] = "partial"
                    yield _sse(0, "done", "Pipeline completed with errors", partial)
                    return

        if not drug_list:
            yield _sse(3, "error", f"No drug candidates found for {symbol}")
            partial["status"] = "partial"
            yield _sse(0, "done", "Pipeline completed with errors", partial)
            return

        names = [d["name"] or "unnamed" for d in drug_list[:5]]
        yield _sse(3, "complete", f"Found {len(drug_list)} candidates: {', '.join(names)}", {"count": len(drug_list)})
    except (ChEMBLError, Exception) as e:
        yield _sse(3, "error", f"Drug search failed: {e}")
        partial["status"] = "partial"
        yield _sse(0, "done", "Pipeline completed with errors", partial)
        return

    # ── Step 4: Molecular docking ──
    yield _sse(4, "running", f"Docking {len(drug_list)} drugs against {pdb_id}... (this may take a minute)")
    try:
        if not settings.nvidia_nim_api_key:
            raise ValueError("NVIDIA_NIM_API_KEY not configured")

        docking_results = await run_diffdock_batch(
            api_key=settings.nvidia_nim_api_key,
            pdb_text=pdb_text,
            drugs=drug_list,
        )

        if not docking_results:
            yield _sse(4, "error", "All docking attempts failed")
            partial["status"] = "partial"
            yield _sse(0, "done", "Pipeline completed with errors", partial)
            return

        # Store docking data for 3D viewer
        partial["docking_data"] = [
            {"drug_name": r["drug_name"], "ligand_sdf": r["ligand_sdf"]}
            for r in docking_results
        ]

        scores_msg = ", ".join(
            f"{r['drug_name']}: {r['confidence_score']}" for r in docking_results[:3]
        )
        yield _sse(4, "complete", f"Docked {len(docking_results)} drugs. Top: {scores_msg}", {"count": len(docking_results)})
    except Exception as e:
        yield _sse(4, "error", f"Docking failed: {e}")
        partial["status"] = "partial"
        yield _sse(0, "done", "Pipeline completed with errors", partial)
        return

    # ── Step 5: Generate AI report ──
    yield _sse(5, "running", "Generating AI analysis report...")
    try:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        report_input = [
            {
                "drug_name": r["drug_name"],
                "smiles": r["smiles"],
                "confidence_score": r["confidence_score"],
                "mechanism": mech_map.get(r.get("drug_name") or r["smiles"]),
                "max_phase": phase_map.get(r.get("drug_name") or r["smiles"]),
            }
            for r in docking_results
        ]

        report_result = generate_report(
            api_key=settings.anthropic_api_key,
            disease=request.disease,
            target={"symbol": symbol, "name": target_name},
            results=report_input,
        )

        # Build final candidates
        explanation_map = {
            c["drug_name"]: c for c in report_result.get("candidates", [])
        }

        candidates = []
        for rank, r in enumerate(docking_results, 1):
            expl = explanation_map.get(r["drug_name"], {})
            candidates.append({
                "rank": rank,
                "drug_name": r["drug_name"],
                "smiles": r["smiles"],
                "confidence_score": r["confidence_score"],
                "mechanism": mech_map.get(r.get("drug_name") or r["smiles"]),
                "explanation": expl.get("explanation", ""),
                "risk_benefit": expl.get("risk_benefit", ""),
            })

        partial["candidates"] = candidates
        partial["report"] = report_result["report_text"]
        partial["status"] = "complete"

        yield _sse(5, "complete", "Report generated", {"candidate_count": len(candidates)})
    except Exception as e:
        yield _sse(5, "error", f"Report generation failed: {e}")
        partial["status"] = "partial"

    # ── Final result ──
    yield _sse(0, "done", "Pipeline finished", partial)


@router.post("/run")
async def run_pipeline(request: PipelineRequest, settings: Settings = Depends(get_settings)):
    return StreamingResponse(
        _run_pipeline(request, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
