"""Postgres storage for the clinical graph (tables kg_nodes and kg_edges)."""

from __future__ import annotations

import json
import logging

from knowledge_graph.graph import Edge, Evidence, KnowledgeGraph, Node

logger = logging.getLogger(__name__)


class GraphStoreError(RuntimeError):
    pass


def load_graph_from_postgres(dsn: str, fallback_sources: dict[str, dict[str, str]] | None = None) -> KnowledgeGraph:
    """Load the clinical graph. Source titles come from knowledge_documents when ingested."""
    import psycopg

    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("select id, type, label, properties from public.kg_nodes")
            node_rows = cur.fetchall()
            cur.execute(
                "select source_id, relation, target_id, properties, evidence_source, evidence_quote "
                "from public.kg_edges order by id"
            )
            edge_rows = cur.fetchall()
            cur.execute("select source, title from public.knowledge_documents")
            titles = dict(cur.fetchall())
    except psycopg.Error as exc:
        raise GraphStoreError("could not read the knowledge graph") from exc
    if not node_rows:
        raise GraphStoreError("the knowledge graph tables are empty; run `python -m knowledge_graph.sync`")

    sources = {url: dict(meta) for url, meta in (fallback_sources or {}).items()}
    for url, title in titles.items():
        sources.setdefault(url, {})["title"] = title
    nodes = [Node(i, t, label, props or {}) for i, t, label, props in node_rows]
    edges = [
        Edge(s, r, t, props or {}, Evidence(src, quote, sources.get(src, {}).get("title", "")))
        for s, r, t, props, src, quote in edge_rows
    ]
    return KnowledgeGraph(nodes, edges, sources, version="postgres")


def replace_graph_in_postgres(dsn: str, graph: KnowledgeGraph) -> tuple[int, int]:
    """Replace the stored clinical graph with `graph` in one transaction."""
    import psycopg

    if any(e.evidence is None for e in graph.edges):
        raise GraphStoreError("every clinical edge needs evidence")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("delete from public.kg_edges")
            cur.execute("delete from public.kg_nodes")
            cur.executemany(
                "insert into public.kg_nodes (id, type, label, properties) values (%s, %s, %s, %s::jsonb)",
                [(n.id, n.type, n.label, json.dumps(n.properties)) for n in graph.nodes.values()],
            )
            cur.executemany(
                "insert into public.kg_edges (source_id, relation, target_id, properties, evidence_source, "
                "evidence_quote) values (%s, %s, %s, %s::jsonb, %s, %s)",
                [
                    (e.source, e.relation, e.target, json.dumps(e.properties), e.evidence.source, e.evidence.quote)
                    for e in graph.edges
                ],
            )
    except psycopg.Error as exc:
        raise GraphStoreError("could not write the knowledge graph") from exc
    return len(graph.nodes), len(graph.edges)
