"""Top-level scanner: walks a project directory and produces a Lineage.

Filesystem-only: no imports of user code, no network, no LLM calls.
Pipeline: discover prompts (manifest + suite references), parse suites,
AST-walk Python sources for @prompt_contract, attach freshness, build edges.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prompt_lineage.integrations.dbt_eval import (
    ParsedSuite, discover_suites, parse_suite,
)
from prompt_lineage.integrations.prompt_contracts import (
    ParsedContract, discover_python_sources, parse_source,
)
from prompt_lineage.integrations.prompt_freshness import (
    FreshnessEntry, FreshnessSnapshot, load_snapshot,
)
from prompt_lineage.model import (
    Contract, Edge, FreshnessInfo, Lineage, Prompt, Suite,
)


class ScanError(RuntimeError):
    """Raised when the scanner cannot read the root path at all."""


@dataclass
class ScanOptions:
    """Reserved for v0.2 (include_archived, prompt_glob, etc.). Keeping the
    dataclass in v0 freezes the public signature."""


def scan(root: str | Path, options: ScanOptions | None = None) -> Lineage:
    """Walk `root` and return a populated Lineage."""
    _ = options  # reserved
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise ScanError(f"scan root does not exist: {root_path}")
    if not root_path.is_dir():
        raise ScanError(f"scan root is not a directory: {root_path}")

    freshness = load_snapshot(root_path)
    suites = [parse_suite(p) for p in discover_suites(root_path)]
    py_files = discover_python_sources(root_path)
    raw_contracts: list[ParsedContract] = []
    for py in py_files:
        raw_contracts.extend(parse_source(py))

    # Discover prompts: union of (a) freshness-manifest-declared and
    # (b) suite-referenced. Keeps lineage honest when one tool is out of date.
    prompt_paths: set[str] = set()
    for entry in freshness.entries:
        prompt_paths.add(entry.path)
    for s in suites:
        for absolute in s.prompt_paths:
            prompt_paths.add(_rel_posix(root_path, absolute))

    # Build Prompt records.
    prompts: dict[str, Prompt] = {}
    freshness_by_path = {e.path: e for e in freshness.entries}
    for rel in sorted(prompt_paths):
        absolute = (root_path / rel).resolve()
        last_mod_iso: str | None = None
        if absolute.exists():
            ts = absolute.stat().st_mtime
            last_mod_iso = datetime.fromtimestamp(
                ts, tz=timezone.utc
            ).isoformat()
        f = freshness_by_path.get(rel)
        prompts[rel] = Prompt(
            id=rel,
            path=rel,
            last_modified=last_mod_iso,
            model_alias=f.model if f else None,
            freshness=_to_freshness_info(f) if f else None,
        )

    # Suite records (edges built below alongside contract edges).
    suite_records: list[Suite] = []
    for s in suites:
        sid = _rel_posix(root_path, s.path)
        covers = [_rel_posix(root_path, p) for p in s.prompt_paths]
        suite_records.append(
            Suite(
                id=sid, covers_prompts=covers,
                assertions=s.assertion_count, cases=s.case_count,
            )
        )

    # Contracts: infer wrapped prompt from body string literals (sorted-first).
    contract_records: list[Contract] = []
    for c in raw_contracts:
        cid_src = _rel_posix(root_path, c.source_path)
        cid = f"{cid_src}:{c.func_name}"
        wraps = _infer_wrapped_prompt(c, prompt_paths)
        contract_records.append(
            Contract(
                id=cid, source_path=cid_src, func_name=c.func_name,
                schema_ref=c.schema_ref, on_violation=c.on_violation,
                wraps_prompt=wraps,
            )
        )

    # Assemble Lineage + edges. Back-pointer lists (evaluated_by, enforced_by)
    # are populated here so renderers don't need to walk the edge list.
    lineage = Lineage(
        prompts=list(prompts.values()),
        suites=suite_records,
        contracts=contract_records,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        root_path=root_path.as_posix(),
    )

    for s in suite_records:
        for pid in s.covers_prompts:
            if pid in prompts:
                prompts[pid].evaluated_by.append(s.id)
                lineage.add_edge(pid, s.id, "evaluated_by")
                lineage.add_edge(s.id, pid, "covers")

    for c in contract_records:
        if c.wraps_prompt and c.wraps_prompt in prompts:
            prompts[c.wraps_prompt].enforced_by.append(c.id)
            lineage.add_edge(c.wraps_prompt, c.id, "enforced_by")
            lineage.add_edge(c.id, c.wraps_prompt, "wraps")

    # Dedup back-pointer lists (a suite can mention the same prompt twice).
    for p in lineage.prompts:
        p.evaluated_by = sorted(set(p.evaluated_by))
        p.enforced_by = sorted(set(p.enforced_by))

    return lineage


def _to_freshness_info(entry: FreshnessEntry) -> FreshnessInfo:
    return FreshnessInfo(
        warn_after=entry.warn_after,
        error_after=entry.error_after,
        last_evaluated=entry.last_evaluated_iso,
        status=entry.status,
    )


def _rel_posix(root: Path, absolute: Path) -> str:
    try:
        return absolute.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # File lives outside the scan root -- preserve absolute as a stable key.
        return absolute.resolve().as_posix()


def _infer_wrapped_prompt(
    contract: ParsedContract, prompt_paths: set[str]
) -> str | None:
    """Best-effort: explicit prompt kwarg > body string literal match."""
    if contract.explicit_prompt:
        return contract.explicit_prompt
    matches = sorted(
        p for p in prompt_paths
        if any(s.endswith(p) or p in s for s in contract.body_strings)
    )
    return matches[0] if matches else None


__all__ = ["scan", "ScanError", "ScanOptions"]
_ = (ParsedSuite, FreshnessSnapshot, Edge)  # public surface area markers
