from pydantic import BaseModel


# --- Pipeline ---
class PipelineRequest(BaseModel):
    disease: str


class PipelineResult(BaseModel):
    disease: str
    targets: list[dict]
    structures: list[dict]
    drugs: list[dict]
    docking_results: list[dict]
    report: str


# --- Targets ---
class TargetHit(BaseModel):
    ensembl_id: str
    symbol: str
    name: str
    score: float


class TargetsResponse(BaseModel):
    disease_id: str
    disease_name: str
    targets: list[TargetHit]


# --- Structures ---
class StructureResponse(BaseModel):
    symbol: str
    pdb_id: str
    resolution: float | None = None
    source: str  # "rcsb" or "alphafold"
    pdb_text: str


# --- Drugs ---
class DrugCandidate(BaseModel):
    chembl_id: str
    name: str | None = None
    smiles: str
    phase: int | None = None


class DrugsResponse(BaseModel):
    target_id: str
    drugs: list[DrugCandidate]


# --- Docking ---
class DockingRequest(BaseModel):
    pdb_id: str
    smiles: str
    drug_name: str | None = None


class DockingResult(BaseModel):
    pdb_id: str
    smiles: str
    drug_name: str | None = None
    confidence_score: float
    pose_url: str | None = None


class DockingResponse(BaseModel):
    results: list[DockingResult]


# --- Report ---
class ReportRequest(BaseModel):
    disease: str
    pipeline_result: PipelineResult


class ReportResponse(BaseModel):
    markdown: str
