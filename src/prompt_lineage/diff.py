"""Lineage diff: compare two Lineage snapshots and report changes.

Structural-only: we report changes to the (model, eval suites, contracts,
freshness status) tuple per prompt, plus suite + contract add/remove. We
do NOT diff the markdown text of a prompt -- that's what `git diff` is for.

Deferred to v0.2: per-case suite changes, per-assertion changes, sub-threshold
freshness drift.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from prompt_lineage.model import Contract, Lineage, Prompt, Suite
from prompt_lineage.render.json import to_dict


@dataclass
class _Change:
    """Base: added | removed | modified entry."""
    id: str
    kind: str
    field_changes: dict[str, tuple] = field(default_factory=dict)


@dataclass
class PromptChange(_Change): pass  # noqa: E701
@dataclass
class SuiteChange(_Change): pass  # noqa: E701
@dataclass
class ContractChange(_Change): pass  # noqa: E701


@dataclass
class DiffReport:
    """Top-level diff result. `as_terminal()`, `as_markdown()`, `as_dict()`."""

    prompt_changes: list[PromptChange] = field(default_factory=list)
    suite_changes: list[SuiteChange] = field(default_factory=list)
    contract_changes: list[ContractChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.prompt_changes) + len(self.suite_changes) + len(self.contract_changes)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0

    def _all_changes(self) -> list:
        return self.prompt_changes + self.suite_changes + self.contract_changes

    def as_dict(self) -> dict:
        return {
            "prompts": [asdict(p) for p in self.prompt_changes],
            "suites": [asdict(s) for s in self.suite_changes],
            "contracts": [asdict(c) for c in self.contract_changes],
            "total_changes": self.total_changes,
        }

    def as_markdown(self) -> str:
        if not self.has_changes:
            return "_no lineage changes_\n"
        lines = ["## prompt-lineage diff", ""]
        for items, label in (
            (self.prompt_changes, "prompt"),
            (self.suite_changes, "suite"),
            (self.contract_changes, "contract"),
        ):
            if not items:
                continue
            lines.append(f"### {label}s")
            for item in items:
                lines.append(f"- `{item.id}` {_format_change(item)}")
            lines.append("")
        lines.append(
            f"_{self.total_changes} change(s) total: "
            f"{_count_kinds(self._all_changes())}_"
        )
        return "\n".join(lines) + "\n"

    def as_terminal(self) -> str:
        if not self.has_changes:
            return "no lineage changes between the two scans\n"
        out: list[str] = ["", "prompt-lineage diff", ""]
        for changes, label in (
            (self.prompt_changes, "prompt"),
            (self.suite_changes, "suite"),
            (self.contract_changes, "contract"),
        ):
            for c in changes:
                out.append(f"  {label:10s} [{c.kind:8s}] {c.id}")
                for fname, (before, after) in (c.field_changes or {}).items():
                    out.append(
                        f"             {fname}: {_short(before)} -> {_short(after)}"
                    )
        out.append("")
        out.append(
            f"{self.total_changes} change(s) -- {_count_kinds(self._all_changes())}"
        )
        out.append("")
        return "\n".join(out)


def diff_lineages(before: Lineage, after: Lineage) -> DiffReport:
    """The core diff. Order-independent, deterministic."""
    return DiffReport(
        prompt_changes=_diff_collection(
            before.prompts, after.prompts, PromptChange, _compare_prompt,
        ),
        suite_changes=_diff_collection(
            before.suites, after.suites, SuiteChange, _compare_suite,
        ),
        contract_changes=_diff_collection(
            before.contracts, after.contracts, ContractChange, _compare_contract,
        ),
    )


def _diff_collection(before, after, change_cls, compare_fn) -> list:
    """Shared add/remove/modify scan over a list of nodes keyed by `.id`."""
    b = {x.id: x for x in before}
    a = {x.id: x for x in after}
    out: list = []
    for k in sorted(set(a) - set(b)):
        out.append(change_cls(id=k, kind="added"))
    for k in sorted(set(b) - set(a)):
        out.append(change_cls(id=k, kind="removed"))
    for k in sorted(set(a) & set(b)):
        changes = compare_fn(b[k], a[k])
        if changes:
            out.append(change_cls(id=k, kind="modified", field_changes=changes))
    return out


def _compare_prompt(before: Prompt, after: Prompt) -> dict:
    changes: dict = {}
    if before.model_alias != after.model_alias:
        changes["model"] = (before.model_alias, after.model_alias)
    if sorted(before.evaluated_by) != sorted(after.evaluated_by):
        changes["eval suites"] = (
            sorted(before.evaluated_by), sorted(after.evaluated_by),
        )
    if sorted(before.enforced_by) != sorted(after.enforced_by):
        changes["contracts"] = (
            sorted(before.enforced_by), sorted(after.enforced_by),
        )
    bf = before.freshness.status if before.freshness else None
    af = after.freshness.status if after.freshness else None
    if bf != af:
        changes["freshness"] = (bf, af)
    return changes


def _compare_suite(before: Suite, after: Suite) -> dict:
    changes: dict = {}
    if sorted(before.covers_prompts) != sorted(after.covers_prompts):
        changes["covers"] = (
            sorted(before.covers_prompts), sorted(after.covers_prompts),
        )
    if before.cases != after.cases:
        changes["cases"] = (before.cases, after.cases)
    if before.assertions != after.assertions:
        changes["assertions"] = (before.assertions, after.assertions)
    return changes


def _compare_contract(before: Contract, after: Contract) -> dict:
    changes: dict = {}
    if before.wraps_prompt != after.wraps_prompt:
        changes["wraps_prompt"] = (before.wraps_prompt, after.wraps_prompt)
    if before.on_violation != after.on_violation:
        changes["on_violation"] = (before.on_violation, after.on_violation)
    return changes


# ---- git ref helpers used by the `diff main..HEAD` CLI form ----


class GitDiffError(RuntimeError):
    """Raised when we can't materialize one of the git refs."""


