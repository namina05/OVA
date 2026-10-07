"""Saving and loading the three cycle models with their calibration and metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xgboost import XGBRegressor

from ml.cycle.features import CYCLE_FEATURES, PAIN_FEATURES, PERIOD_FEATURES
from ml.models.model_store import ModelNotFoundError

TASKS: dict[str, tuple[str, ...]] = {
    "cycle_length": CYCLE_FEATURES,
    "period_length": PERIOD_FEATURES,
    "pain": PAIN_FEATURES,
}
METADATA_FILE = "metadata.json"


@dataclass
class CycleModelBundle:
    models: dict[str, XGBRegressor]
    # Calibrated multiplier of each task's spread giving the requested coverage.
    interval_quantiles: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", "unknown"))


def save_cycle_bundle(bundle: CycleModelBundle, directory: str | Path) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for task, model in bundle.models.items():
        model.save_model(path / f"{task}.json")
    metadata = {
        **bundle.metadata,
        "interval_quantiles": bundle.interval_quantiles,
        "feature_columns": {task: list(cols) for task, cols in TASKS.items()},
    }
    (path / METADATA_FILE).write_text(json.dumps(metadata, indent=2, default=str))
    return path


def load_cycle_bundle(directory: str | Path) -> CycleModelBundle:
    path = Path(directory)
    files = [path / f"{t}.json" for t in TASKS] + [path / METADATA_FILE]
    if not all(f.is_file() for f in files):
        raise ModelNotFoundError(f"no trained cycle model in {path}")
    metadata = json.loads((path / METADATA_FILE).read_text())
    for task, columns in TASKS.items():
        if metadata["feature_columns"].get(task) != list(columns):
            raise ValueError(f"saved {task} features differ from the code; retrain the cycle model")
    models = {}
    for task in TASKS:
        model = XGBRegressor()
        model.load_model(path / f"{task}.json")
        models[task] = model
    return CycleModelBundle(models, metadata["interval_quantiles"], metadata)
