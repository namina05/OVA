from datetime import date, timedelta

import pandas as pd
import pytest

from knowledge_graph.graph import KnowledgeGraph
from knowledge_graph.personal import PersonalGraphBuilder
from ml import schema
from ml.cycle import data as cd

TODAY = date(2026, 10, 1)


@pytest.fixture(scope="module")
def builder() -> PersonalGraphBuilder:
    return PersonalGraphBuilder(KnowledgeGraph.load_json(), symptom_lookback_days=90, min_zone_sessions=3)


def periods(lengths, first=date(2026, 1, 1), period_days=5) -> pd.DataFrame:
    starts = [first]
    for n in lengths:
        starts.append(starts[-1] + timedelta(days=n))
    return pd.DataFrame({cd.USER_ID: "u1", cd.START: starts,
                         cd.END: [s + timedelta(days=period_days - 1) for s in starts]})


def sessions(rows) -> pd.DataFrame:
    return pd.DataFrame([
        {schema.USER_ID: "u1", schema.STARTED_AT: pd.Timestamp("2026-09-01", tz="UTC") + pd.Timedelta(days=i),
         schema.ZONE: z, schema.TEMPERATURE: 40, schema.DURATION: 20, schema.MODE: "continuous",
         schema.PAIN_BEFORE: 8, schema.PAIN_AFTER: 8 - r}
        for i, (z, r) in enumerate(rows)
    ])


EMPTY = pd.DataFrame()


def test_regular_cycles_give_no_pattern(builder):
    assert builder.detect_patterns(periods([28, 29, 28]), date(2026, 4, 1)) == {}


@pytest.mark.parametrize("lengths, today, expected", [
    ([20, 21, 20], date(2026, 3, 15), "pattern:cycle_outside_24_38_days"),
    ([42, 45, 44], date(2026, 6, 15), "pattern:cycle_outside_24_38_days"),
    ([25, 50, 26, 27], date(2026, 6, 1), "pattern:cycle_varies_over_20_days"),
    ([28, 28], date(2026, 6, 1), "pattern:no_period_90_days"),
])
def test_cycle_patterns_are_detected(builder, lengths, today, expected):
    assert expected in builder.detect_patterns(periods(lengths), today)


def test_long_period_is_detected(builder):
    assert "pattern:period_longer_than_8_days" in builder.detect_patterns(periods([28], period_days=10), date(2026, 2, 5))


def test_logged_red_flag_symptom_becomes_cited_alert(builder):
    logs = pd.DataFrame([
        {cd.USER_ID: "u1", cd.LOG_DATE: date(2026, 9, 20), cd.SYMPTOMS: ["fever_with_period_pain", "not_in_graph"]},
        {cd.USER_ID: "u1", cd.LOG_DATE: date(2026, 9, 21), cd.SYMPTOMS: ["fever_with_period_pain"]},
        {cd.USER_ID: "u1", cd.LOG_DATE: date(2026, 1, 1), cd.SYMPTOMS: ["pain_during_sex_or_toilet"]},  # too old
    ])
    g = builder.build("u1", EMPTY, EMPTY, logs, TODAY)
    assert [a.trigger for a in g.alerts] == ["symptom:fever_with_period_pain"]
    assert g.alerts[0].origin == "logged_recently"
    assert g.alerts[0].evidence[0].source == "https://medlineplus.gov/periodpain.html"
    logged = [e for e in g.edges if e.relation == "LOGGED"]
    assert len(logged) == 1 and logged[0].properties["times_logged"] == 2
    # the clinical WARRANTS edge is included so the graph explains the alert
    assert any(e.relation == "WARRANTS" and e.evidence for e in g.edges)


def test_zone_response_insight_needs_enough_sessions(builder):
    strong = builder.build("u1", sessions([("lower_back", 6)] * 3 + [("lower_abdomen", 2)] * 3), EMPTY, EMPTY, TODAY)
    [insight] = [i for i in strong.insights if i.kind == "best_zone"]
    assert insight.data["zone"] == "lower_back"
    assert "6.0 points" in insight.text
    weak = builder.build("u1", sessions([("lower_back", 6)] * 2 + [("lower_abdomen", 2)] * 3), EMPTY, EMPTY, TODAY)
    assert not [i for i in weak.insights if i.kind == "best_zone"]


def test_personal_graph_holds_no_copied_rows(builder):
    g = builder.build("u1", sessions([("lower_back", 4)] * 3), periods([28, 28]), EMPTY, date(2026, 3, 1))
    assert g.user_node == "user:u1"
    assert all(e.source == "user:u1" or e.evidence is not None for e in g.edges)
    assert {n.type for n in g.nodes} <= {"user", "body_zone", "symptom", "cycle_pattern", "care_level", "condition"}
    d = g.to_dict()
    assert set(d) == {"user_node", "nodes", "edges", "alerts", "insights"}
