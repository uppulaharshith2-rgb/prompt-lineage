"""Lineage data model: Prompt, Suite, Contract nodes + Edge. Dataclasses, not
Pydantic, because the JSON contract is what adopters lock in on -- not the
in-memory class shape."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

EdgeKind = Literal["evaluated_by", "enforced_by", "covers", "wraps"]


@dataclass
class FreshnessInfo:
    """Subset of prompt-freshness state surfaced in lineage."""
    warn_after: Optional[str] = None
    error_after: Optional[str] = None
    last_evaluated: Optional[str] = None
    status: Optional[str] = None  # fresh|warning|stale|unevaluated


@dataclass
class Prompt:
    """One prompt template. `id == path` today; separated for a future
    registry-fetched prompt world."""
    id: str
    path: str
    last_modified: Optional[str] = None
    model_alias: Optional[str] = None
    evaluated_by: list[str] = field(default_factory=list)
    enforced_by: list[str] = field(default_factory=list)
    freshness: Optional[FreshnessInfo] = None


@dataclass
class Suite:
    """A dbt-eval-shape YAML suite."""
    id: str
    covers_prompts: list[str] = field(default_factory=list)
    assertions: int = 0
    cases: int = 0


@dataclass
class Contract:
    """One @prompt_contract usage. `id` is `<path>:<func>`."""
    id: str
    source_path: str
    func_name: str
    schema_ref: Optional[str] = None
    on_violation: Optional[str] = None
    wraps_prompt: Optional[str] = None  # heuristically inferred


@dataclass
class Edge:
    """Directed link. `kind` is one of EdgeKind."""
    src: str
    dst: str
    kind: EdgeKind


@dataclass
class Lineage:
    """Root container the JSON + HTML renderers consume."""
    prompts: list[Prompt] = field(default_factory=list)
    suites: list[Suite] = field(default_factory=list)
    contracts: list[Contract] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    generated_at: Optional[str] = None
    root_path: Optional[str] = None

    def prompt_by_id(self, pid: str) -> Optional[Prompt]:
        return next((p for p in self.prompts if p.id == pid), None)

    def suite_by_id(self, sid: str) -> Optional[Suite]:
        return next((s for s in self.suites if s.id == sid), None)

    def contract_by_id(self, cid: str) -> Optional[Contract]:
        return next((c for c in self.contracts if c.id == cid), None)

    def add_edge(self, src: str, dst: str, kind: EdgeKind) -> None:
        # Dedup: same edge can come from multiple sources.
        if any(e.src == src and e.dst == dst and e.kind == kind for e in self.edges):
            return
        self.edges.append(Edge(src=src, dst=dst, kind=kind))

    def counts(self) -> dict[str, int]:
        return {
            "prompts": len(self.prompts),
            "suites": len(self.suites),
            "contracts": len(self.contracts),
            "edges": len(self.edges),
            "uncovered_prompts": sum(1 for p in self.prompts if not p.evaluated_by),
            "unenforced_prompts": sum(1 for p in self.prompts if not p.enforced_by),
        }
