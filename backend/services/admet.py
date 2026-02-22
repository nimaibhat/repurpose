"""ADMET prediction service using RDKit molecular descriptors.

Computes Absorption, Distribution, Metabolism, Excretion, Toxicity,
and Drug-likeness scores from SMILES strings. Optionally enhanced
by a DeepChem Tox21 model for toxicity prediction.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

# DeepChem 2.5 requires Keras 2 (tf-keras) with TF 2.20+
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

from rdkit import Chem
from rdkit.Chem import Descriptors, QED, rdMolDescriptors

# ─── Optional Tox21 Model ────────────────────────────────────────────────────

_tox21_model = None
_tox21_transformers = None


def load_tox21_model(model_dir: str | Path | None = None) -> bool:
    """Load a pre-trained Tox21 GraphConvModel and transformers. Returns True on success."""
    global _tox21_model, _tox21_transformers
    if model_dir is None:
        model_dir = Path(__file__).parent.parent / "models" / "tox21"
    else:
        model_dir = Path(model_dir)

    if not model_dir.exists():
        return False

    try:
        import deepchem as dc
        _tox21_model = dc.models.GraphConvModel(n_tasks=12, mode="classification", model_dir=str(model_dir))
        _tox21_model.restore()

        transformers_path = model_dir.parent / "tox21_transformers.pkl"
        if transformers_path.exists():
            with open(transformers_path, "rb") as f:
                _tox21_transformers = pickle.load(f)
        return True
    except Exception as e:
        print(f"Warning: Could not load Tox21 model: {e}")
        _tox21_model = None
        _tox21_transformers = None
        return False


def predict_tox21(smiles: str) -> float | None:
    """Predict toxicity probability using Tox21 model. Returns 0-1 score or None."""
    if _tox21_model is None:
        return None
    try:
        import deepchem as dc
        import numpy as np
        featurizer = dc.feat.ConvMolFeaturizer()
        features = featurizer.featurize([smiles])
        # Provide dummy y/w with correct shape for 12-task classification
        dummy_y = np.zeros((1, 12))
        dummy_w = np.zeros((1, 12))
        dataset = dc.data.NumpyDataset(X=features, y=dummy_y, w=dummy_w)
        preds = _tox21_model.predict(dataset)
        # Average toxicity probability across all 12 Tox21 tasks
        tox_probs = preds[0, :, 1]  # shape: (n_tasks,) — class 1 = toxic
        return float(np.nanmean(tox_probs))
    except Exception:
        return None


# ─── Reactive Substructure SMARTS ─────────────────────────────────────────────

_REACTIVE_SMARTS = [
    "[#6](=O)[Cl,Br,I]",       # acyl halides
    "[N;X2]=[N;X2]=[N;X1]",    # azides
    "[#6]1[#6][#8]1",          # epoxides
    "[SX2H]",                   # free thiols
    "[NX2]=O",                  # nitroso groups
    "C(=O)OO",                 # peroxides
]

_REACTIVE_PATTERNS = None


def _get_reactive_patterns() -> list:
    global _REACTIVE_PATTERNS
    if _REACTIVE_PATTERNS is None:
        _REACTIVE_PATTERNS = []
        for sma in _REACTIVE_SMARTS:
            pat = Chem.MolFromSmarts(sma)
            if pat is not None:
                _REACTIVE_PATTERNS.append(pat)
    return _REACTIVE_PATTERNS


# ─── Scoring Helpers ──────────────────────────────────────────────────────────

def _label(score: float) -> str:
    if score >= 0.7:
        return "High"
    if score >= 0.4:
        return "Medium"
    return "Low"


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# ─── ADMET Property Scorers ──────────────────────────────────────────────────

def _score_absorption(mw: float, logp: float, hbd: int, hba: int, tpsa: float) -> dict:
    """Lipinski Rule of Five + TPSA check."""
    violations = sum([
        mw >= 500,
        logp >= 5,
        hbd > 5,
        hba > 10,
    ])
    tpsa_ok = tpsa < 140

    score = _clamp(1.0 - violations * 0.2 - (0.2 if not tpsa_ok else 0.0))
    details_parts = []
    if violations > 0:
        details_parts.append(f"{violations} Lipinski violation{'s' if violations > 1 else ''}")
    if not tpsa_ok:
        details_parts.append(f"TPSA={tpsa:.0f} (>140)")
    details = "; ".join(details_parts) if details_parts else "Passes Lipinski Ro5 and TPSA<140"

    return {"score": round(score, 3), "label": _label(score), "details": details}


def _score_distribution(logp: float, tpsa: float, mw: float) -> dict:
    """LogP range (1-3 optimal), moderate TPSA, reasonable MW."""
    # LogP component: optimal 1-3
    if 1.0 <= logp <= 3.0:
        logp_score = 1.0
    elif logp < 1.0:
        logp_score = _clamp(logp)  # 0→0, 1→1
    else:
        logp_score = _clamp(1.0 - (logp - 3.0) / 4.0)  # 3→1, 7→0

    # TPSA component: 40-90 optimal
    if 40 <= tpsa <= 90:
        tpsa_score = 1.0
    elif tpsa < 40:
        tpsa_score = _clamp(tpsa / 40.0)
    else:
        tpsa_score = _clamp(1.0 - (tpsa - 90) / 100.0)

    # MW component: <500 preferred
    mw_score = _clamp(1.0 - max(0, mw - 300) / 400.0)

    score = _clamp(logp_score * 0.5 + tpsa_score * 0.3 + mw_score * 0.2)
    details = f"LogP={logp:.2f} (opt 1-3), TPSA={tpsa:.0f} (opt 40-90), MW={mw:.0f}"

    return {"score": round(score, 3), "label": _label(score), "details": details}


def _score_metabolism(rot_bonds: int, mol: Chem.Mol) -> dict:
    """Rotatable bonds <10, no reactive substructures."""
    rot_score = _clamp(1.0 - max(0, rot_bonds - 5) / 10.0)

    reactive_count = 0
    for pat in _get_reactive_patterns():
        if mol.HasSubstructMatch(pat):
            reactive_count += 1
    react_score = _clamp(1.0 - reactive_count * 0.3)

    score = _clamp(rot_score * 0.6 + react_score * 0.4)
    details_parts = [f"RotBonds={rot_bonds}"]
    if reactive_count > 0:
        details_parts.append(f"{reactive_count} reactive group{'s' if reactive_count > 1 else ''}")
    else:
        details_parts.append("no reactive groups")

    return {"score": round(score, 3), "label": _label(score), "details": "; ".join(details_parts)}


def _score_excretion(mw: float, logp: float, tpsa: float) -> dict:
    """MW<500, LogP<5, moderate TPSA for renal clearance."""
    mw_score = _clamp(1.0 - max(0, mw - 300) / 400.0)
    logp_score = _clamp(1.0 - max(0, logp - 2) / 5.0)
    tpsa_score = 1.0 if 20 <= tpsa <= 120 else _clamp(0.5)

    score = _clamp(mw_score * 0.4 + logp_score * 0.4 + tpsa_score * 0.2)
    details = f"MW={mw:.0f}, LogP={logp:.2f}, TPSA={tpsa:.0f}"

    return {"score": round(score, 3), "label": _label(score), "details": details}


def _score_toxicity(qed: float, smiles: str) -> dict:
    """QED-based toxicity score, optionally enhanced by Tox21."""
    tox21_prob = predict_tox21(smiles)

    if tox21_prob is not None:
        # Blend: Tox21 gives probability of toxicity; invert for safety score
        safety_score = _clamp(1.0 - tox21_prob)
        score = _clamp(safety_score * 0.7 + qed * 0.3)
        details = f"Tox21 safety={safety_score:.2f}, QED={qed:.2f} (model-enhanced)"
    else:
        # RDKit-only: use QED as proxy for drug-likeness / low toxicity
        score = _clamp(qed * 0.8 + 0.2)
        details = f"QED={qed:.2f} (heuristic, no Tox21 model)"

    return {"score": round(score, 3), "label": _label(score), "details": details}


def _score_drug_likeness(qed: float, mw: float, logp: float, hbd: int, hba: int) -> dict:
    """Composite QED + Lipinski violations."""
    violations = sum([mw >= 500, logp >= 5, hbd > 5, hba > 10])
    lipinski_score = _clamp(1.0 - violations * 0.25)

    score = _clamp(qed * 0.6 + lipinski_score * 0.4)
    details = f"QED={qed:.2f}, Lipinski violations={violations}"

    return {"score": round(score, 3), "label": _label(score), "details": details}


# ─── Main API ─────────────────────────────────────────────────────────────────

def predict_admet(smiles: str) -> dict:
    """Compute all 6 ADMET properties from a SMILES string.

    Returns dict with keys: smiles, absorption, distribution, metabolism,
    excretion, toxicity, drug_likeness, overall_score.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        # Return zeroed-out result for invalid SMILES
        zero = {"score": 0.0, "label": "Low", "details": "Invalid SMILES"}
        return {
            "smiles": smiles,
            "drug_name": None,
            "absorption": zero,
            "distribution": zero,
            "metabolism": zero,
            "excretion": zero,
            "toxicity": zero,
            "drug_likeness": zero,
            "overall_score": 0.0,
        }

    # Compute descriptors
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    tpsa = Descriptors.TPSA(mol)
    rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
    qed = QED.qed(mol)

    absorption = _score_absorption(mw, logp, hbd, hba, tpsa)
    distribution = _score_distribution(logp, tpsa, mw)
    metabolism = _score_metabolism(rot_bonds, mol)
    excretion = _score_excretion(mw, logp, tpsa)
    toxicity = _score_toxicity(qed, smiles)
    drug_likeness = _score_drug_likeness(qed, mw, logp, hbd, hba)

    # Overall: weighted average
    overall = (
        absorption["score"] * 0.2
        + distribution["score"] * 0.15
        + metabolism["score"] * 0.15
        + excretion["score"] * 0.15
        + toxicity["score"] * 0.2
        + drug_likeness["score"] * 0.15
    )

    return {
        "smiles": smiles,
        "drug_name": None,
        "absorption": absorption,
        "distribution": distribution,
        "metabolism": metabolism,
        "excretion": excretion,
        "toxicity": toxicity,
        "drug_likeness": drug_likeness,
        "overall_score": round(overall, 3),
    }


