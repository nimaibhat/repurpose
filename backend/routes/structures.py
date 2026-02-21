from fastapi import APIRouter

from models.schemas import StructuresResponse, StructureHit

router = APIRouter(prefix="/structures", tags=["structures"])


@router.get("/{target_id}", response_model=StructuresResponse)
async def get_structures(target_id: str):
    return StructuresResponse(
        target_id=target_id,
        structures=[
            StructureHit(pdb_id="6VJJ", title="BRAF kinase domain", resolution=2.1),
            StructureHit(pdb_id="4MNE", title="BRAF V600E mutant", resolution=2.5),
        ],
    )
