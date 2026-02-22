import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path

import httpx
from rdkit import Chem
from rdkit.Chem import AllChem

DIFFDOCK_URL = "https://health.api.nvidia.com/v1/biology/mit/diffdock"
ASSETS_URL = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
TIMEOUT = 90.0
MAX_CONCURRENT = 2
RPM_LIMIT = 35  # stay under 40 RPM cap with headroom
MAX_RETRIES = 3

# Rate limiting: 40 calls per minute
RATE_LIMIT_CALLS = 40
RATE_LIMIT_PERIOD = 60.0  # seconds

logger = logging.getLogger(__name__)

# Error tracking
ERROR_LOG_FILE = Path(__file__).parent.parent / "diffdock_errors.json"
_error_log = []

# Dynamic protein blacklist - proteins that failed receptor embedding generation
_failed_proteins = set()


def _log_error(error_data: dict):
    """Log error to in-memory list and flush to file periodically."""
    print(f"🔴 ERROR LOG: stage={error_data.get('stage')}, drug={error_data.get('drug_name')}, error={str(error_data.get('error', ''))[:50]}")
    _error_log.append(error_data)
    # Flush to file every 10 errors
    if len(_error_log) % 10 == 0:
        _flush_errors()


def _flush_errors():
    """Write all logged errors to JSON file."""
    print(f"📝 FLUSHING ERRORS: {len(_error_log)} errors to write")
    if _error_log:
        try:
            existing = []
            if ERROR_LOG_FILE.exists():
                with open(ERROR_LOG_FILE, 'r') as f:
                    existing = json.load(f)
            existing.extend(_error_log)
            with open(ERROR_LOG_FILE, 'w') as f:
                json.dump(existing, f, indent=2)
            print(f"✅ Wrote {len(_error_log)} errors to {ERROR_LOG_FILE}")
            _error_log.clear()
        except Exception as e:
            logger.error(f"Failed to write error log: {e}")
    else:
        print(f"ℹ️  No errors to flush (this is normal if all dockings succeeded)")


class RateLimiter:
    """Sliding-window rate limiter for async HTTP calls."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            # Evict timestamps outside the window
            while self._timestamps and self._timestamps[0] <= now - self._window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max:
                sleep_until = self._timestamps[0] + self._window
                delay = sleep_until - now
                if delay > 0:
                    logger.info("Rate limit: sleeping %.1fs", delay)
                    await asyncio.sleep(delay)
                self._timestamps.popleft()
            self._timestamps.append(time.monotonic())


class DiffDockError(Exception):
    pass


def smiles_to_sdf(smiles: str) -> str | None:
    """Convert a SMILES string to an SDF mol block with 3D coordinates."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        return None
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)


async def _upload_asset(
    client: httpx.AsyncClient, api_key: str, content: str, limiter: RateLimiter,
) -> str:
    """Upload a file to NVCF assets and return the asset ID."""
    await limiter.acquire()
    resp = await client.post(
        ASSETS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"contentType": "text/plain", "description": "diffdock-file"},
    )
    resp.raise_for_status()
    data = resp.json()

    await limiter.acquire()
    resp = await client.put(
        data["uploadUrl"],
        content=content.encode(),
        headers={
            "x-amz-meta-nvcf-asset-description": "diffdock-file",
            "Content-Type": "text/plain",
        },
    )
    resp.raise_for_status()

    return data["assetId"]


