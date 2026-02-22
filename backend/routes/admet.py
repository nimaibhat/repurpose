from fastapi import APIRouter

from models.schemas import (
    AdmetRequest,
    AdmetBatchRequest,
    AdmetResult,
    AdmetDrugsRequest,
    AdmetDrugsResponse,
    AdmetDrugResult,
    AdmetScores,
    AdmetSummary,
)
from services.admet import (
    predict_admet,
    predict_admet_batch,
    build_admet_flags,
    admet_pass_fail,
)

router = APIRouter(prefix="/admet", tags=["admet"])


@router.post("", response_model=AdmetDrugsResponse)
async def predict_drugs(request: AdmetDrugsRequest):
    """Predict ADMET properties for a list of drugs with per-drug error handling."""
    results: list[AdmetDrugResult] = []

    for drug in request.drugs:
        raw = predict_admet(drug.smiles)
        flags = build_admet_flags(raw)
        overall = raw["overall_score"]

        results.append(AdmetDrugResult(
            drug_name=drug.name,
            smiles=drug.smiles,
            scores=AdmetScores(
                absorption=raw["absorption"]["score"],
                distribution=raw["distribution"]["score"],
                metabolism=raw["metabolism"]["score"],
                excretion=raw["excretion"]["score"],
                toxicity=raw["toxicity"]["score"],
                drug_likeness=raw["drug_likeness"]["score"],
            ),
            overall_score=overall,
            flags=flags,
            pass_fail=admet_pass_fail(overall, flags),
        ))

    passed = sum(1 for r in results if r.pass_fail == "pass")
    warned = sum(1 for r in results if r.pass_fail == "warn")
    failed = sum(1 for r in results if r.pass_fail == "fail")

    return AdmetDrugsResponse(
        results=results,
        summary=AdmetSummary(
            total=len(results),
            passed=passed,
            warned=warned,
            failed=failed,
        ),
    )


@router.post("/predict", response_model=AdmetResult)
async def predict_single(request: AdmetRequest):
    """Predict ADMET properties for a single SMILES string."""
    return predict_admet(request.smiles)


@router.post("/batch", response_model=list[AdmetResult])
async def predict_batch(request: AdmetBatchRequest):
    """Predict ADMET properties for a batch of SMILES strings."""
    return predict_admet_batch(request.smiles_list)
