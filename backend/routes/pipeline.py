from fastapi import APIRouter, HTTPException

from models.schemas import PipelineRequest, PipelineResult
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


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
    
    # TODO: Step 3: For each symbol, get structures from RCSB
    # TODO: Step 4: For each symbol, get compounds from ChEMBL
    # TODO: Step 5: Run docking simulations
    # TODO: Step 6: Generate report
    
    return PipelineResult(
        disease=disease_info["name"],
        targets=targets,
        structures=[],
        drugs=[],
        docking_results=[],
        report=f"# Pipeline for {disease_info['name']}\n\nTarget symbols: {', '.join(target_symbols)}",
    )
