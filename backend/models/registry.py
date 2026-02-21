from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# protein_registry
# ---------------------------------------------------------------------------

class ProteinRegistryCreate(BaseModel):
    """Payload used when inserting a new protein into the registry."""
    target_id: str       # UniProt or Ensembl ID (maps to the UNIQUE column)
    display_name: str | None = None


class ProteinRegistryRead(ProteinRegistryCreate):
    """Full row returned from Supabase, including server-generated fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# drug_registry
# ---------------------------------------------------------------------------

class DrugRegistryCreate(BaseModel):
    """Payload used when inserting a new drug into the registry."""
    chembl_id: str       # ChEMBL ID (maps to the UNIQUE column)
    common_name: str | None = None
    smiles: str | None = None
    phase: int | None = None


class DrugRegistryRead(DrugRegistryCreate):
    """Full row returned from Supabase, including server-generated fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
