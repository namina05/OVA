"""Train the general pain-reduction model.

Usage:
  python -m ml.training.train --csv sessions.csv --out models/current
  python -m ml.training.train --from-db --out models/current      # reads DATABASE_URL
  python -m ml.training.train --synthetic --out models/dev          # development only

The split is by USER: train, validation and test users never overlap, so the
test score measures how well the model works for people it has never seen,
which is the situation of every new user of the belt. Validation is used for
early stopping; test is touched once, at the end.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBRegressor

from ml.models.model_store import ModelBundle, save_bundle
from ml.preprocessing.cleaning import clean_sessions
from ml.preprocessing.features import FeatureSpec, build_training_frame
from safety.limits import SafetyLimits, load_safety_limits

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingParams:
    n_estimators: int = 600
    learning_rate: float = 0.05
    max_depth: int = 4
    min_child_weight: float = 3.0
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 40
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    random_state: int = 42


@dataclass
class TrainingResult:
    bundle: ModelBundle
    metrics: dict[str, Any] = field(default_factory=dict)


class InsufficientDataError(ValueError):
    pass


def split_by_user(
    groups: np.ndarray, params: TrainingParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Index arrays for train / validation / test with no user in two sets."""
    if len(np.unique(groups)) < 3:
        raise InsufficientDataError("need sessions from at least 3 users to split train/validation/test")
    indices = np.arange(len(groups))
    outer = GroupShuffleSplit(n_splits=1, test_size=params.test_fraction, random_state=params.random_state)
    rest, test = next(outer.split(indices, groups=groups))
    val_share = params.validation_fraction / (1 - params.test_fraction)
    inner = GroupShuffleSplit(n_splits=1, test_size=val_share, random_state=params.random_state)
    train_rel, val_rel = next(inner.split(rest, groups=groups[rest]))
    return rest[train_rel], rest[val_rel], test


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else float("nan"),
        "n": int(len(y_true)),
    }


def train_model(
    raw_sessions: pd.DataFrame,
    limits: SafetyLimits,
    params: TrainingParams | None = None,
) -> TrainingResult:
    params = params or TrainingParams()
    sessions = clean_sessions(raw_sessions)
    spec = FeatureSpec(zones=limits.allowed_zones, modes=limits.allowed_modes)
    X, y, groups = build_training_frame(spec, sessions)
    train_idx, val_idx, test_idx = split_by_user(groups, params)
    logger.info("rows: train=%d validation=%d test=%d", len(train_idx), len(val_idx), len(test_idx))

    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=params.n_estimators,
        learning_rate=params.learning_rate,
        max_depth=params.max_depth,
        min_child_weight=params.min_child_weight,
        subsample=params.subsample,
        colsample_bytree=params.colsample_bytree,
        reg_lambda=params.reg_lambda,
        early_stopping_rounds=params.early_stopping_rounds,
        eval_metric="rmse",
        random_state=params.random_state,
        n_jobs=1,
    )
    model.fit(
        X.iloc[train_idx], y[train_idx],
        eval_set=[(X.iloc[val_idx], y[val_idx])],
        verbose=False,
    )

    y_test = y[test_idx]
    test_pred = model.predict(X.iloc[test_idx])
    baseline = np.full_like(y_test, y[train_idx].mean())
    cold = X.iloc[test_idx]["hist_n_sessions"].to_numpy() == 0
    metrics: dict[str, Any] = {
        "validation": regression_metrics(y[val_idx], model.predict(X.iloc[val_idx])),
        "test": regression_metrics(y_test, test_pred),
        "test_baseline_mean": regression_metrics(y_test, baseline),
        "test_cold_start": regression_metrics(y_test[cold], test_pred[cold]) if cold.any() else None,
        "test_with_history": regression_metrics(y_test[~cold], test_pred[~cold]) if (~cold).any() else None,
        "best_iteration": int(model.best_iteration),
        "users": {
            "train": int(len(np.unique(groups[train_idx]))),
            "validation": int(len(np.unique(groups[val_idx]))),
            "test": int(len(np.unique(groups[test_idx]))),
        },
    }
    metadata = {
        "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_sessions": int(len(sessions)),
        "training_params": params.__dict__,
        "safety_limits_at_training": limits.to_dict(),
        "metrics": metrics,
    }
    return TrainingResult(ModelBundle(model=model, spec=spec, metadata=metadata), metrics)


def _load_sessions(args: argparse.Namespace, limits: SafetyLimits) -> pd.DataFrame:
    if args.synthetic:
        from ml.training.synthetic import generate_synthetic_sessions

        logger.warning("training on SYNTHETIC data: for development only, never deploy this model")
        return generate_synthetic_sessions(n_users=args.synthetic_users, limits=limits)
    if args.csv:
        return pd.read_csv(args.csv)
    from api.services.repository import PostgresTherapySessionRepository
    from config import AppSettings

    settings = AppSettings.from_env()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    return PostgresTherapySessionRepository.from_settings(settings).get_all_sessions()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="CSV with therapy_sessions columns")
    source.add_argument("--from-db", action="store_true", help="read the therapy_sessions view")
    source.add_argument("--synthetic", action="store_true", help="generate synthetic data (development only)")
    parser.add_argument("--synthetic-users", type=int, default=300)
    parser.add_argument("--out", required=True, help="directory to write the model to")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    limits = load_safety_limits()
    result = train_model(_load_sessions(args, limits), limits)
    if args.synthetic:
        result.bundle.metadata["synthetic_data"] = True
    save_bundle(result.bundle, args.out)

    m = result.metrics
    print(f"saved model {result.bundle.version} to {args.out}")
    print(f"test   MAE={m['test']['mae']:.3f}  RMSE={m['test']['rmse']:.3f}  R2={m['test']['r2']:.3f}")
    print(f"mean-baseline MAE={m['test_baseline_mean']['mae']:.3f}  RMSE={m['test_baseline_mean']['rmse']:.3f}")
    for name in ("test_cold_start", "test_with_history"):
        if m[name]:
            print(f"{name:<18} MAE={m[name]['mae']:.3f}  RMSE={m[name]['rmse']:.3f}  (n={m[name]['n']})")


if __name__ == "__main__":
    main()
