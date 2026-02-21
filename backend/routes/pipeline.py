import logging

from fastapi import APIRouter, HTTPException, Depends

from config import Settings, get_settings
from models.schemas import PipelineRequest, PipelineResult
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb, RCSBError
from services.chembl import search_drugs, ChEMBLError
from services.nvidia_nim import run_diffdock_batch
from services.claude import generate_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/", response_model=PipelineResult)
async def run_pipeline(request: PipelineRequest, settings: Settings = Depends(get_settings)):

    # Step 1: Disease → top protein targets
    try:
        disease_info = await search_disease(request.disease)
        targets = await get_associated_targets(disease_info["id"])
    except OpenTargetsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Targets error: {e}")

    if not targets:
        raise HTTPException(status_code=404, detail=f"No targets found for '{request.disease}'")

    top_target = targets[0]
    symbol = top_target["symbol"]

    # Step 2: Gene symbol → PDB structure (RCSB, AlphaFold fallback)
    pdb_text = None
    structure = None

    pdb_id = await search_pdb(symbol)
    if pdb_id:
        try:
            pdb_text = await download_pdb(pdb_id)
            resolution = await get_resolution(pdb_id)
            structure = {
                "symbol": symbol,
                "pdb_id": pdb_id,
                "resolution": resolution,
                "source": "rcsb",
            }
        except Exception as e:
            logger.warning("RCSB download failed for %s: %s", pdb_id, e)

    if pdb_text is None:
        try:
            uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
            structure = {
                "symbol": symbol,
                "pdb_id": f"AF-{uniprot_id}-F1",
                "resolution": None,
                "source": "alphafold",
            }
        except RCSBError as e:
            raise HTTPException(status_code=404, detail=f"No structure found for {symbol}: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Structure fetch error: {e}")

    # Step 3: Gene symbol → FDA-approved drug candidates (ChEMBL)
    try:
        _, drugs = await search_drugs(symbol)
    except ChEMBLError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ChEMBL error: {e}")

    if not drugs:
        raise HTTPException(status_code=404, detail=f"No drug candidates found for {symbol}")

    # Step 4: Run DiffDock batch docking
    docking_results = []
    if settings.nvidia_nim_api_key:
        drug_inputs = [{"name": d.get("name"), "smiles": d["smiles"]} for d in drugs]
        docking_results = await run_diffdock_batch(
            api_key=settings.nvidia_nim_api_key,
            pdb_text=pdb_text,
            drugs=drug_inputs,
        )

        # Enrich docking results with mechanism/phase from ChEMBL
        mech_map = {d.get("name"): d.get("mechanism") for d in drugs}
        phase_map = {d.get("name"): d.get("max_phase") for d in drugs}
        for r in docking_results:
            r["mechanism"] = mech_map.get(r.get("drug_name"))
            r["max_phase"] = phase_map.get(r.get("drug_name"))
    else:
        logger.warning("NVIDIA_NIM_API_KEY not set — skipping docking")

    # Step 5: Generate Claude report
    report = ""
    if docking_results and settings.anthropic_api_key:
        try:
            report_result = generate_report(
                api_key=settings.anthropic_api_key,
                disease=disease_info["name"],
                target=top_target,
                results=docking_results[:10],
            )
            report = report_result["report_text"]
        except Exception as e:
            logger.warning("Report generation failed: %s", e)
            report = f"Report generation failed: {e}"
    elif not docking_results:
        report = "No docking results available."
    else:
        report = "ANTHROPIC_API_KEY not configured."

    return PipelineResult(
        disease=disease_info["name"],
        targets=targets,
        structures=[structure] if structure else [],
        drugs=drugs,
        docking_results=docking_results,
        report=report,
    )
