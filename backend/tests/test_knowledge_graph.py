import os
import re
from pathlib import Path

import pytest

from knowledge_graph.advisor import ClinicalAdvisor, UnknownSymptomError
from knowledge_graph.graph import Edge, GraphError, KnowledgeGraph, Node

# The vetted documents live in supabase/knowledge (from the chatbot work).
# OVA_KNOWLEDGE_DIR can point elsewhere; the citation test is skipped if they are absent.
KNOWLEDGE_DIR = Path(
    os.environ.get("OVA_KNOWLEDGE_DIR", Path(__file__).resolve().parents[2] / "supabase" / "knowledge")
)


@pytest.fixture(scope="module")
def graph() -> KnowledgeGraph:
    return KnowledgeGraph.load_json()


@pytest.fixture(scope="module")
def advisor(graph) -> ClinicalAdvisor:
    return ClinicalAdvisor(graph)


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def test_every_clinical_edge_cites_a_known_source(graph):
    assert graph.edges
    for edge in graph.edges:
        assert edge.evidence is not None
        assert edge.evidence.source in graph.sources, edge
        assert edge.evidence.title


@pytest.mark.skipif(not KNOWLEDGE_DIR.is_dir(), reason="knowledge documents not available")
def test_every_quote_appears_verbatim_in_its_document(graph):
    for edge in graph.edges:
        document = KNOWLEDGE_DIR / graph.sources[edge.evidence.source]["file"]
        assert _normalize(edge.evidence.quote) in _normalize(document.read_text(encoding="utf-8")), (
            f"quote for {edge.source} -{edge.relation}-> {edge.target} not found in {document.name}"
        )


def test_every_red_flag_leads_to_care(graph, advisor):
    red_flags = [n.id for n in graph.nodes_of_type("symptom") if n.properties.get("red_flag")]
    patterns = [n.id for n in graph.nodes_of_type("cycle_pattern")]
    alerts = advisor.alerts_for(red_flags + patterns, origin="test")
    assert {a.trigger for a in alerts} == set(red_flags + patterns)


def test_graph_rejects_dangling_edges_and_missing_evidence():
    with pytest.raises(GraphError):
        KnowledgeGraph([Node("symptom:a", "symptom", "A")], [Edge("symptom:a", "X", "symptom:b")])
    with pytest.raises(GraphError):
        KnowledgeGraph.from_dict({
            "nodes": [{"id": "symptom:a", "type": "symptom", "label": "A"},
                      {"id": "care:see_doctor", "type": "care_level", "label": "C"}],
            "edges": [{"source": "symptom:a", "relation": "WARRANTS", "target": "care:see_doctor"}],
        })


def test_emergency_outranks_other_alerts(advisor):
    alerts = advisor.alerts_for(
        advisor.symptom_node_ids(["fever_with_period_pain", "tss_symptoms", "severe_pain_painkillers_not_helping"]),
        origin="reported_now",
    )
    assert [a.care_level for a in alerts] == ["emergency", "urgent", "see_doctor"]
    assert "call 911" in alerts[0].evidence[0].quote


def test_two_hop_alert_carries_both_citations(advisor):
    [alert] = advisor.alerts_for(["pattern:cycle_varies_over_20_days"], origin="cycle_pattern")
    assert alert.path == ("pattern:cycle_varies_over_20_days", "condition:irregular_periods", "care:see_doctor")
    assert len(alert.evidence) == 2


def test_ordinary_symptom_gives_no_alert(advisor):
    assert advisor.alerts_for(advisor.symptom_node_ids(["menstrual_cramps"]), origin="reported_now") == []


def test_unknown_symptoms_are_reported(advisor):
    with pytest.raises(UnknownSymptomError) as exc:
        advisor.symptom_node_ids(["menstrual_cramps", "made_up"])
    assert exc.value.unknown == ["made_up"]


def test_heat_evidence_depends_on_zone(advisor):
    abdomen = advisor.heat_evidence("lower_abdomen")
    back = advisor.heat_evidence("lower_back")
    assert any("lower abdomen" in e.quote for e in abdomen)
    assert any("spread to your back" in e.quote for e in back)
    assert not any("spread to your back" in e.quote for e in abdomen)
    assert advisor.heat_cautions()
