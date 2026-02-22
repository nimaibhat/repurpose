"""XGBoost Binding Affinity prediction service.

Predicts binding affinity (pKd) from SMILES-derived tabular features
(RDKit descriptors + ADMET sub-scores) using a pre-trained XGBRegressor.
Follows the same module-level lazy-loading pattern as services/admet.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# ─── Module-level model holder ───────────────────────────────────────────────

_xgb_model = None
_feature_names: list[str] | None = None

# ─── Feature Extraction ─────────────────────────────────────────────────────


def _compute_features(smiles: str) -> list[float] | None:
    """Compute 20 features from a SMILES string: 14 RDKit descriptors + 6 ADMET sub-scores."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, QED, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = Descriptors.TPSA(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
        qed = QED.qed(mol)
        heavy_atoms = mol.GetNumHeavyAtoms()
        rings = rdMolDescriptors.CalcNumRings(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        frac_csp3 = rdMolDescriptors.CalcFractionCSP3(mol)
        heteroatoms = rdMolDescriptors.CalcNumHeteroatoms(mol)
        mr = Descriptors.MolMR(mol)
        formal_charge = Chem.GetFormalCharge(mol)

        # ADMET sub-scores (reuse existing scoring functions)
        from services.admet import predict_admet

        admet = predict_admet(smiles)
        absorption = admet["absorption"]["score"]
        distribution = admet["distribution"]["score"]
        metabolism = admet["metabolism"]["score"]
        excretion = admet["excretion"]["score"]
        toxicity = admet["toxicity"]["score"]
        drug_likeness = admet["drug_likeness"]["score"]

        return [
            mw, logp, tpsa, hbd, hba, rot_bonds, qed, heavy_atoms,
            rings, aromatic_rings, frac_csp3, heteroatoms, mr, formal_charge,
            absorption, distribution, metabolism, excretion, toxicity, drug_likeness,
        ]
    except Exception as e:
        print(f"Warning: feature extraction failed for {smiles}: {e}")
        return None


FEATURE_NAMES = [
    "mw", "logp", "tpsa", "hbd", "hba", "rot_bonds", "qed", "heavy_atoms",
    "rings", "aromatic_rings", "frac_csp3", "heteroatoms", "mr", "formal_charge",
    "absorption", "distribution", "metabolism", "excretion", "toxicity", "drug_likeness",
]


# ─── Model Loading ───────────────────────────────────────────────────────────


def load_xgb_model(model_dir: str | Path | None = None) -> bool:
    """Load pre-trained XGBoost binding affinity model. Returns True on success."""
    global _xgb_model, _feature_names

    if model_dir is None:
        model_dir = Path(__file__).parent.parent / "models" / "xgb_affinity"
    else:
        model_dir = Path(model_dir)

    model_path = model_dir / "xgb_binding_affinity.json"
    if not model_path.exists():
        print(f"XGBoost affinity model not found at {model_path}")
        return False

    try:
        import xgboost as xgb

        model = xgb.XGBRegressor()
        model.load_model(str(model_path))
        _xgb_model = model

        # Load metadata if available
        meta_path = model_dir / "metadata.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            _feature_names = meta.get("feature_names", FEATURE_NAMES)
        else:
            _feature_names = FEATURE_NAMES

        print(f"XGBoost affinity model loaded from {model_path}")
        return True

    except Exception as e:
        print(f"Warning: Could not load XGBoost affinity model: {e}")
        _xgb_model = None
        _feature_names = None
        return False


# ─── Inference ───────────────────────────────────────────────────────────────


def predict_binding_affinity(smiles: str) -> dict | None:
    """Predict binding affinity from a SMILES string.

    Returns {"predicted_pkd": float, "predicted_kd_nm": float} or None.
    """
    if _xgb_model is None:
        return None

    try:
        import numpy as np

        features = _compute_features(smiles)
        if features is None:
            return None

        X = np.array([features], dtype=np.float32)
        pkd_raw = float(_xgb_model.predict(X)[0])

        # Clamp to realistic pKd range (0-12)
        pkd = max(0.0, min(12.0, pkd_raw))

        # Convert pKd to Kd in nanomolar: Kd = 10^(-pKd) * 1e9
        kd_nm = math.pow(10, -pkd) * 1e9

        return {
            "predicted_pkd": round(pkd, 2),
            "predicted_kd_nm": round(kd_nm, 1),
        }

    except Exception as e:
        print(f"Warning: XGBoost affinity prediction failed: {e}")
        return None