def lineage_at_ref(
    repo_root: str | Path, ref: str, sub_path: str = "."
) -> Lineage:
    """Scan a git ref by checking it out into a temp git worktree.

    `git worktree add` (not `checkout`) keeps the user's working tree
    untouched -- critical for CI where two refs are scanned back-to-back."""
    from prompt_lineage.scanner import scan

    repo = Path(repo_root).expanduser().resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise GitDiffError(f"{repo} is not a git repo")

    with tempfile.TemporaryDirectory(prefix="prompt-lineage-diff-") as tmp:
        tmp_path = Path(tmp) / "wt"
        try:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach",
                 str(tmp_path), ref],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise GitDiffError(
                f"git worktree add failed for {ref}: {exc.stderr.strip()}"
            ) from exc
        try:
            return scan(tmp_path / sub_path)
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force",
                 str(tmp_path)],
                capture_output=True, text=True,
            )


def parse_ref_pair(arg: str) -> tuple[str, str]:
    """'A..B' or 'A...B' (treated as ..). Returns (base, head)."""
    sep = "..." if "..." in arg else (".." if ".." in arg else None)
    if sep is None:
        raise ValueError(f"ref pair must look like 'main..HEAD', got: {arg!r}")
    base, head = arg.split(sep, 1)
    if not base or not head:
        raise ValueError(f"both sides of ref pair must be set: {arg!r}")
    return base, head


def _short(v) -> str:
    if isinstance(v, list):
        if not v:
            return "[]"
        if len(v) > 3:
            return f"[{', '.join(v[:3])}, ...{len(v) - 3} more]"
        return "[" + ", ".join(v) + "]"
    return "-" if v is None else str(v)


def _count_kinds(items: list) -> str:
    counts = {"added": 0, "removed": 0, "modified": 0}
    for it in items:
        counts[it.kind] = counts.get(it.kind, 0) + 1
    return ", ".join(f"{v} {k}" for k, v in counts.items() if v)


def _format_change(item) -> str:
    if item.kind in ("added", "removed"):
        return item.kind
    parts = [
        f"{f}: {_short(b)} -> {_short(a)}"
        for f, (b, a) in (item.field_changes or {}).items()
    ]
    return "modified -- " + "; ".join(parts)


def lineage_to_json_str(lineage: Lineage) -> str:
    """Helper used by tests + the action runner."""
    return json.dumps(to_dict(lineage), indent=2)
