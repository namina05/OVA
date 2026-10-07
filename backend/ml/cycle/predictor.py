"""Next-period, period-length and pain forecasts for one user.

Method for the start date, recorded in predictions.method:
  onboarding_default  no complete cycle logged yet: sign-up cycle length (or 28 days)
  recent_average      fewer than `min_cycles_for_model` cycles: their average
  model               XGBoost correction to the user's recent average, with a
                      calibrated range and a SHAP explanation

Period length and pain always use their models, which fall back on sign-up
values and the general population when the user has little history, and the
result says how personal it is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
import shap

from ml.cycle import data as cd
from ml.cycle.datasets import cap_cycle_adjustment, cycle_scale
from ml.cycle.features import (
    CYCLE_FEATURES,
    PAIN_FEATURES,
    PAIN_OFFSETS,
    PERIOD_FEATURES,
    PainHistory,
    cycle_baseline,
    cycle_features,
    pain_features,
    period_baseline,
    period_features,
)
from ml.cycle.model_store import CycleModelBundle
from ml.recommendation.personalization import PersonalizationLevel

ONBOARDING_RANGE_DAYS = 7
RECENT_AVERAGE_MIN_RANGE_DAYS = 4
MIN_SHAP_DAYS = 0.3

_FACTOR_TEXT = {
    "last_cycle": "your last cycle ({:.0f} days)",
    "mean_last3": "your recent average ({:.1f} days)",
    "median_prior": "your usual cycle ({:.0f} days)",
    "std_last6": "how much your cycles vary (±{:.1f} days)",
    "min_last6": "your shortest recent cycle ({:.0f} days)",
    "max_last6": "your longest recent cycle ({:.0f} days)",
    "trend": "the change in your last cycle ({:+.1f} days vs. average)",
    "typical_cycle_length": "the cycle length you entered at sign-up ({:.0f} days)",
    "age": "your age ({:.0f})",
    "mean_period_length": "your recent period length ({:.1f} days)",
    "n_prior_cycles": "the number of cycles logged ({:.0f})",
    "baseline": "the starting estimate ({:.1f} days)",
}


class NoPeriodDataError(ValueError):
    """The user has not logged any period start yet."""


@dataclass(frozen=True)
class PainDay:
    date: date
    day: int  # relative to the predicted start; 0 = first day
    expected_pain: float
    low: float
    high: float

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "day": self.day, "expected_pain": self.expected_pain,
                "low": self.low, "high": self.high}


@dataclass(frozen=True)
class CycleFactor:
    name: str
    contribution_days: float
    description: str


@dataclass(frozen=True)
class CycleForecast:
    method: str
    last_period_start: date
    predicted_start: date
    range_days: int
    predicted_cycle_length: float
    predicted_period_length: int
    period_length_range_days: int
    pain_forecast: list[PainDay]
    days_until_start: int
    is_late: bool
    personalization_level: PersonalizationLevel
    complete_cycles: int
    explanation: str
    factors: list[CycleFactor] = field(default_factory=list)
    model_version: str = ""


class CyclePredictor:
    def __init__(self, bundle: CycleModelBundle, min_cycles_for_model: int = 2) -> None:
        self.bundle = bundle
        self.min_cycles_for_model = min_cycles_for_model
        self._cycle_explainer = shap.TreeExplainer(bundle.models["cycle_length"])

    def _model(self, task: str, columns: tuple[str, ...], rows: list[dict[str, float]]) -> np.ndarray:
        return self.bundle.models[task].predict(pd.DataFrame(rows, columns=list(columns), dtype=float))

    def predict(
        self,
        periods: pd.DataFrame,
        daily_logs: pd.DataFrame,
        profile: cd.Profile,
        today: date,
    ) -> CycleForecast:
        periods = cd.clean_periods(periods) if not periods.empty else periods
        if periods.empty:
            raise NoPeriodDataError("log the first day of a period to get predictions")
        logs = cd.clean_daily_logs(daily_logs) if not daily_logs.empty else pd.DataFrame(
            columns=[cd.USER_ID, cd.LOG_DATE, cd.PAIN, cd.SYMPTOMS]
        )
        cycles = cd.UserCycles.from_periods(periods)
        last_start = cycles.starts[-1]
        age = profile.age_on(today)
        prior_cycles = [float(c) for c in cycles.cycle_lengths if c is not None]
        prior_periods = [float(p) for p in cycles.period_lengths if p is not None]
        n = len(prior_cycles)

        # -- cycle length -> next start ------------------------------------
        base = cycle_baseline(prior_cycles, profile)
        factors: list[CycleFactor] = []
        if n == 0:
            method, length, range_days = "onboarding_default", base.value, ONBOARDING_RANGE_DAYS
            explanation = (
                f"No complete cycle is logged yet, so this uses {base.description} ({base.value:.0f} days). "
                "Predictions become personal after you log your next period start."
            )
        elif n < self.min_cycles_for_model:
            method, length = "recent_average", base.value
            range_days = max(RECENT_AVERAGE_MIN_RANGE_DAYS, math.ceil(np.std(prior_cycles)) if n > 1 else 0)
            explanation = (
                f"Based on {base.description} ({base.value:.1f} days). With fewer than "
                f"{self.min_cycles_for_model} logged cycles the model is not used yet."
            )
        else:
            method = "model"
            row = cycle_features(prior_cycles, prior_periods, profile, age)
            frame = pd.DataFrame([row], columns=list(CYCLE_FEATURES), dtype=float)
            range_days = max(1, math.ceil(self.bundle.interval_quantiles["cycle_length"] * cycle_scale(row["std_last6"])))
            adjustment = float(cap_cycle_adjustment(
                self.bundle.models["cycle_length"].predict(frame)[0], row["std_last6"]
            ))
            length = base.value + adjustment
            factors = self._cycle_factors(frame, row)
            explanation = f"Based on {base.description} (average {base.value:.1f} days)"
            if abs(adjustment) >= 0.5 and factors:
                top = [f.description for f in factors if math.copysign(1, f.contribution_days) == math.copysign(1, adjustment)][:2]
                explanation += f", adjusted by {adjustment:+.1f} days" + (f" mainly because of {' and '.join(top)}" if top else "")
            explanation += f". Your cycles are expected to vary by about ±{range_days} days."

        predicted_start = last_start + timedelta(days=int(round(length)))
        days_until = (predicted_start - today).days

        # -- period length ------------------------------------------------
        p_base = period_baseline(prior_periods, profile)
        p_row = period_features(prior_periods, prior_cycles, profile, age)
        period_length = p_base.value + float(self._model("period_length", PERIOD_FEATURES, [p_row])[0])
        period_length_int = int(np.clip(round(period_length), cd.MIN_PERIOD_DAYS, cd.MAX_PERIOD_DAYS))
        period_range = max(1, math.ceil(self.bundle.interval_quantiles["period_length"]))

        # -- pain forecast ------------------------------------------------
        history = PainHistory([
            cd.pain_by_offset(logs[logs[cd.USER_ID] == str(periods[cd.USER_ID].iloc[0])], s, PAIN_OFFSETS)
            for s in cycles.starts
        ])
        days = [d for d in PAIN_OFFSETS if d < period_length_int]
        pain_rows = [pain_features(d, history, p_base.value, age) for d in days]
        pains = np.clip(self._model("pain", PAIN_FEATURES, pain_rows), 0, 10)
        q_pain = self.bundle.interval_quantiles["pain"]
        forecast = [
            PainDay(
                predicted_start + timedelta(days=d), d, round(float(p), 1),
                round(float(max(0.0, p - q_pain)), 1), round(float(min(10.0, p + q_pain)), 1),
            )
            for d, p in zip(days, pains)
        ]

        if n == 0:
            level = PersonalizationLevel.NONE
        elif n < self.min_cycles_for_model:
            level = PersonalizationLevel.LIMITED
        else:
            level = PersonalizationLevel.PERSONALIZED

        if history.n_with_data == 0:
            explanation += " The pain forecast is not personal yet: log your pain during your period to improve it."
        else:
            peak = max(forecast, key=lambda d: d.expected_pain)
            explanation += (
                f" From your logged pain, the most painful day is expected to be day {peak.day + 1} "
                f"({peak.date.isoformat()}, about {peak.expected_pain:.0f}/10)."
                if peak.day >= 0 else
                f" From your logged pain, pain may start before your period, around {peak.date.isoformat()}."
            )

        return CycleForecast(
            method=method,
            last_period_start=last_start,
            predicted_start=predicted_start,
            range_days=int(range_days),
            predicted_cycle_length=round(float(length), 1),
            predicted_period_length=period_length_int,
            period_length_range_days=period_range,
            pain_forecast=forecast,
            days_until_start=days_until,
            is_late=days_until < 0,
            personalization_level=level,
            complete_cycles=n,
            explanation=explanation,
            factors=factors,
            model_version=self.bundle.version,
        )

    def _cycle_factors(self, frame: pd.DataFrame, row: dict[str, float]) -> list[CycleFactor]:
        values = np.asarray(self._cycle_explainer.shap_values(frame))[0]
        factors = [
            CycleFactor(name, round(float(v), 2), _FACTOR_TEXT[name].format(row[name]))
            for name, v in zip(frame.columns, values)
            if abs(v) >= MIN_SHAP_DAYS and not math.isnan(row[name])
        ]
        return sorted(factors, key=lambda f: -abs(f.contribution_days))
