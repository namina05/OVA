"""Train the cycle models: cycle length (-> next period start), period length, pain.

Usage:
  python -m ml.cycle.train --synthetic --out models/cycle          # development only
  python -m ml.cycle.train --csv-dir data/ --out models/cycle      # periods.csv, daily_logs.csv, profiles.csv
  python -m ml.cycle.train --from-db --out models/cycle            # reads DATABASE_URL

Users are split into train / validation / test groups that never overlap.
Validation drives early stopping and calibrates the prediction ranges
(split conformal), and the test users are scored once at the end, against
simple baselines, so it is clear what the model adds.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from ml.cycle.datasets import TaskData, build_datasets, cap_cycle_adjustment
from ml.cycle.model_store import CycleModelBundle, save_cycle_bundle
from ml.training.train import TrainingParams, regression_metrics, split_by_user

logger = logging.getLogger(__name__)

DEFAULT_COVERAGE = 0.8


def conformal_quantile(scores: np.ndarray, coverage: float) -> float:
    """Split-conformal quantile: about `coverage` of new errors fall within it."""
    n = len(scores)
    if n == 0:
        raise ValueError("no validation rows to calibrate the prediction range")
    rank = min(n, int(np.ceil((n + 1) * coverage)))  # the rank-th smallest score
    return float(np.sort(scores)[rank - 1])


def _fit(task: TaskData, train: np.ndarray, val: np.ndarray, params: TrainingParams) -> XGBRegressor:
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
        eval_metric="mae",
        random_state=params.random_state,
        n_jobs=1,
    )
    model.fit(
        task.features.iloc[train], task.residual[train],
        eval_set=[(task.features.iloc[val], task.residual[val])], verbose=False,
    )
    return model


def _predict(model: XGBRegressor, task: TaskData, idx: np.ndarray, name: str = "") -> np.ndarray:
    adjustment = model.predict(task.features.iloc[idx])
    if name == "cycle_length":  # scored exactly as the predictor will use it
        adjustment = cap_cycle_adjustment(adjustment, task.features.iloc[idx]["std_last6"].to_numpy())
    return task.baseline[idx] + adjustment


def train_cycle_models(
    periods: pd.DataFrame,
    daily_logs: pd.DataFrame,
    profiles: pd.DataFrame,
    params: TrainingParams | None = None,
    coverage: float = DEFAULT_COVERAGE,
    pain_source: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None = None,
) -> CycleModelBundle:
    """pain_source: (periods, daily_logs, profiles) for the pain model when the main data has no pain logs."""
    params = params or TrainingParams()
    datasets = build_datasets(periods, daily_logs, profiles)
    if pain_source is not None:
        datasets["pain"] = build_datasets(*pain_source)["pain"]
    models: dict[str, XGBRegressor] = {}
    quantiles: dict[str, float] = {}
    metrics: dict[str, Any] = {}

    for name, task in datasets.items():
        train, val, test = split_by_user(task.groups, params)
        model = _fit(task, train, val, params)
        val_scores = np.abs(task.target[val] - _predict(model, task, val, name)) / task.scale[val]
        q = conformal_quantile(val_scores, coverage)

        pred = _predict(model, task, test, name)
        half_width = q * task.scale[test]
        y = task.target[test]
        m: dict[str, Any] = {
            "test": regression_metrics(y, pred),
            "test_baseline": regression_metrics(y, task.baseline[test]) if name != "pain" else None,
            "interval_coverage": float(np.mean(np.abs(y - pred) <= half_width)),
            "interval_mean_half_width": float(np.mean(half_width)),
            "best_iteration": int(model.best_iteration),
            "rows": {"train": len(train), "validation": len(val), "test": len(test)},
        }
        if name == "cycle_length":
            m["test_fixed_28_days"] = regression_metrics(y, np.full_like(y, 28.0))
            enough = task.extra["n_prior"][test] >= 2
            if enough.any():
                m["test_users_with_2plus_cycles"] = regression_metrics(y[enough], pred[enough])
                m["test_baseline_users_with_2plus_cycles"] = regression_metrics(y[enough], task.baseline[test][enough])
        if name == "pain":
            # Baseline: this user's average pain on that day of earlier periods, else the training mean.
            prior = task.features.iloc[test]["prior_mean_pain_day"].to_numpy()
            fallback = float(task.target[train].mean())
            m["test_baseline"] = regression_metrics(y, np.where(np.isnan(prior), fallback, prior))
        models[name], quantiles[name], metrics[name] = model, q, m
        logger.info("%s: test MAE %.2f (baseline %.2f)", name, m["test"]["mae"], m["test_baseline"]["mae"])

    metadata = {
        "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "coverage_target": coverage,
        "training_params": params.__dict__,
        "metrics": metrics,
    }
    return CycleModelBundle(models, quantiles, metadata)


def _load(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if args.synthetic:
        from ml.cycle.synthetic import generate_synthetic_cycles

        logger.warning("training on SYNTHETIC cycle data: for development only, never deploy this model")
        d = generate_synthetic_cycles(n_users=args.synthetic_users)
        return d.periods, d.daily_logs, d.profiles
    if args.csv_dir:
        from pathlib import Path

        base = Path(args.csv_dir)
        logs = pd.read_csv(base / "daily_logs.csv")
        if "symptoms" in logs.columns:
            logs = logs.drop(columns=["symptoms"])
        return pd.read_csv(base / "periods.csv"), logs, pd.read_csv(base / "profiles.csv")
    from api.services.cycle_repository import PostgresCycleRepository
    from config import AppSettings

    settings = AppSettings.from_env()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    repo = PostgresCycleRepository(settings.database_url)
    return repo.get_all_periods(), repo.get_all_daily_logs(), repo.get_all_profiles()


def _train_from_dataset(args: argparse.Namespace) -> CycleModelBundle:
    """Cycle and period-length models from the dataset's training users; pain from synthetic data."""
    from pathlib import Path

    from ml.cycle.external_dataset import read_cycle_dataset, split_users, to_app_tables
    from ml.cycle.synthetic import generate_synthetic_cycles

    raw = read_cycle_dataset(args.dataset)
    train_raw, holdout_raw = split_users(raw, args.holdout_fraction, args.split_seed)
    if args.holdout_out:
        out = Path(args.holdout_out)
        out.mkdir(parents=True, exist_ok=True)
        train_raw.to_csv(out / "train_users.csv", index=False)
        holdout_raw.to_csv(out / "holdout_users.csv", index=False)
    train = to_app_tables(train_raw)
    logger.warning("the dataset has no pain logs: the pain model is trained on SYNTHETIC data")
    synthetic = generate_synthetic_cycles(n_users=args.synthetic_users)
    bundle = train_cycle_models(
        train.periods, train.daily_logs, train.profiles, coverage=args.coverage,
        pain_source=(synthetic.periods, synthetic.daily_logs, synthetic.profiles),
    )
    bundle.metadata["data_sources"] = {
        "cycle_length": f"{Path(args.dataset).name} (training users only)",
        "period_length": f"{Path(args.dataset).name} (training users only)",
        "pain": "synthetic",
    }
    bundle.metadata["dataset_split"] = {
        "holdout_fraction": args.holdout_fraction,
        "seed": args.split_seed,
        "train_users": sorted(int(u) for u in train_raw["User ID"].unique()),
        "holdout_users": sorted(int(u) for u in holdout_raw["User ID"].unique()),
        "train_cycles": len(train_raw),
        "holdout_cycles": len(holdout_raw),
    }
    bundle.metadata["synthetic_data"] = True  # pain model and the dataset itself are synthetic
    return bundle


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--synthetic", action="store_true")
    source.add_argument("--csv-dir")
    source.add_argument("--from-db", action="store_true")
    source.add_argument("--dataset", help="cycle dataset .xlsx/.csv (one row per cycle); trains on 80%% of users")
    parser.add_argument("--holdout-fraction", type=float, default=0.2, help="users kept out of training")
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--holdout-out", help="folder to write train_users.csv and holdout_users.csv")
    parser.add_argument("--synthetic-users", type=int, default=400)
    parser.add_argument("--coverage", type=float, default=DEFAULT_COVERAGE)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dataset:
        bundle = _train_from_dataset(args)
    else:
        bundle = train_cycle_models(*_load(args), coverage=args.coverage)
        if args.synthetic:
            bundle.metadata["synthetic_data"] = True
    save_cycle_bundle(bundle, args.out)

    print(f"saved cycle models {bundle.version} to {args.out}")
    if "dataset_split" in bundle.metadata:
        sp = bundle.metadata["dataset_split"]
        print(f"dataset split: {len(sp['train_users'])} training users ({sp['train_cycles']} cycles), "
              f"{len(sp['holdout_users'])} held-out users ({sp['holdout_cycles']} cycles) not used")
    for name, m in bundle.metadata["metrics"].items():
        print(
            f"{name:<14} MAE={m['test']['mae']:.2f} RMSE={m['test']['rmse']:.2f} | "
            f"baseline MAE={m['test_baseline']['mae']:.2f} | "
            f"{bundle.metadata['coverage_target']:.0%} range covers {m['interval_coverage']:.0%} "
            f"(avg ±{m['interval_mean_half_width']:.1f})"
        )
        if name == "cycle_length":
            print(f"{'':<14} fixed 28-day guess MAE={m['test_fixed_28_days']['mae']:.2f}")
            if "test_users_with_2plus_cycles" in m:
                print(
                    f"{'':<14} users with 2+ cycles: MAE={m['test_users_with_2plus_cycles']['mae']:.2f} "
                    f"vs recent-average MAE={m['test_baseline_users_with_2plus_cycles']['mae']:.2f}"
                )


if __name__ == "__main__":
    main()
