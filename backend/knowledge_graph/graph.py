"""In-memory knowledge graph: typed nodes and evidence-backed relations.

The same structure holds the shared clinical graph (loaded from Postgres or the
bundled JSON) and a user's personal subgraph (built on request).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_GRAPH_PATH = Path(__file__).with_name("clinical_graph.json")

NODE_TYPES = frozenset(
    {"symptom", "condition", "therapy", "care_level", "cycle_phase", "body_zone", "cycle_pattern", "user"}
)


class GraphError(ValueError):
    pass


@dataclass(frozen=True)
class Evidence:
    source: str  # URL of the knowledge document
    quote: str  # exact sentence from it
    title: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "title": self.title, "quote": self.quote}


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "label": self.label, "properties": self.properties}


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    evidence: Evidence | None = None  # None only for personal (user-data) edges

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "properties": self.properties,
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }


class KnowledgeGraph:
    def __init__(
        self,
        nodes: Iterable[Node],
        edges: Iterable[Edge],
        sources: dict[str, dict[str, str]] | None = None,
        version: str = "unknown",
    ) -> None:
        self.nodes: dict[str, Node] = {}
        for node in nodes:
            if node.id in self.nodes:
                raise GraphError(f"duplicate node {node.id}")
            if node.type not in NODE_TYPES:
                raise GraphError(f"node {node.id} has unknown type {node.type}")
            self.nodes[node.id] = node
        self.sources = sources or {}
        self.version = version
        self.edges: list[Edge] = []
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        for edge in edges:
            self.add_edge(edge)

    def add_edge(self, edge: Edge) -> None:
        for end in (edge.source, edge.target):
            if end not in self.nodes:
                raise GraphError(f"edge {edge.source} -{edge.relation}-> {edge.target}: unknown node {end}")
        self.edges.append(edge)
        self._out[edge.source].append(edge)
        self._in[edge.target].append(edge)

    def node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def out_edges(self, node_id: str, relation: str | None = None) -> list[Edge]:
        return [e for e in self._out.get(node_id, []) if relation is None or e.relation == relation]

    def in_edges(self, node_id: str, relation: str | None = None) -> list[Edge]:
        return [e for e in self._in.get(node_id, []) if relation is None or e.relation == relation]

    def nodes_of_type(self, node_type: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def evidence(self, source: str, quote: str) -> Evidence:
        return Evidence(source=source, quote=quote, title=self.sources.get(source, {}).get("title", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeGraph":
        sources = data.get("sources", {})
        nodes = [Node(n["id"], n["type"], n["label"], n.get("properties", {})) for n in data["nodes"]]
        edges = []
        for e in data["edges"]:
            ev = e.get("evidence")
            if not ev or not ev.get("source") or not ev.get("quote"):
                raise GraphError(f"clinical edge {e['source']} -{e['relation']}-> {e['target']} has no evidence")
            edges.append(
                Edge(
                    e["source"], e["relation"], e["target"], e.get("properties", {}),
                    Evidence(ev["source"], ev["quote"], sources.get(ev["source"], {}).get("title", "")),
                )
            )
        return cls(nodes, edges, sources, data.get("version", "unknown"))

    @classmethod
    def load_json(cls, path: str | Path = DEFAULT_GRAPH_PATH) -> "KnowledgeGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