def build_admet_flags(raw: dict) -> list[str]:
    """Derive human-readable flags from a detailed predict_admet result."""
    flags: list[str] = []
    if raw["absorption"]["details"] == "Invalid SMILES":
        flags.append("Invalid SMILES")
        return flags
    if raw["absorption"]["label"] == "Low":
        flags.append("Poor absorption")
    if raw["distribution"]["label"] == "Low":
        flags.append("Poor distribution")
    if raw["metabolism"]["label"] == "Low":
        flags.append("Metabolic liability")
    if raw["excretion"]["label"] == "Low":
        flags.append("Poor clearance")
    if raw["toxicity"]["label"] == "Low":
        flags.append("Toxicity concern")
    if raw["drug_likeness"]["label"] == "Low":
        flags.append("Poor drug-likeness")
    return flags


def admet_pass_fail(overall: float, flags: list[str]) -> str:
    if "Invalid SMILES" in flags:
        return "fail"
    if overall >= 0.7:
        return "pass"
    if overall >= 0.4:
        return "warn"
    return "fail"


def build_admet_summary(raw: dict) -> dict:
    """Convert detailed predict_admet result to flat summary with flags and pass/fail."""
    flags = build_admet_flags(raw)
    overall = raw["overall_score"]
    return {
        "absorption": raw["absorption"]["score"],
        "distribution": raw["distribution"]["score"],
        "metabolism": raw["metabolism"]["score"],
        "excretion": raw["excretion"]["score"],
        "toxicity": raw["toxicity"]["score"],
        "drug_likeness": raw["drug_likeness"]["score"],
        "overall_score": overall,
        "flags": flags,
        "pass_fail": admet_pass_fail(overall, flags),
    }


def predict_admet_batch(
    smiles_list: list[str],
    drug_names: list[str | None] | None = None,
) -> list[dict]:
    """Batch ADMET prediction for a list of SMILES strings."""
    results = []
    for i, smi in enumerate(smiles_list):
        result = predict_admet(smi)
        if drug_names and i < len(drug_names):
            result["drug_name"] = drug_names[i]
        results.append(result)
    return results
