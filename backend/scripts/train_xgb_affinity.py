#!/usr/bin/env python3
"""Train an XGBoost model to predict binding affinity (pKd) from SMILES features.

Usage:
    python3 backend/scripts/train_xgb_affinity.py --pdbbind-dir /path/to/refined-set

The PDBbind refined-set directory should contain:
    - index/INDEX_refined_data.2020  (tab-separated: PDB_code, resolution, release_year, -logKd, Kd, reference, ligand_name)
    - <pdb_code>/<pdb_code>_ligand.sdf  per complex

Outputs:
    - backend/models/xgb_affinity/xgb_binding_affinity.json
    - backend/models/xgb_affinity/metadata.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


def parse_pdbbind_index(pdbbind_dir: Path) -> list[dict]:
    """Parse PDBbind index file for pKd labels and PDB codes."""
    index_path = pdbbind_dir / "index" / "INDEX_refined_data.2020"
    if not index_path.exists():
        # Try alternate naming
        candidates = list((pdbbind_dir / "index").glob("INDEX_refined*"))
        if candidates:
            index_path = candidates[0]
        else:
            raise FileNotFoundError(f"No PDBbind index file found in {pdbbind_dir / 'index'}")

    entries = []
    with open(index_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            pdb_code = parts[0].lower()
            try:
                pkd = float(parts[3])  # -logKd/Ki column
            except ValueError:
                continue
            entries.append({"pdb_code": pdb_code, "pkd": pkd})

    return entries


def extract_smiles_from_sdf(sdf_path: Path) -> str | None:
    """Extract SMILES from an SDF file via RDKit."""
    from rdkit import Chem

    supplier = Chem.SDMolSupplier(str(sdf_path), removeHs=True, sanitize=True)
    for mol in supplier:
        if mol is not None:
            return Chem.MolToSmiles(mol)
    return None


def compute_features(smiles: str) -> list[float] | None:
    """Compute 20 features: 14 RDKit descriptors + 6 ADMET sub-scores."""
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

    # ADMET sub-scores — import from project
    sys.path.insert(0, str(Path(__file__).parent.parent))
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


FEATURE_NAMES = [
    "mw", "logp", "tpsa", "hbd", "hba", "rot_bonds", "qed", "heavy_atoms",
    "rings", "aromatic_rings", "frac_csp3", "heteroatoms", "mr", "formal_charge",
    "absorption", "distribution", "metabolism", "excretion", "toxicity", "drug_likeness",
]


def main():
    parser = argparse.ArgumentParser(description="Train XGBoost binding affinity model on PDBbind")
    parser.add_argument("--pdbbind-dir", type=str, required=True, help="Path to PDBbind refined-set directory")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for model files")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    pdbbind_dir = Path(args.pdbbind_dir)
    if not pdbbind_dir.exists():
        print(f"Error: PDBbind directory not found: {pdbbind_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).parent.parent / "models" / "xgb_affinity"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Parse index
    print("Parsing PDBbind index...")
    entries = parse_pdbbind_index(pdbbind_dir)
    print(f"Found {len(entries)} entries in index")

    # Step 2: Extract SMILES and compute features
    print("Extracting SMILES and computing features...")
    X_list = []
    y_list = []
    skipped = 0
    t0 = time.time()

    for i, entry in enumerate(entries):
        pdb_code = entry["pdb_code"]
        sdf_path = pdbbind_dir / pdb_code / f"{pdb_code}_ligand.sdf"

        if not sdf_path.exists():
            skipped += 1
            continue

        smiles = extract_smiles_from_sdf(sdf_path)
        if smiles is None:
            skipped += 1
            continue

        features = compute_features(smiles)
        if features is None:
            skipped += 1
            continue

        X_list.append(features)
        y_list.append(entry["pkd"])

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"  Processed {i + 1}/{len(entries)} ({elapsed:.1f}s, {skipped} skipped)")

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.float32)
    print(f"Dataset: {len(X)} compounds ({skipped} skipped), {len(FEATURE_NAMES)} features")

    # Step 3: Split 80/10/10
    from sklearn.model_selection import train_test_split

    rng = np.random.RandomState(args.seed)
    indices = rng.permutation(len(X))
    n_train = int(0.8 * len(X))
    n_val = int(0.1 * len(X))

    train_idx = indices[:n_train]
    val_idx = indices[n_train:n_train + n_val]
    test_idx = indices[n_train + n_val:]

    X_train, y_train = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    print(f"Split: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")

    # Step 4: Train XGBoost
    import xgboost as xgb
    from scipy.stats import pearsonr

    print("Training XGBRegressor...")
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=args.seed,
        early_stopping_rounds=20,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )

    # Step 5: Evaluate
    y_pred_test = model.predict(X_test)
    rmse = np.sqrt(np.mean((y_test - y_pred_test) ** 2))
    mae = np.mean(np.abs(y_test - y_pred_test))
    r, p_val = pearsonr(y_test, y_pred_test)

    print(f"\nTest results:")
    print(f"  RMSE:      {rmse:.3f}")
    print(f"  MAE:       {mae:.3f}")
    print(f"  Pearson R: {r:.3f} (p={p_val:.2e})")

    # Step 6: Save model
    model_path = output_dir / "xgb_binding_affinity.json"
    model.save_model(str(model_path))
    print(f"\nModel saved to {model_path}")

    # Save metadata
    metadata = {
        "feature_names": FEATURE_NAMES,
        "n_features": len(FEATURE_NAMES),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "test_rmse": round(rmse, 4),
        "test_mae": round(mae, 4),
        "test_pearson_r": round(r, 4),
        "xgb_params": model.get_params(),
    }
    # Convert numpy types for JSON serialization
    def _serialize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    meta_path = output_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=_serialize)
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    main()
