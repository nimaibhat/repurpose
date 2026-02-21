import asyncio
import logging

import httpx
from rdkit import Chem
from rdkit.Chem import AllChem

DIFFDOCK_URL = "https://health.api.nvidia.com/v1/biology/mit/diffdock"
ASSETS_URL = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
TIMEOUT = 90.0
MAX_CONCURRENT = 3

logger = logging.getLogger(__name__)


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


async def _upload_asset(client: httpx.AsyncClient, api_key: str, content: str) -> str:
    """Upload a file to NVCF assets and return the asset ID."""
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
    api_key: str,
    protein_asset_id: str,
    smiles: str,
    drug_name: str | None,
) -> dict | None:
    """Dock a single ligand against a protein. Returns best pose or None on failure."""
    # Convert SMILES to SDF
    sdf_text = smiles_to_sdf(smiles)
    if sdf_text is None:
        logger.warning("Invalid SMILES for %s: %s", drug_name or "unknown", smiles[:60])
        return None

    async with semaphore:
        try:
            ligand_asset_id = await _upload_asset(client, api_key, sdf_text)

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

            if resp.status_code != 200:
                logger.warning("DiffDock %d for %s: %s", resp.status_code, drug_name or "unknown", resp.text[:500])
                return None

            data = resp.json()
        except Exception as e:
            logger.warning("DiffDock failed for %s (%s): %s", drug_name or "unknown", smiles[:40], e)
            return None

    if data.get("status") == "failed":
        logger.warning("DiffDock inference failed for %s: %s", drug_name or "unknown", data.get("details"))
        return None

    ligand_positions = data.get("ligand_positions")
    confidences = data.get("position_confidence")

    if not ligand_positions or not confidences:
        logger.warning("No poses returned for %s", drug_name or smiles[:40])
        return None

    # Filter out None confidences
    valid_pairs = [
        (i, c) for i, c in enumerate(confidences)
        if c is not None and i < len(ligand_positions) and ligand_positions[i]
    ]
    if not valid_pairs:
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
) -> list[dict]:
    """Dock multiple drugs against a protein concurrently.

    Args:
        api_key: NVIDIA NIM API key.
        pdb_text: Raw PDB file text for the protein.
        drugs: List of {"name": ..., "smiles": ...} dicts.

    Returns:
        List of results sorted by confidence descending. Failed drugs are skipped.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        protein_asset_id = await _upload_asset(client, api_key, pdb_text)

        tasks = [
            _dock_single(client, semaphore, api_key, protein_asset_id, d["smiles"], d.get("name"))
            for d in drugs
        ]
        results = await asyncio.gather(*tasks)

    valid = [r for r in results if r is not None]
    valid.sort(key=lambda r: r["confidence_score"], reverse=True)
    return valid
