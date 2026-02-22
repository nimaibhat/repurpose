"""Train a Tox21 toxicity prediction model using DeepChem.

Requires: pip install deepchem>=2.8 tensorflow
Run:      python3 backend/scripts/train_tox21.py

The trained model is saved to backend/models/tox21/
and transformers to backend/models/tox21_transformers.pkl.
Both are automatically loaded by the ADMET service at startup.
"""

import os
import pickle
from pathlib import Path

# DeepChem 2.5 requires Keras 2 (tf-keras) with TF 2.20+
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")


def train():
    import deepchem as dc

    model_dir = Path(__file__).parent.parent / "models" / "tox21"
    model_dir.mkdir(parents=True, exist_ok=True)
    transformers_path = Path(__file__).parent.parent / "models" / "tox21_transformers.pkl"

    print("Loading Tox21 dataset...")
    tasks, datasets, transformers = dc.molnet.load_tox21(featurizer="GraphConv")
    train_dataset, valid_dataset, test_dataset = datasets

    print(f"Tasks: {len(tasks)}")
    print(f"Train samples: {len(train_dataset)}")
    print(f"Valid samples: {len(valid_dataset)}")

    model = dc.models.GraphConvModel(
        n_tasks=len(tasks),
        mode="classification",
        model_dir=str(model_dir),
        batch_size=128,
        learning_rate=0.001,
    )

    print("Training...")
    model.fit(train_dataset, nb_epoch=30)

    # Save transformers for inference-time normalization
    with open(transformers_path, "wb") as f:
        pickle.dump(transformers, f)
    print(f"Transformers saved to: {transformers_path}")

    # Evaluate
    metric = dc.metrics.Metric(dc.metrics.roc_auc_score)
    train_score = model.evaluate(train_dataset, [metric], transformers)
    valid_score = model.evaluate(valid_dataset, [metric], transformers)
    test_score = model.evaluate(test_dataset, [metric], transformers)

    print(f"Train ROC-AUC: {train_score}")
    print(f"Valid ROC-AUC: {valid_score}")
    print(f"Test  ROC-AUC: {test_score}")
    print(f"Model saved to: {model_dir}")


if __name__ == "__main__":
    train()
