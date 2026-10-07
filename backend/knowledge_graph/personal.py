"""A user's personal knowledge graph, linked into the clinical graph.

Built on request from the user's own rows (therapy sessions, periods, daily
logs) and never stored, so no user data is duplicated. Edges:

  user -LOGGED-> symptom           symptoms from daily_logs in the look-back window
  user -HAS_PATTERN-> pattern      cycle patterns detected from logged periods
  user -RESPONDS_TO-> zone         average pain reduction from therapy sessions

Symptom and pattern nodes are the clinical graph's nodes, so the clinical
WARRANTS paths from them become the user's health alerts. Pattern thresholds
are read from the clinical nodes' properties, not hard-coded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from knowledge_graph.advisor import SYMPTOM_PREFIX, ClinicalAdvisor, HealthAlert
from knowledge_graph.graph import Edge, KnowledgeGraph, Node
from ml import schema
from ml.cycle import data as cd
from ml.preprocessing.cleaning import clean_sessions

MISSED_LOG_NOTE = "Based on the period starts you logged; a missed or late log can also cause this."


@dataclass(frozen=True)
class Insight:
    kind: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "data": self.data}


@dataclass
class PersonalGraph:
    user_node: str
    nodes: list[Node]
    edges: list[Edge]
    alerts: list[HealthAlert]
    insights: list[Insight]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_node": self.user_node,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "alerts": [a.to_dict() for a in self.alerts],
            "insights": [i.to_dict() for i in self.insights],
        }


class PersonalGraphBuilder:
    def __init__(
        self,
        graph: KnowledgeGraph,
        symptom_lookback_days: int = 90,
        min_zone_sessions: int = 3,
    ) -> None:
        self.graph = graph
        self.advisor = ClinicalAdvisor(graph)
        self.symptom_lookback_days = symptom_lookback_days
        self.min_zone_sessions = min_zone_sessions

    def _prop(self, node_id: str, key: str) -> float | None:
        node = self.graph.node(node_id)
        return None if node is None else node.properties.get(key)

    # -- cycle patterns -------------------------------------------------------

    def detect_patterns(self, periods: pd.DataFrame, today: date) -> dict[str, dict[str, Any]]:
        """Pattern node id -> the values that triggered it."""
        if periods.empty:
            return {}
        periods = cd.clean_periods(periods)
        cycles = cd.UserCycles.from_periods(periods)
        found: dict[str, dict[str, Any]] = {}

        recent = cycles.raw_cycle_lengths[-3:]
        low = self._prop("pattern:cycle_outside_24_38_days", "min_days")
        high = self._prop("pattern:cycle_outside_24_38_days", "max_days")
        if len(recent) >= 2 and low is not None and high is not None:
            median = float(np.median(recent))
            if not low <= median <= high:
                found["pattern:cycle_outside_24_38_days"] = {"recent_cycle_lengths": recent, "note": MISSED_LOG_NOTE}

        plausible = [c for c in cycles.cycle_lengths[-6:] if c is not None]
        max_variation = self._prop("pattern:cycle_varies_over_20_days", "max_variation_days")
        if len(plausible) >= 3 and max_variation is not None and max(plausible) - min(plausible) > max_variation:
            found["pattern:cycle_varies_over_20_days"] = {"recent_cycle_lengths": plausible, "note": MISSED_LOG_NOTE}

        max_period = self._prop("pattern:period_longer_than_8_days", "max_days")
        ended = periods[periods[cd.END].notna()].tail(3)
        long_periods = [
            (e - s).days + 1 for s, e in zip(ended[cd.START], ended[cd.END]) if (e - s).days + 1 > (max_period or 99)
        ]
        if long_periods:
            found["pattern:period_longer_than_8_days"] = {"period_lengths": long_periods}

        no_period_days = self._prop("pattern:no_period_90_days", "days")
        since_last = (today - cycles.starts[-1]).days
        if no_period_days is not None and since_last > no_period_days:
            found["pattern:no_period_90_days"] = {"days_since_last_period": since_last, "note": MISSED_LOG_NOTE}
        return found

    # -- symptoms -------------------------------------------------------------

    def logged_symptoms(self, daily_logs: pd.DataFrame, today: date) -> dict[str, dict[str, Any]]:
        if daily_logs.empty:
            return {}
        logs = cd.clean_daily_logs(daily_logs)
        since = today - timedelta(days=self.symptom_lookback_days)
        logs = logs[(logs[cd.LOG_DATE] >= since) & (logs[cd.LOG_DATE] <= today)]
        found: dict[str, dict[str, Any]] = {}
        for log_date, symptoms in zip(logs[cd.LOG_DATE], logs[cd.SYMPTOMS]):
            for key in symptoms:
                node_id = f"{SYMPTOM_PREFIX}{key}"
                if node_id not in self.graph.nodes:
                    continue  # free text the graph doesn't know is not interpreted
                entry = found.setdefault(node_id, {"times_logged": 0, "last_logged": log_date})
                entry["times_logged"] += 1
                entry["last_logged"] = max(entry["last_logged"], log_date)
        for entry in found.values():
            entry["last_logged"] = entry["last_logged"].isoformat()
        return found

    # -- therapy response -----------------------------------------------------

    def zone_response(self, sessions: pd.DataFrame) -> dict[str, dict[str, Any]]:
        if sessions.empty:
            return {}
        clean = clean_sessions(sessions)
        stats = clean.groupby(schema.ZONE)[schema.PAIN_REDUCTION].agg(["count", "mean"])
        return {
            zone: {"sessions": int(row["count"]), "mean_pain_reduction": round(float(row["mean"]), 2)}
            for zone, row in stats.iterrows()
        }

    def _zone_insight(self, zones: dict[str, dict[str, Any]]) -> Insight | None:
        enough = sorted(
            ((z, s) for z, s in zones.items() if s["sessions"] >= self.min_zone_sessions),
            key=lambda zs: -zs[1]["mean_pain_reduction"],
        )
        if len(enough) < 2:
            return None
        (best, b), (second, s) = enough[0], enough[1]
        if b["mean_pain_reduction"] - s["mean_pain_reduction"] < 0.5:
            return None
        return Insight(
            "best_zone",
            f"Your sessions on the {best.replace('_', ' ')} averaged {b['mean_pain_reduction']:.1f} points of pain "
            f"relief over {b['sessions']} sessions, more than the {second.replace('_', ' ')} "
            f"({s['mean_pain_reduction']:.1f} over {s['sessions']}).",
            {"zone": best, **b},
        )

    # -- assembly -------------------------------------------------------------

    def build(
        self,
        user_id: str,
        sessions: pd.DataFrame,
        periods: pd.DataFrame,
        daily_logs: pd.DataFrame,
        today: date,
    ) -> PersonalGraph:
        user_node = Node(f"user:{user_id}", "user", "You")
        nodes: dict[str, Node] = {user_node.id: user_node}
        edges: list[Edge] = []

        def link(relation: str, target: Node, props: dict[str, Any]) -> None:
            nodes[target.id] = target
            edges.append(Edge(user_node.id, relation, target.id, props))

        symptoms = self.logged_symptoms(daily_logs, today)
        for node_id, props in symptoms.items():
            link("LOGGED", self.graph.nodes[node_id], props)

        patterns = self.detect_patterns(periods, today)
        for node_id, props in patterns.items():
            link("HAS_PATTERN", self.graph.nodes[node_id], props)

        zones = self.zone_response(sessions)
        for zone, props in zones.items():
            node = self.graph.node(f"zone:{zone}") or Node(f"zone:{zone}", "body_zone", zone.replace("_", " ").capitalize())
            link("RESPONDS_TO", node, props)

        alerts = (
            self.advisor.alerts_for(symptoms, origin="logged_recently")
            + self.advisor.alerts_for(patterns, origin="cycle_pattern")
        )
        alerts.sort(key=lambda a: -a.severity)
        # Include the clinical nodes and edges each alert walked, so the graph explains itself.
        for alert in alerts:
            for a, b in zip(alert.path, alert.path[1:]):
                nodes.setdefault(b, self.graph.nodes[b])
                edges.extend(e for e in self.graph.out_edges(a) if e.target == b and e not in edges)

        insights = [i for i in [self._zone_insight(zones)] if i]
        if not periods.empty and not patterns:
            insights.append(Insight("cycle_patterns", "No unusual cycle patterns were found in the periods you logged."))
        return PersonalGraph(user_node.id, list(nodes.values()), edges, alerts, insights)
