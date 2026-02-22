"""GNN Binding Affinity prediction service.

Predicts binding affinity (pKd) from protein-ligand 3D complexes using a
Graph Isomorphism Network (GIN) trained on PDBbind v2020. Follows the same
module-level lazy-loading pattern as services/admet.py.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# ─── Optional heavy imports (deferred until model load) ──────────────────────

_torch = None
_pyg_nn = None
_pyg_data = None
_pyg_pool = None

# ─── Module-level model holder ───────────────────────────────────────────────

_gnn_model = None
_model_config: dict | None = None

# ─── Constants ───────────────────────────────────────────────────────────────

# One-hot encoding for common elements (top 10 in PDBbind)
ELEMENT_LIST = [6, 7, 8, 16, 15, 9, 17, 35, 53, 5, 30]  # C,N,O,S,P,F,Cl,Br,I,B,Zn

# 20 standard amino acids
AA_LIST = [
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
    "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
    "THR", "TRP", "TYR", "VAL",
]
AA_TO_IDX = {aa: i for i, aa in enumerate(AA_LIST)}

# Hybridization mapping (RDKit)
HYBRIDIZATION_LIST = ["SP", "SP2", "SP3", "SP3D", "SP3D2"]

# RBF parameters for edge distance encoding
RBF_CENTERS = np.linspace(0.0, 10.0, 21)
RBF_GAMMA = 5.0

# 11 elem + 5 hybrid + 1 charge + 1 arom + 1 ring + 1 neighbors + 1 protein + 20 AA + 6 pad = 47
NODE_DIM = 47
EDGE_DIM = 24  # 21 (RBF distance) + 3 (edge type one-hot: intra-lig, intra-prot, inter)


# ─── Model Definition ────────────────────────────────────────────────────────

def _get_model_class():
    """Return the BindingAffinityGNN class (imports torch lazily)."""
    global _torch, _pyg_nn, _pyg_data, _pyg_pool

    import torch
    import torch.nn as nn
    import torch_geometric.nn as pyg_nn
    import torch_geometric.data as pyg_data
    from torch_geometric.nn import global_mean_pool, global_max_pool

    _torch = torch
    _pyg_nn = pyg_nn
    _pyg_data = pyg_data
    _pyg_pool = {"mean": global_mean_pool, "max": global_max_pool}

    class BindingAffinityGNN(nn.Module):
        """3-layer GIN with batch norm for pKd prediction."""

        def __init__(self, node_dim: int = NODE_DIM, edge_dim: int = EDGE_DIM, hidden_dim: int = 128):
            super().__init__()
            self.node_encoder = nn.Linear(node_dim, hidden_dim)

            self.convs = nn.ModuleList()
            self.bns = nn.ModuleList()
            for _ in range(3):
                mlp = nn.Sequential(
                    nn.Linear(hidden_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, hidden_dim),
                )
                self.convs.append(pyg_nn.GINConv(mlp))
                self.bns.append(nn.BatchNorm1d(hidden_dim))

            # MLP head: concat(mean_pool, max_pool) -> scalar
            self.head = nn.Sequential(
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, 1),
            )

        def forward(self, data):
            x = self.node_encoder(data.x)
            for conv, bn in zip(self.convs, self.bns):
                x = conv(x, data.edge_index)
                x = bn(x)
                x = x.relu()

            batch = data.batch if hasattr(data, "batch") and data.batch is not None else _torch.zeros(x.size(0), dtype=_torch.long, device=x.device)
            x_mean = _pyg_pool["mean"](x, batch)
            x_max = _pyg_pool["max"](x, batch)
            x_cat = _torch.cat([x_mean, x_max], dim=-1)

            return self.head(x_cat).squeeze(-1)

    return BindingAffinityGNN


# ─── Featurization ───────────────────────────────────────────────────────────

def _rbf_encode(distance: float) -> np.ndarray:
    """Radial Basis Function encoding of a single distance."""
    return np.exp(-RBF_GAMMA * (distance - RBF_CENTERS) ** 2).astype(np.float32)


def _atom_features(
    atomic_num: int,
    hybridization: str | None = None,
    formal_charge: int = 0,
    is_aromatic: bool = False,
    is_in_ring: bool = False,
    num_heavy_neighbors: int = 0,
    is_protein: bool = False,
    residue_name: str | None = None,
) -> np.ndarray:
    """Compute node feature vector (47 dims)."""
    feat = np.zeros(NODE_DIM, dtype=np.float32)
    idx = 0

    if atomic_num in ELEMENT_LIST:
        feat[ELEMENT_LIST.index(atomic_num)] = 1.0
    idx += len(ELEMENT_LIST)

    if hybridization and hybridization in HYBRIDIZATION_LIST:
        feat[idx + HYBRIDIZATION_LIST.index(hybridization)] = 1.0
    idx += len(HYBRIDIZATION_LIST)

    feat[idx] = float(formal_charge);            idx += 1
    feat[idx] = 1.0 if is_aromatic else 0.0;     idx += 1
    feat[idx] = 1.0 if is_in_ring else 0.0;      idx += 1
    feat[idx] = float(num_heavy_neighbors);       idx += 1
    feat[idx] = 1.0 if is_protein else 0.0;      idx += 1

    if residue_name and residue_name in AA_TO_IDX:
        feat[idx + AA_TO_IDX[residue_name]] = 1.0

    return feat


def featurize_complex(pdb_text: str, ligand_sdf: str) -> object | None:
    """Convert protein PDB + ligand SDF strings into a PyG Data graph.

    This function accepts raw text (not file paths) so it can be reused
    identically in the training notebook and inference service.

    Returns a torch_geometric.data.Data object or None on failure.
    """
    global _torch, _pyg_data

    try:
        from rdkit import Chem
        from Bio.PDB import PDBParser
        import io
        import warnings

        if _torch is None:
            import torch
            import torch_geometric.data as pyg_data_mod
            _torch = torch
            globals()["_pyg_data"] = pyg_data_mod

        torch = _torch
        Data = _pyg_data.Data if _pyg_data else __import__("torch_geometric.data", fromlist=["Data"]).Data

        # --- Parse ligand ---
        mol = Chem.MolFromMolBlock(ligand_sdf, removeHs=False)
        if mol is None:
            mol = Chem.MolFromMolBlock(ligand_sdf, removeHs=True)
        if mol is None:
            return None

        # Get ligand conformer coordinates
        conf = mol.GetConformer()
        lig_coords = []
        lig_features = []
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            lig_coords.append([pos.x, pos.y, pos.z])
            hyb = str(atom.GetHybridization()) if atom.GetHybridization() else None
            lig_features.append(_atom_features(
                atomic_num=atom.GetAtomicNum(),
                hybridization=hyb,
                formal_charge=atom.GetFormalCharge(),
                is_aromatic=atom.GetIsAromatic(),
                is_in_ring=atom.IsInRing(),
                num_heavy_neighbors=len([n for n in atom.GetNeighbors() if n.GetAtomicNum() > 1]),
                is_protein=False,
            ))
        lig_coords = np.array(lig_coords)
        n_lig = len(lig_features)

        # --- Parse protein binding pocket ---
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parser = PDBParser(QUIET=True)
            structure = parser.get_structure("protein", io.StringIO(pdb_text))

        prot_atoms = []
        for atom in structure.get_atoms():
            if atom.element.strip() in ("H", ""):
                continue
            prot_atoms.append(atom)

        if not prot_atoms:
            return None

        prot_coords_all = np.array([a.get_vector().get_array() for a in prot_atoms])

        # Extract binding pocket: protein atoms within 10A of any ligand atom
        from scipy.spatial.distance import cdist
        dist_matrix = cdist(prot_coords_all, lig_coords)
        pocket_mask = dist_matrix.min(axis=1) < 10.0
        pocket_indices = np.where(pocket_mask)[0]

        if len(pocket_indices) == 0:
            return None

        pocket_atoms = [prot_atoms[i] for i in pocket_indices]
        pocket_coords = prot_coords_all[pocket_indices]

        # Protein node features
        prot_features = []
        for atom in pocket_atoms:
            elem = atom.element.strip().capitalize()
            atomic_num = Chem.GetPeriodicTable().GetAtomicNumber(elem) if elem else 6
            residue = atom.get_parent()
            res_name = residue.get_resname() if residue else None
            prot_features.append(_atom_features(
                atomic_num=atomic_num,
                is_protein=True,
                residue_name=res_name,
            ))
        n_prot = len(prot_features)

        # --- Build graph ---
        all_features = np.array(lig_features + prot_features, dtype=np.float32)
        all_coords = np.vstack([lig_coords, pocket_coords])

        edge_src = []
        edge_dst = []
        edge_features = []

        # Edge type one-hot: [intra_ligand, intra_protein, inter]

        # Intra-ligand bonds (from RDKit)
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            dist = np.linalg.norm(all_coords[i] - all_coords[j])
            rbf = _rbf_encode(dist)
            etype = np.array([1, 0, 0], dtype=np.float32)
            ef = np.concatenate([rbf, etype])
            edge_src.extend([i, j])
            edge_dst.extend([j, i])
            edge_features.extend([ef, ef])

        # Intra-protein bonds (< 1.6A between pocket atoms)
        if n_prot > 1:
            prot_dist = cdist(pocket_coords, pocket_coords)
            pi, pj = np.where((prot_dist < 1.6) & (prot_dist > 0.1))
            for ii, jj in zip(pi, pj):
                dist = prot_dist[ii, jj]
                rbf = _rbf_encode(dist)
                etype = np.array([0, 1, 0], dtype=np.float32)
                ef = np.concatenate([rbf, etype])
                edge_src.append(n_lig + ii)
                edge_dst.append(n_lig + jj)
                edge_features.append(ef)

        # Protein-ligand interactions (< 5A)
        cross_dist = cdist(lig_coords, pocket_coords)
        li, pi = np.where(cross_dist < 5.0)
        for l_idx, p_idx in zip(li, pi):
            dist = cross_dist[l_idx, p_idx]
            rbf = _rbf_encode(dist)
            etype = np.array([0, 0, 1], dtype=np.float32)
            ef = np.concatenate([rbf, etype])
            # Bidirectional
            edge_src.extend([l_idx, n_lig + p_idx])
            edge_dst.extend([n_lig + p_idx, l_idx])
            edge_features.extend([ef, ef])

        if not edge_src:
            return None

        x = torch.tensor(all_features, dtype=torch.float32)
        edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
        edge_attr = torch.tensor(np.array(edge_features, dtype=np.float32), dtype=torch.float32)
        pos = torch.tensor(all_coords, dtype=torch.float32)

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, pos=pos)

    except Exception as e:
        print(f"Warning: featurize_complex failed: {e}")
        return None


# ─── Model Loading ───────────────────────────────────────────────────────────

def load_gnn_model(model_dir: str | Path | None = None) -> bool:
    """Load pre-trained GNN binding affinity model. Returns True on success."""
    global _gnn_model, _model_config

    if model_dir is None:
        model_dir = Path(__file__).parent.parent / "models" / "gnn_affinity"
    else:
        model_dir = Path(model_dir)

    weights_path = model_dir / "gnn_binding_affinity.pt"
    if not weights_path.exists():
        print(f"GNN affinity model not found at {weights_path}")
        return False

    try:
        import torch

        BindingAffinityGNN = _get_model_class()

        checkpoint = torch.load(weights_path, map_location="cpu", weights_only=False)

        # Support both raw state_dict and dict with metadata
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
            _model_config = {k: v for k, v in checkpoint.items() if k != "state_dict"}
        else:
            state_dict = checkpoint
            _model_config = {}

        hidden_dim = _model_config.get("hidden_dim", 128)
        model = BindingAffinityGNN(
            node_dim=NODE_DIM,
            edge_dim=EDGE_DIM,
            hidden_dim=hidden_dim,
        )
        model.load_state_dict(state_dict)
        model.eval()
        _gnn_model = model
        print(f"GNN affinity model loaded from {weights_path}")
        return True

    except Exception as e:
        print(f"Warning: Could not load GNN affinity model: {e}")
        _gnn_model = None
        _model_config = None
        return False


# ─── Inference ───────────────────────────────────────────────────────────────

def predict_binding_affinity(pdb_text: str, ligand_sdf: str) -> dict | None:
    """Predict binding affinity from protein PDB text and ligand SDF text.

    Returns {"predicted_pkd": float, "predicted_kd_nm": float} or None.
    """
    if _gnn_model is None:
        return None

    try:
        import torch

        data = featurize_complex(pdb_text, ligand_sdf)
        if data is None:
            return None

        with torch.no_grad():
            pkd = _gnn_model(data).item()

        # Convert pKd to Kd in nanomolar: Kd = 10^(-pKd) * 1e9
        kd_nm = math.pow(10, -pkd) * 1e9

        return {
            "predicted_pkd": round(pkd, 2),
            "predicted_kd_nm": round(kd_nm, 1),
        }

    except Exception as e:
        print(f"Warning: GNN affinity prediction failed: {e}")
        return None
