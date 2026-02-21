from fastapi import APIRouter, HTTPException, Depends

from models.schemas import DockingRequest, DockingResponse, DockingResult
from services.nvidia_nim import run_diffdock_batch
from config import Settings, get_settings

router = APIRouter(prefix="/docking", tags=["docking"])


@router.post("/", response_model=DockingResponse)
async def run_docking(request: DockingRequest, settings: Settings = Depends(get_settings)):
    if not settings.nvidia_nim_api_key:
        raise HTTPException(status_code=500, detail="NVIDIA_NIM_API_KEY not configured")

    drugs = [{"name": d.name, "smiles": d.smiles} for d in request.drugs]

    results = await run_diffdock_batch(
        api_key=settings.nvidia_nim_api_key,
        pdb_text=request.pdb_text,
        drugs=drugs,
    )

    return DockingResponse(results=[DockingResult(**r) for r in results])
