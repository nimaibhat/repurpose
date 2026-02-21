from fastapi import APIRouter, HTTPException, Query

from models.schemas import StructureResponse
from services.rcsb import search_pdb, download_pdb, get_resolution, fetch_alphafold_pdb, RCSBError

router = APIRouter(prefix="/structures", tags=["structures"])


@router.get("/", response_model=StructureResponse)
async def get_structure(symbol: str = Query(..., description="Gene symbol, e.g. 'KRAS'")):
    # Try RCSB first
    pdb_id = await search_pdb(symbol)

    if pdb_id:
        try:
            pdb_text = await download_pdb(pdb_id)
            resolution = await get_resolution(pdb_id)
            return StructureResponse(
                symbol=symbol,
                pdb_id=pdb_id,
                resolution=resolution,
                source="rcsb",
                pdb_text=pdb_text,
            )
        except Exception:
            pass  # fall through to AlphaFold

    # AlphaFold fallback
    try:
        uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
        return StructureResponse(
            symbol=symbol,
            pdb_id=f"AF-{uniprot_id}-F1",
            resolution=None,
            source="alphafold",
            pdb_text=pdb_text,
        )
    except RCSBError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch structure: {e}")
