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
    max_phase: int
    mechanism: str | None = None


class DrugsResponse(BaseModel):
    symbol: str
    target_chembl_id: str
    drugs: list[DrugCandidate]


# --- Docking ---
class DockingDrug(BaseModel):
    name: str | None = None
    smiles: str


class DockingRequest(BaseModel):
    pdb_text: str
    drugs: list[DockingDrug]


class DockingResult(BaseModel):
    drug_name: str | None = None
    smiles: str
    confidence_score: float
    ligand_sdf: str
    num_poses: int


class DockingResponse(BaseModel):
    results: list[DockingResult]


# --- Report ---
class ReportRequest(BaseModel):
    disease: str
    pipeline_result: PipelineResult


class ReportResponse(BaseModel):
    markdown: str
