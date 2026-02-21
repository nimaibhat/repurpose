from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from config import Settings, get_settings
from models.schemas import TargetHit, TargetsResponse
from services.open_targets import OpenTargetsError, get_associated_targets, search_disease
from services.registry import save_targets

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("/", response_model=TargetsResponse)
async def get_targets(
    background_tasks: BackgroundTasks,
    disease: str = Query(..., description="Disease name, e.g. 'pancreatic cancer'"),
    settings: Settings = Depends(get_settings),
):
    try:
        disease_info = await search_disease(disease)
        raw_targets = await get_associated_targets(disease_info["id"])
    except OpenTargetsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Targets API error: {e}")

    background_tasks.add_task(
        save_targets,
        settings,
        raw_targets,
        disease_info["id"],
        disease_info["name"],
    )

    return TargetsResponse(
        disease_id=disease_info["id"],
        disease_name=disease_info["name"],
        targets=[TargetHit(**t) for t in raw_targets],
    )