async def _dock_single(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    rate_limiter: RateLimiter,
    api_key: str,
    protein_asset_id: str,
    smiles: str,
    drug_name: str | None,
) -> dict | None:
    """Dock a single ligand against a protein. Returns best pose or None on failure."""
    start_time = time.time()

    # Filter out peptides (too complex for RDKit)
    # Most small molecule drugs have SMILES < 400 chars, peptides typically 600+
    if len(smiles) > 600:
        _log_error({
            "drug_name": drug_name,
            "smiles": smiles[:100] + "...",
            "stage": "peptide_filtered",
            "error": f"SMILES too long ({len(smiles)} chars) - likely a peptide/large biologic",
            "timestamp": time.time(),
        })
        logger.info(f"Skipping large molecule {drug_name} (SMILES length: {len(smiles)})")
        return None

    # Convert SMILES to SDF
    sdf_text = smiles_to_sdf(smiles)
    if sdf_text is None:
        _log_error({
            "drug_name": drug_name,
            "smiles": smiles,
            "stage": "rdkit_conversion",
            "error": "Failed to convert SMILES to SDF",
            "timestamp": time.time(),
        })
        logger.warning("Invalid SMILES for %s: %s", drug_name or "unknown", smiles[:60])
        return None

    async with semaphore:
        ligand_asset_id = None
        try:
            # Rate limit before API call
            await rate_limiter.acquire()
            upload_start = time.time()
            
            ligand_asset_id = await _upload_asset(client, api_key, sdf_text, rate_limiter)
            upload_time = time.time() - upload_start

            # Rate limit before DiffDock call
            await rate_limiter.acquire()
            diffdock_start = time.time()
            
            resp = await client.post(
                DIFFDOCK_URL,
                json={
                    "ligand": ligand_asset_id,
                    "ligand_file_type": "sdf",
                    "protein": protein_asset_id,
                    "num_poses": 5,
                    "time_divisions": 20,
                    "steps": 18,
                    "save_trajectory": False,
                    "is_staged": True,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "NVCF-INPUT-ASSET-REFERENCES": f"{protein_asset_id},{ligand_asset_id}",
                },
            )
            diffdock_time = time.time() - diffdock_start

            if resp.status_code != 200:
                _log_error({
                    "drug_name": drug_name,
                    "smiles": smiles,
                    "stage": "diffdock_http_error",
                    "status_code": resp.status_code,
                    "response_text": resp.text[:1000],
                    "upload_time": upload_time,
                    "diffdock_time": diffdock_time,
                    "total_time": time.time() - start_time,
                    "timestamp": time.time(),
                })
                logger.warning("DiffDock %d for %s: %s", resp.status_code, drug_name or "unknown", resp.text[:500])
                return None

            data = resp.json()
        except Exception as e:
            error_info = {
                "drug_name": drug_name,
                "smiles": smiles,
                "stage": "diffdock_exception",
                "error": str(e),
                "error_type": type(e).__name__,
                "total_time": time.time() - start_time,
                "timestamp": time.time(),
            }
            if ligand_asset_id:
                error_info["ligand_uploaded"] = True
            _log_error(error_info)
            logger.warning("DiffDock failed for %s (%s): %s", drug_name or "unknown", smiles[:40], e)
            return None

    # Check inference status
    if data.get("status") == "failed":
        error_details = data.get("details", "")
        _log_error({
            "drug_name": drug_name,
            "smiles": smiles,
            "stage": "diffdock_inference_failed",
            "status": data.get("status"),
            "details": error_details,
            "full_response": data,
            "total_time": time.time() - start_time,
            "timestamp": time.time(),
        })
        logger.warning("DiffDock inference failed for %s: %s", drug_name or "unknown", error_details)
        
        # If this is a receptor embedding error, it's a protein structure issue
        # Return a special marker so the batch can be aborted
        if "receptor embeddings" in str(error_details).lower():
            return {"_protein_failed": True, "error": error_details}
        
        return None

    ligand_positions = data.get("ligand_positions")
    confidences = data.get("position_confidence")

    if not ligand_positions or not confidences:
        _log_error({
            "drug_name": drug_name,
            "smiles": smiles,
            "stage": "no_poses_returned",
            "has_positions": bool(ligand_positions),
            "has_confidences": bool(confidences),
            "response_keys": list(data.keys()),
            "total_time": time.time() - start_time,
            "timestamp": time.time(),
        })
        logger.warning("No poses returned for %s", drug_name or smiles[:40])
        return None

    # Filter out None confidences
    valid_pairs = [
        (i, c) for i, c in enumerate(confidences)
        if c is not None and i < len(ligand_positions) and ligand_positions[i]
    ]
    if not valid_pairs:
        _log_error({
            "drug_name": drug_name,
            "smiles": smiles,
            "stage": "all_poses_none_confidence",
            "num_poses": len(confidences),
            "total_time": time.time() - start_time,
            "timestamp": time.time(),
        })
        logger.warning("All poses had None confidence for %s", drug_name or smiles[:40])
        return None

    best_idx, best_conf = max(valid_pairs, key=lambda p: p[1])

    return {
        "drug_name": drug_name,
        "smiles": smiles,
        "confidence_score": round(best_conf, 4),
        "ligand_sdf": ligand_positions[best_idx],
        "num_poses": len(valid_pairs),
    }


async def run_diffdock_batch(
    api_key: str,
    pdb_text: str,
    drugs: list[dict],
    pdb_id: str = None,
) -> list[dict]:
    """Dock multiple drugs against a protein concurrently.

    Args:
        api_key: NVIDIA NIM API key.
        pdb_text: Raw PDB file text for the protein.
        drugs: List of {"name": ..., "smiles": ...} dicts.
        pdb_id: PDB ID of the protein (for blacklist tracking).

    Returns:
        List of results sorted by confidence descending. Failed drugs are skipped.
    """
    # Check if this protein already failed - skip entire batch
    if pdb_id and pdb_id in _failed_proteins:
        print(f"⚠️  Skipping {len(drugs)} drugs for {pdb_id} - protein previously failed receptor embedding")
        return []
    
    print(f"🚀 Starting DiffDock batch: {len(drugs)} drugs")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    rate_limiter = RateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        protein_asset_id = await _upload_asset(client, api_key, pdb_text, rate_limiter)

        tasks = [
            _dock_single(client, semaphore, rate_limiter, api_key, protein_asset_id, d["smiles"], d.get("name"))
            for d in drugs
        ]
        results = await asyncio.gather(*tasks)

    # Check for protein-level failures (receptor embedding errors)
    protein_failed = any(r and isinstance(r, dict) and r.get("_protein_failed") for r in results)
    if protein_failed and pdb_id:
        _failed_proteins.add(pdb_id)
        print(f"🚫 Protein {pdb_id} failed receptor embedding - added to blacklist")
        print(f"   Future drugs for this protein will be skipped automatically")

    valid = [r for r in results if r is not None and not (isinstance(r, dict) and r.get("_protein_failed"))]
    failed_count = len(results) - len(valid)
    print(f"✅ DiffDock batch complete: {len(valid)} successful, {failed_count} failed")
    valid.sort(key=lambda r: r["confidence_score"], reverse=True)
    
    # Flush any remaining errors to file
    _flush_errors()
    
    return valid
