import httpx

BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
TIMEOUT = 15.0
MIN_PHASE4_COUNT = 5


class ChEMBLError(Exception):
    pass


async def _get_json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params={**(params or {}), "format": "json"})
    resp.raise_for_status()
    return resp.json()


async def search_target(symbol: str) -> list[str]:
    """Resolve a gene symbol to candidate ChEMBL target IDs.
    Returns IDs ranked: SINGLE PROTEIN with exact symbol match first."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        data = await _get_json(client, f"{BASE_URL}/target/search.json", {"q": symbol})

    targets = data.get("targets", [])
    if not targets:
        raise ChEMBLError(f"No ChEMBL target found for '{symbol}'")

    def _score(t: dict) -> tuple[int, int]:
        is_single = 1 if t.get("target_type") == "SINGLE PROTEIN" else 0
        has_match = 0
        for comp in t.get("target_components", []):
            for s in comp.get("target_component_synonyms", []):
                if s.get("component_synonym", "").upper() == symbol.upper():
                    has_match = 1
                    break
        return (has_match, is_single)

    targets.sort(key=_score, reverse=True)
    return [t["target_chembl_id"] for t in targets[:10]]


async def get_mechanisms(target_chembl_id: str) -> list[dict]:
    """Get drug mechanisms for a target. Returns list of {molecule_chembl_id, mechanism_of_action}."""
    mechanisms = []
    url = f"{BASE_URL}/mechanism.json"
    params = {"target_chembl_id": target_chembl_id, "limit": 100}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        data = await _get_json(client, url, params)

    for mech in data.get("mechanisms", []):
        mol_id = mech.get("molecule_chembl_id")
        if mol_id:
            mechanisms.append({
                "molecule_chembl_id": mol_id,
                "mechanism_of_action": mech.get("mechanism_of_action"),
            })

    return mechanisms


async def get_molecule(client: httpx.AsyncClient, molecule_chembl_id: str) -> dict | None:
    """Fetch molecule details. Returns None if no SMILES available."""
    data = await _get_json(client, f"{BASE_URL}/molecule/{molecule_chembl_id}.json")

    structures = data.get("molecule_structures") or {}
    smiles = structures.get("canonical_smiles")
    if not smiles:
        return None

    try:
        max_phase = int(float(data.get("max_phase", 0) or 0))
    except (TypeError, ValueError):
        max_phase = 0

    return {
        "chembl_id": molecule_chembl_id,
        "name": data.get("pref_name"),
        "smiles": smiles,
        "max_phase": max_phase,
    }


async def search_drugs(symbol: str, limit: int = 20) -> tuple[str, list[dict]]:
    """Find approved/clinical drugs for a gene symbol.

    Returns (target_chembl_id, drugs_list).
    Prioritises Phase 4 drugs; backfills with Phase 3 if fewer than 5 Phase 4 found.
    Skips molecules without SMILES.
    """
    candidate_ids = await search_target(symbol)

    # Try candidates until we find one with mechanisms
    target_chembl_id = candidate_ids[0]
    mechanisms: list[dict] = []
    for cid in candidate_ids:
        mechanisms = await get_mechanisms(cid)
        if mechanisms:
            target_chembl_id = cid
            break

    if not mechanisms:
        return target_chembl_id, []

    # Build mechanism lookup
    moa_map: dict[str, str | None] = {
        m["molecule_chembl_id"]: m["mechanism_of_action"] for m in mechanisms
    }

    # Deduplicate molecule IDs
    mol_ids = list(dict.fromkeys(m["molecule_chembl_id"] for m in mechanisms))

    # Fetch molecules concurrently
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        molecules = []
        for mol_id in mol_ids:
            mol = await get_molecule(client, mol_id)
            if mol:
                mol["mechanism"] = moa_map.get(mol["chembl_id"])
                molecules.append(mol)

    # Split by phase
    phase4 = [m for m in molecules if (m.get("max_phase") or 0) >= 4]
    phase3 = [m for m in molecules if (m.get("max_phase") or 0) == 3]

    # Prefer Phase 4; backfill with Phase 3 if too few
    results = phase4[:]
    if len(results) < MIN_PHASE4_COUNT:
        results.extend(phase3)

    # Sort: Phase 4 first, then by name
    results.sort(key=lambda d: (-(d.get("max_phase") or 0), d.get("name") or ""))

    return target_chembl_id, results[:limit]
