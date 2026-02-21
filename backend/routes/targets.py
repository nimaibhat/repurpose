from fastapi import APIRouter, HTTPException, Query

from models.schemas import TargetsResponse, TargetHit
from services.open_targets import search_disease, get_associated_targets, OpenTargetsError

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("/", response_model=TargetsResponse)
async def get_targets(disease: str = Query(..., description="Disease name, e.g. 'pancreatic cancer'")):
    try:
        disease_info = await search_disease(disease)
        raw_targets = await get_associated_targets(disease_info["id"])
    except OpenTargetsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Targets API error: {e}")

    return TargetsResponse(
        disease_id=disease_info["id"],
        disease_name=disease_info["name"],
        targets=[TargetHit(**t) for t in raw_targets],
    )
