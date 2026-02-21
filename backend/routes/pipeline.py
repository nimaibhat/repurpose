from fastapi import APIRouter

from models.schemas import PipelineRequest, PipelineResult

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/", response_model=PipelineResult)
async def run_pipeline(request: PipelineRequest):
    return PipelineResult(
        disease=request.disease,
        targets=[
            {"id": "ENSG00000157764", "symbol": "BRAF", "name": "B-Raf proto-oncogene", "score": 0.92},
        ],
        structures=[
            {"pdb_id": "6VJJ", "title": "BRAF kinase domain", "resolution": 2.1},
        ],
        drugs=[
            {"chembl_id": "CHEMBL2068237", "name": "Dabrafenib", "smiles": "CC1=C(F)...", "phase": 4},
        ],
        docking_results=[
            {"pdb_id": "6VJJ", "smiles": "CC1=C(F)...", "drug_name": "Dabrafenib", "confidence_score": 0.85},
        ],
        report="# Placeholder pipeline report",
    )
