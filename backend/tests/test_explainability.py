import numpy as np
import pandas as pd
import pytest

from ml import schema
from ml.explainability.shap_explainer import ShapExplainer, feature_group
from ml.preprocessing.features import TherapyContext, build_feature_row, to_frame
from ml.preprocessing.history import UserHistory
from ml.recommendation.personalization import build_user_history
from ml.recommendation.service import RecommendationService
from safety.setting import TherapySetting

SETTING = TherapySetting("lower_abdomen", 40.0, 20.0, "continuous")
CONTEXT = TherapyContext(pain_before=7, pain_zone="lower_abdomen", cycle_day=2, cycle_phase="menstrual")


def user_history(reduction_at_40: int, reduction_elsewhere: int) -> UserHistory:
    rows = [("lower_abdomen", 40, 20, 8, 8 - reduction_at_40)] * 6 + [("lower_back", 38, 15, 8, 8 - reduction_elsewhere)] * 6
    return build_user_history(pd.DataFrame([
        {
            schema.USER_ID: "u1", schema.STARTED_AT: pd.Timestamp("2026-03-01", tz="UTC") + pd.Timedelta(days=i),
            schema.ZONE: z, schema.TEMPERATURE: t, schema.DURATION: d, schema.MODE: "continuous",
            schema.PAIN_BEFORE: b, schema.PAIN_AFTER: a,
        }
        for i, (z, t, d, b, a) in enumerate(rows)
    ]))


@pytest.fixture(scope="module")
def explainer(bundle) -> ShapExplainer:
    return ShapExplainer(bundle)


def test_every_feature_belongs_to_a_group(bundle):
    for column in bundle.spec.feature_columns:
        assert feature_group(column)


def test_shap_contributions_add_up_to_the_prediction(bundle, explainer):
    history = user_history(5, 1)
    features = to_frame(bundle.spec, [build_feature_row(bundle.spec, CONTEXT, SETTING, history)])
    prediction = float(bundle.model.predict(features)[0])
    total = explainer.base_value + sum(explainer.contributions(features).values())
    assert total == pytest.approx(prediction, abs=1e-2)  # float32 rounding


def test_explanation_names_the_setting_and_real_history(bundle, explainer):
    history = user_history(5, 1)
    features = to_frame(bundle.spec, [build_feature_row(bundle.spec, CONTEXT, SETTING, history)])
    explanation = explainer.explain(features, SETTING, CONTEXT, history, 3.0)
    assert explanation.text.startswith("Recommended: Lower abdomen, 40°C for 20 minutes")
    assert explanation.factors == tuple(sorted(explanation.factors, key=lambda f: -abs(f.contribution)))
    # numbers quoted in the text come from the actual history
    zone_factor = next(f for f in explanation.factors if f.name == "history_zone")
    assert "6 previous sessions on the lower abdomen (average reduction 5.0)" in zone_factor.description
    assert "associated with better reported pain relief" in explanation.text


def test_no_better_relief_claim_when_history_was_worse(bundle, explainer):
    history = user_history(1, 5)  # this setting did worse than the user's average
    features = to_frame(bundle.spec, [build_feature_row(bundle.spec, CONTEXT, SETTING, history)])
    explanation = explainer.explain(features, SETTING, CONTEXT, history, 1.0)
    assert "associated with better" not in explanation.text


def test_cold_start_explanation_does_not_mention_past_sessions(bundle, explainer):
    history = UserHistory.empty()
    features = to_frame(bundle.spec, [build_feature_row(bundle.spec, CONTEXT, SETTING, history)])
    explanation = explainer.explain(features, SETTING, CONTEXT, history, 2.0)
    assert "previous session" not in explanation.text
    assert not any(f.name.startswith("history_") for f in explanation.factors)
