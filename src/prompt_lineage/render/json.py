"""lineage.json emitter -- the schema that locks in.

v0.1 shape: schema_version, generated_at, root_path, counts, prompts[],
suites[], contracts[], edges[]. Edges use {from, to, kind} (matching dbt's
lineage spec) instead of the Python-side src/dst. Breaking changes bump
the major. Adding optional fields does not.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from prompt_lineage import SCHEMA_VERSION
from prompt_lineage.model import Lineage


def to_dict(lineage: Lineage) -> dict[str, Any]:
    """Serialize a Lineage to a JSON-safe dict."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": lineage.generated_at,
        "root_path": lineage.root_path,
        "counts": lineage.counts(),
        "prompts": [_prompt_dict(p) for p in lineage.prompts],
        "suites": [asdict(s) for s in lineage.suites],
        "contracts": [asdict(c) for c in lineage.contracts],
        "edges": [
            {"from": e.src, "to": e.dst, "kind": e.kind}
            for e in lineage.edges
        ],
    }


def to_json(lineage: Lineage, *, indent: int = 2) -> str:
    """Serialize to a pretty-printed JSON string."""
    return json.dumps(to_dict(lineage), indent=indent, sort_keys=False)


def _prompt_dict(p) -> dict[str, Any]:
    """Manual serialization so `freshness=None` cleanly omits the key."""
    out: dict[str, Any] = {
        "id": p.id,
        "path": p.path,
        "last_modified": p.last_modified,
        "model_alias": p.model_alias,
        "evaluated_by": list(p.evaluated_by),
        "enforced_by": list(p.enforced_by),
    }
    if p.freshness is not None:
        out["freshness"] = asdict(p.freshness)
    return out
