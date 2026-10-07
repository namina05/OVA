"""Clinical reasoning over the knowledge graph.

Turns symptoms and cycle patterns into health alerts by walking WARRANTS
relations to a care level, either directly or through one intermediate node
(e.g. pattern -IS_SIGN_OF-> irregular periods -WARRANTS-> see a doctor).
Every alert carries the exact source sentences of the edges it walked, so the
app can show where the advice comes from. Nothing here is generated text
about health beyond the care-level advice stored in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from knowledge_graph.graph import Edge, Evidence, KnowledgeGraph, Node

WARRANTS = "WARRANTS"
BRIDGE_RELATIONS = ("IS_SIGN_OF", "CAUSES")
SYMPTOM_PREFIX = "symptom:"


class UnknownSymptomError(ValueError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f"unknown symptoms: {unknown}")
        self.unknown = unknown


@dataclass(frozen=True)
class HealthAlert:
    trigger: str
    trigger_label: str
    care_level: str  # emergency | urgent | see_doctor
    severity: int  # 3 emergency, 2 urgent, 1 see a doctor
    advice: str
    origin: str  # reported_now | logged_recently | cycle_pattern
    path: tuple[str, ...]
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "trigger_label": self.trigger_label,
            "care_level": self.care_level,
            "severity": self.severity,
            "advice": self.advice,
            "origin": self.origin,
            "path": list(self.path),
            "evidence": [e.to_dict() for e in self.evidence],
        }


class ClinicalAdvisor:
    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    # -- vocabulary ---------------------------------------------------------

    def symptom_keys(self) -> list[str]:
        """Keys the app may send or store in daily_logs.symptoms (e.g. 'fever_with_period_pain')."""
        return sorted(n.id.removeprefix(SYMPTOM_PREFIX) for n in self.graph.nodes_of_type("symptom"))

    def symptom_node_ids(self, keys: Iterable[str]) -> list[str]:
        ids = [f"{SYMPTOM_PREFIX}{k}" for k in keys]
        unknown = [i.removeprefix(SYMPTOM_PREFIX) for i in ids if i not in self.graph.nodes]
        if unknown:
            raise UnknownSymptomError(unknown)
        return ids

    # -- alerts -------------------------------------------------------------

    def _care(self, edge: Edge) -> Node | None:
        node = self.graph.node(edge.target)
        return node if node is not None and node.type == "care_level" else None

    def _paths_to_care(self, start: str) -> list[tuple[list[Edge], Node]]:
        paths: list[tuple[list[Edge], Node]] = []
        for edge in self.graph.out_edges(start, WARRANTS):
            if care := self._care(edge):
                paths.append(([edge], care))
        for relation in BRIDGE_RELATIONS:
            for bridge in self.graph.out_edges(start, relation):
                for edge in self.graph.out_edges(bridge.target, WARRANTS):
                    if care := self._care(edge):
                        paths.append(([bridge, edge], care))
        return paths

    def alerts_for(self, node_ids: Iterable[str], origin: str) -> list[HealthAlert]:
        """The most serious care level reachable from each node, with its evidence."""
        alerts: list[HealthAlert] = []
        for node_id in dict.fromkeys(node_ids):
            node = self.graph.node(node_id)
            paths = self._paths_to_care(node_id) if node else []
            if not paths:
                continue
            edges, care = max(paths, key=lambda p: (p[1].properties.get("severity", 0), -len(p[0])))
            alerts.append(
                HealthAlert(
                    trigger=node_id,
                    trigger_label=node.label,
                    care_level=care.id.split(":", 1)[1],
                    severity=int(care.properties.get("severity", 1)),
                    advice=str(care.properties.get("advice", care.label)),
                    origin=origin,
                    path=(node_id, *(e.target for e in edges)),
                    evidence=tuple(e.evidence for e in edges if e.evidence),
                )
            )
        return sorted(alerts, key=lambda a: -a.severity)

    # -- therapy evidence -----------------------------------------------------

    def heat_evidence(self, zone: str) -> list[Evidence]:
        """Sources supporting heat therapy, and heat on this zone, for the explanation."""
        zone_id = f"zone:{zone}"
        evidence = [e.evidence for e in self.graph.out_edges("therapy:heat", "RELIEVES") if e.evidence]
        evidence += [
            e.evidence for e in self.graph.out_edges("therapy:heat", "APPLIED_TO")
            if e.target == zone_id and e.evidence
        ]
        evidence += [
            e.evidence for e in self.graph.in_edges(zone_id)
            if e.relation in ("LOCATED_IN", "SPREADS_TO") and e.evidence
            and self.graph.nodes[e.source].type == "symptom"
        ]
        return list(dict.fromkeys(evidence))

    def heat_cautions(self) -> list[Evidence]:
        return [e.evidence for e in self.graph.out_edges("therapy:heat", "HAS_REPORTED_ADVERSE_EFFECT") if e.evidence]


def merge_alerts(*groups: list[HealthAlert]) -> list[HealthAlert]:
    """One alert per trigger (the most serious), most serious first."""
    best: dict[str, HealthAlert] = {}
    for alert in (a for group in groups for a in group):
        if alert.trigger not in best or alert.severity > best[alert.trigger].severity:
            best[alert.trigger] = alert
    return sorted(best.values(), key=lambda a: -a.severity)
