from fastapi import APIRouter

from models.schemas import DockingRequest, DockingResponse, DockingResult

router = APIRouter(prefix="/docking", tags=["docking"])


@router.post("/", response_model=DockingResponse)
async def run_docking(request: DockingRequest):
    return DockingResponse(
        results=[
            DockingResult(
                pdb_id=request.pdb_id,
                smiles=request.smiles,
                drug_name=request.drug_name,
                confidence_score=0.85,
                pose_url=None,
            )
        ]
    )
