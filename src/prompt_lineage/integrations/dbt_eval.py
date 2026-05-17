"""dbt-eval suite parser.

Reads dbt-eval-shape YAML suites (github.com/uppulaharshith2-rgb/dbt-eval)
and extracts: covered prompt(s), case count, assertion count.

Prompt refs (priority order): top-level `prompt:`, top-level `prompts:` list,
per-case `prompt:`, convention fallback `../prompts/<suite-stem>.md`.

Tolerant: malformed assertions don't abort the scan -- lineage should still
build when half the repo is broken, that's exactly when you need it most.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ParsedSuite:
    """In-memory record returned to the scanner."""

    path: Path  # absolute
    name: str
    model: str | None
    prompt_paths: list[Path]  # absolute, deduped
    case_count: int
    assertion_count: int


def discover_suites(root: Path) -> list[Path]:
    """Find dbt-eval YAML suites under `<root>/evals/` (or recursive fallback).
    Always skips `prompts.yml` (that's prompt-freshness)."""
    root = root.resolve()
    evals_dir = root / "evals"
    base = evals_dir if evals_dir.is_dir() else root
    matches = sorted(list(base.rglob("*.yml")) + list(base.rglob("*.yaml")))
    return [m for m in matches if m.name != "prompts.yml"]


def parse_suite(suite_path: Path) -> ParsedSuite:
    """Parse one suite YAML. Never raises: bad YAML -> empty ParsedSuite."""
    sp = suite_path.resolve()
    try:
        raw = yaml.safe_load(sp.read_text()) or {}
    except yaml.YAMLError:
        return ParsedSuite(
            path=sp, name=sp.stem, model=None,
            prompt_paths=[], case_count=0, assertion_count=0,
        )
    if not isinstance(raw, dict):
        return ParsedSuite(
            path=sp, name=sp.stem, model=None,
            prompt_paths=[], case_count=0, assertion_count=0,
        )

    name = str(raw.get("name") or sp.stem)
    model = raw.get("model")
    model_s = str(model) if model is not None else None

    refs: list[str] = []
    if isinstance(raw.get("prompt"), str):
        refs.append(raw["prompt"])
    if isinstance(raw.get("prompts"), list):
        refs.extend(str(r) for r in raw["prompts"] if isinstance(r, str))

    cases = raw.get("cases") or []
    case_count = len(cases) if isinstance(cases, list) else 0
    assertion_count = 0
    if isinstance(cases, list):
        for case in cases:
            if not isinstance(case, dict):
                continue
            if isinstance(case.get("prompt"), str):
                refs.append(case["prompt"])
            a = case.get("assertions")
            if isinstance(a, list):
                assertion_count += len(a)

    if not refs:
        # Convention fallback: a sibling prompts/ dir alongside the evals dir.
        guess = sp.parent.parent / "prompts" / f"{name}.md"
        if guess.exists():
            refs.append(str(guess))

    seen: set[Path] = set()
    resolved: list[Path] = []
    for ref in refs:
        candidate = (sp.parent / ref).resolve()
        if not candidate.exists():
            # Soft: a stale reference does not break the lineage build.
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        resolved.append(candidate)

    return ParsedSuite(
        path=sp,
        name=name,
        model=model_s,
        prompt_paths=resolved,
        case_count=case_count,
        assertion_count=assertion_count,
    )
