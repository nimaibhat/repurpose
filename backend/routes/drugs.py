from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from config import Settings, get_settings
from models.schemas import DrugCandidate, DrugsResponse
from services.chembl import ChEMBLError, search_drugs
from services.registry import save_drugs

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/", response_model=DrugsResponse)
async def get_drugs(
    background_tasks: BackgroundTasks,
    symbol: str = Query(..., description="Gene symbol, e.g. 'KRAS'"),
    limit: int = Query(20, ge=1, le=100, description="Max drugs to return"),
    settings: Settings = Depends(get_settings),
):
    try:
        target_chembl_id, drugs = await search_drugs(symbol, limit=limit)
    except ChEMBLError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ChEMBL API error: {e}")

    background_tasks.add_task(save_drugs, settings, drugs)

    return DrugsResponse(
        symbol=symbol,
        target_chembl_id=target_chembl_id,
        drugs=[DrugCandidate(**d) for d in drugs],
    )
