from fastapi import APIRouter

from models.schemas import DrugsResponse, DrugCandidate

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/{target_id}", response_model=DrugsResponse)
async def get_drugs(target_id: str):
    return DrugsResponse(
        target_id=target_id,
        drugs=[
            DrugCandidate(chembl_id="CHEMBL2068237", name="Dabrafenib", smiles="CC1=C(F)C(NS(=O)(=O)C2=CC=CC=C2)=NC(NC3=CC=C(C4CC4)C(F)=C3)=N1", phase=4),
            DrugCandidate(chembl_id="CHEMBL1336", name="Vemurafenib", smiles="CCCS(=O)(=O)NC1=CC=C(F)C(C(=O)C2=CNC3=NC=C(C=C23)C3=CC=C(Cl)CC3)=C1F", phase=4),
        ],
    )
