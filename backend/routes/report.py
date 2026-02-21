from fastapi import APIRouter, HTTPException, Depends

from models.schemas import ReportRequest, ReportResponse, CandidateExplanation
from services.claude import generate_report
from config import Settings, get_settings

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/", response_model=ReportResponse)
async def create_report(request: ReportRequest, settings: Settings = Depends(get_settings)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    result = generate_report(
        api_key=settings.anthropic_api_key,
        disease=request.disease,
        target=request.target.model_dump(),
        results=[r.model_dump() for r in request.results],
    )

    return ReportResponse(
        report_text=result["report_text"],
        candidates=[CandidateExplanation(**c) for c in result["candidates"]],
    )
