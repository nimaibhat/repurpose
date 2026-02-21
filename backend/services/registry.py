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
# columns: id, target_id (UNIQUE), display_name, disease_id, disease_name, created_at
# ---------------------------------------------------------------------------

def save_targets(
    settings: Settings,
    targets: list[dict],
    disease_id: str,
    disease_name: str,
) -> None:
    """Upsert every target from a /api/targets response into protein_registry.

    Each dict in *targets* must have: ensembl_id, symbol, name, score.
    Conflict key is target_id (Ensembl ID) — duplicate queries just refresh
    the disease context columns.
    """
    print(f"[registry] save_targets called with {len(targets)} target(s). supabase_url set: {bool(settings.supabase_url)}, key set: {bool(settings.supabase_service_key)}")

    if not _is_configured(settings):
        print("[registry] Supabase not configured — skipping protein registry save")
        return

    if not targets:
        print("[registry] No targets passed — nothing to save")
        return

    rows = [
        {
            "target_id":    t["ensembl_id"],   # UNIQUE conflict key
            "display_name": t.get("symbol"),
            "disease_id":   disease_id,
            "disease_name": disease_name,
        }
        for t in targets
        if t.get("ensembl_id")
    ]

    if not rows:
        return

    print(f"[registry] Attempting to upsert {len(rows)} protein(s) to Supabase...")
    for row in rows:
        print(f"  -> {row['target_id']} | {row['display_name']} | {row['disease_name']}")

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{settings.supabase_url}/rest/v1/protein_registry",
                headers=_headers(settings.supabase_service_key),
                params={"on_conflict": "target_id"},
                json=rows,
            )
            resp.raise_for_status()
        print(f"[registry] Successfully upserted {len(rows)} protein(s). HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[registry] ERROR saving proteins: {exc}")


def save_protein(settings: Settings, target_id: str, display_name: str | None) -> None:
    """Upsert a single protein (used by the pipeline route)."""
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
# drug_registry  (columns: id, chembl_id, common_name, smiles, phase, created_at)
# ---------------------------------------------------------------------------

def save_drugs(settings: Settings, drugs: list[dict]) -> None:
    """Upsert a batch of drugs into drug_registry (keyed on chembl_id).

    Each dict in *drugs* is expected to have the keys that ChEMBL returns:
      chembl_id, name, smiles, max_phase   (all others are ignored).
    """
    print(f"[registry] save_drugs called with {len(drugs)} drug(s). supabase_url set: {bool(settings.supabase_url)}, key set: {bool(settings.supabase_service_key)}")

    if not _is_configured(settings):
        print("[registry] Supabase not configured — skipping drug registry save")
        return

    if not drugs:
        print("[registry] No drugs passed — nothing to save")
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

    print(f"[registry] Attempting to upsert {len(rows)} drug(s) to Supabase...")
    for row in rows:
        print(f"  -> {row['chembl_id']} | {row['common_name']} | phase {row['phase']}")

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{settings.supabase_url}/rest/v1/drug_registry",
                headers=_headers(settings.supabase_service_key),
                params={"on_conflict": "chembl_id"},
                json=rows,
            )
            resp.raise_for_status()
        print(f"[registry] Successfully upserted {len(rows)} drug(s). HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[registry] ERROR saving drugs: {exc}")
