"""Graph traversal utilities. v0 exposes the adjacency primitives an
external visualizer (or our own v0.2 force-graph) would need. The v0
*view* is the sortable table -- the graph view is deferred to v0.2.
Schema stays stable; the view changes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from prompt_lineage.model import EdgeKind, Lineage


@dataclass
class Adjacency:
    """Pre-built adjacency lists keyed by node id."""

    outgoing: dict[str, list[tuple[str, EdgeKind]]]
    incoming: dict[str, list[tuple[str, EdgeKind]]]

    def neighbors(self, node_id: str) -> list[str]:
        """All directly connected node ids, regardless of edge direction."""
        seen: set[str] = set()
        out: list[str] = []
        for dst, _ in self.outgoing.get(node_id, []):
            if dst not in seen:
                seen.add(dst)
                out.append(dst)
        for src, _ in self.incoming.get(node_id, []):
            if src not in seen:
                seen.add(src)
                out.append(src)
        return out


def build_adjacency(lineage: Lineage) -> Adjacency:
    """Walk the edge list once, produce out/in adjacency maps."""
    outgoing: dict[str, list[tuple[str, EdgeKind]]] = defaultdict(list)
    incoming: dict[str, list[tuple[str, EdgeKind]]] = defaultdict(list)
    for e in lineage.edges:
        outgoing[e.src].append((e.dst, e.kind))
        incoming[e.dst].append((e.src, e.kind))
    return Adjacency(outgoing=dict(outgoing), incoming=dict(incoming))


def orphan_prompts(lineage: Lineage) -> list[str]:
    """Prompts with neither eval nor contract -- the highest-risk rows."""
    return [
        p.id for p in lineage.prompts
        if not p.evaluated_by and not p.enforced_by
    ]


def uncovered_prompts(lineage: Lineage) -> list[str]:
    """Prompts with no eval suite. May still be enforced by a contract."""
    return [p.id for p in lineage.prompts if not p.evaluated_by]


def unenforced_prompts(lineage: Lineage) -> list[str]:
    """Prompts with no contract. May still be evaluated."""
    return [p.id for p in lineage.prompts if not p.enforced_by]
