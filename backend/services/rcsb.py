import httpx

RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
ALPHAFOLD_URL = "https://alphafold.ebi.ac.uk/files"
TIMEOUT = 15.0


class RCSBError(Exception):
    pass


def _build_rcsb_query(symbol: str) -> dict:
    return {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
                        "operator": "exact_match",
                        "value": symbol,
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "exptl.method",
                        "operator": "exact_match",
                        "value": "X-RAY DIFFRACTION",
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
                        "operator": "exact_match",
                        "value": "Homo sapiens",
                    },
                },
            ],
        },
        "return_type": "entry",
        "request_options": {
            "sort": [
                {
                    "sort_by": "rcsb_entry_info.resolution_combined",
                    "direction": "asc",
                }
            ],
            "paginate": {"start": 0, "rows": 1},
        },
    }


async def search_pdb(symbol: str) -> str | None:
    """Search RCSB for the best-resolution human X-ray structure for a gene symbol.
    Returns PDB ID or None."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(RCSB_SEARCH_URL, json=_build_rcsb_query(symbol))
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        data = resp.json()

    results = data.get("result_set", [])
    if not results:
        return None
    return results[0]["identifier"]


async def download_pdb(pdb_id: str) -> str:
    """Download the raw .pdb file text for a given PDB ID."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        resp.raise_for_status()
        return resp.text


async def get_resolution(pdb_id: str) -> float | None:
    """Fetch resolution for a PDB entry via the RCSB data API."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}")
        resp.raise_for_status()
        data = resp.json()
    resolutions = data.get("rcsb_entry_info", {}).get("resolution_combined", [])
    return resolutions[0] if resolutions else None


async def _symbol_to_uniprot(symbol: str) -> str | None:
    """Map a gene symbol to a UniProt accession (human, reviewed)."""
    params = {
        "query": f"gene_exact:{symbol} AND organism_id:9606",
        "format": "json",
        "size": "1",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(UNIPROT_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        return None
    return results[0]["primaryAccession"]


async def fetch_alphafold_pdb(symbol: str) -> tuple[str, str]:
    """Fallback: fetch an AlphaFold predicted structure.
    Returns (uniprot_id, pdb_text)."""
    uniprot_id = await _symbol_to_uniprot(symbol)
    if not uniprot_id:
        raise RCSBError(f"Could not map '{symbol}' to a UniProt ID for AlphaFold fallback")

    url = f"{ALPHAFOLD_URL}/AF-{uniprot_id}-F1-model_v4.pdb"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return uniprot_id, resp.text
