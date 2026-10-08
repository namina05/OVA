"""Saving and loading the therapy model with its feature spec and metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xgboost import XGBRegressor

from ml.preprocessing.features import FeatureSpec

MODEL_FILE = "model.json"
METADATA_FILE = "metadata.json"


class ModelNotFoundError(FileNotFoundError):
    pass


@dataclass
class ModelBundle:
    model: XGBRegressor
    spec: FeatureSpec
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", "unknown"))


def save_bundle(bundle: ModelBundle, directory: str | Path) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    bundle.model.save_model(path / MODEL_FILE)
    metadata = {
        **bundle.metadata,
        "feature_spec": bundle.spec.to_dict(),
        "feature_columns": bundle.spec.feature_columns,
    }
    (path / METADATA_FILE).write_text(json.dumps(metadata, indent=2, default=str))
    return path


def load_bundle(directory: str | Path) -> ModelBundle:
    path = Path(directory)
    if not (path / MODEL_FILE).is_file() or not (path / METADATA_FILE).is_file():
        raise ModelNotFoundError(f"no trained model in {path}")
    metadata = json.loads((path / METADATA_FILE).read_text())
    spec = FeatureSpec.from_dict(metadata["feature_spec"])
    if metadata["feature_columns"] != spec.feature_columns:
        raise ValueError("saved features differ from the code; retrain the model")
    model = XGBRegressor()
    model.load_model(path / MODEL_FILE)
    return ModelBundle(model, spec, metadata)
