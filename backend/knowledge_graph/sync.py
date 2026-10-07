"""Load the reviewed clinical graph JSON into Supabase.

Usage (reads DATABASE_URL):
  python -m knowledge_graph.sync
  python -m knowledge_graph.sync --json path/to/clinical_graph.json
"""

from __future__ import annotations

import argparse
import os

from knowledge_graph.graph import DEFAULT_GRAPH_PATH, KnowledgeGraph
from knowledge_graph.store import replace_graph_in_postgres


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default=str(DEFAULT_GRAPH_PATH))
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is not set")
    graph = KnowledgeGraph.load_json(args.json)  # validates nodes, edges and evidence first
    nodes, edges = replace_graph_in_postgres(dsn, graph)
    print(f"knowledge graph {graph.version}: wrote {nodes} nodes and {edges} edges")


if __name__ == "__main__":
    main()
