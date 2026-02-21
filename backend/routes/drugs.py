from fastapi import APIRouter, HTTPException, Query

from models.schemas import DrugsResponse, DrugCandidate
from services.chembl import search_drugs, ChEMBLError

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/", response_model=DrugsResponse)
async def get_drugs(
    symbol: str = Query(..., description="Gene symbol, e.g. 'KRAS'"),
    limit: int = Query(20, ge=1, le=100, description="Max drugs to return"),
):
    try:
        target_chembl_id, drugs = await search_drugs(symbol, limit=limit)
    except ChEMBLError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ChEMBL API error: {e}")

    return DrugsResponse(
        symbol=symbol,
        target_chembl_id=target_chembl_id,
        drugs=[DrugCandidate(**d) for d in drugs],
    )
