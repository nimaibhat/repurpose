"""
Background-safe helpers for writing to protein_registry and drug_registry.

Uses the Supabase PostgREST REST API directly via httpx — no supabase-py SDK
needed, which avoids its heavy C-extension dependencies (pyiceberg, pyroaring).

These are plain synchronous functions so they can be handed directly to
FastAPI's BackgroundTasks, which runs sync callables in a thread-pool
executor (no event-loop conflict).
"""

from __future__ import annotations

import logging

import httpx

from config import Settings

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


def _is_configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _headers(service_key: str) -> dict:
    """Standard Supabase PostgREST headers for an authenticated upsert."""
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        # merge-duplicates = ON CONFLICT DO UPDATE (upsert)
        # return=minimal    = don't send the row back in the response body
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


# ---------------------------------------------------------------------------
# protein_registry
# ---------------------------------------------------------------------------

def save_protein(settings: Settings, target_id: str, display_name: str | None) -> None:
    """Upsert a single protein into protein_registry (keyed on target_id)."""
    if not _is_configured(settings):
        logger.warning("Supabase not configured — skipping protein registry save")
        return

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{settings.supabase_url}/rest/v1/protein_registry",
                headers=_headers(settings.supabase_service_key),
                params={"on_conflict": "target_id"},
                json={"target_id": target_id, "display_name": display_name},
            )
            resp.raise_for_status()
        logger.info("Registry: upserted protein %s", target_id)
    except Exception as exc:
        logger.error("Registry: failed to save protein %s — %s", target_id, exc)


# ---------------------------------------------------------------------------
# drug_registry
# ---------------------------------------------------------------------------

def save_drugs(settings: Settings, drugs: list[dict]) -> None:
    """Upsert a batch of drugs into drug_registry (keyed on chembl_id).

    Each dict in *drugs* is expected to have the keys that ChEMBL returns:
      chembl_id, name, smiles, max_phase   (all others are ignored).
    """
    if not _is_configured(settings):
        logger.warning("Supabase not configured — skipping drug registry save")
        return

    if not drugs:
        return

    # Map ChEMBL field names → registry column names; skip rows with no chembl_id
    rows = [
        {
            "chembl_id": d["chembl_id"],
            "common_name": d.get("name"),
            "smiles": d.get("smiles"),
            "phase": d.get("max_phase"),
        }
        for d in drugs
        if d.get("chembl_id")
    ]

    if not rows:
        return

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{settings.supabase_url}/rest/v1/drug_registry",
                headers=_headers(settings.supabase_service_key),
                params={"on_conflict": "chembl_id"},
                json=rows,
            )
            resp.raise_for_status()
        logger.info("Registry: upserted %d drug(s)", len(rows))
    except Exception as exc:
        logger.error("Registry: failed to save drugs — %s", exc)
