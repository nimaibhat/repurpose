import httpx


async def fetch_structures(target_id: str) -> list[dict]:
    """Fetch PDB structures for a given target from RCSB."""
    raise NotImplementedError("TODO: implement RCSB PDB client")
