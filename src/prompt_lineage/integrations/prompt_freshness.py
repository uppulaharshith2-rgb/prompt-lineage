"""prompt-freshness manifest + state integration.

Reads `<root>/prompts.yml` and `<root>/.prompt-freshness/state.json`. Both
optional. We re-implement the loader (rather than `import`) so prompt-lineage
stays zero-deps on the rest of the suite -- the interop is over the file
shape, not Python imports.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass
class FreshnessEntry:
    """What the scanner needs to know per prompt."""

    path: str  # manifest-relative POSIX
    model: str
    warn_after: str | None
    error_after: str | None
    last_evaluated_iso: str | None
    status: str  # 'fresh' | 'warning' | 'stale' | 'unevaluated'


@dataclass
class FreshnessSnapshot:
    """In-memory result of reading both manifest and state."""

    entries: list[FreshnessEntry]
    manifest_found: bool
    state_found: bool


def load_snapshot(root: Path) -> FreshnessSnapshot:
    """Read manifest + state. Missing files = integration absent, not error."""
    root = root.resolve()
    manifest_path = root / "prompts.yml"
    state_path = root / ".prompt-freshness" / "state.json"

    if not manifest_path.exists():
        return FreshnessSnapshot(
            entries=[], manifest_found=False, state_found=state_path.exists()
        )

    try:
        manifest_raw = yaml.safe_load(manifest_path.read_text()) or {}
    except yaml.YAMLError:
        return FreshnessSnapshot(
            entries=[], manifest_found=True, state_found=state_path.exists()
        )

    defaults = manifest_raw.get("defaults") or {}
    default_warn = defaults.get("warn_after")
    default_error = defaults.get("error_after")
    default_model = defaults.get("model")

    entries_raw = manifest_raw.get("prompts") or []
    seen: dict[str, FreshnessEntry] = {}
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        pattern = item.get("path")
        if not isinstance(pattern, str):
            continue
        model = item.get("model", default_model)
        if not isinstance(model, str):
            continue
        warn = item.get("warn_after", default_warn)
        err = item.get("error_after", default_error)
        for rel in _expand_pattern(root, pattern):
            if rel in seen:
                continue
            seen[rel] = FreshnessEntry(
                path=rel, model=model,
                warn_after=str(warn) if warn else None,
                error_after=str(err) if err else None,
                last_evaluated_iso=None,
                status="unevaluated",
            )

    state_data: dict[str, dict] = {}
    if state_path.exists():
        try:
            state_data = json.loads(state_path.read_text()) or {}
        except (json.JSONDecodeError, OSError):
            state_data = {}
    # state.json: {"prompts": {"<path>": {"model": "...", "last_evaluated": <unix>}}}
    prompts_state = state_data.get("prompts", {}) if isinstance(state_data, dict) else {}

    for rel, entry in seen.items():
        record = prompts_state.get(rel)
        if not isinstance(record, dict):
            continue
        recorded_model = record.get("model")
        last_ts = record.get("last_evaluated")
        if not isinstance(last_ts, (int, float)):
            continue
        entry.last_evaluated_iso = datetime.fromtimestamp(
            last_ts, tz=timezone.utc
        ).isoformat()
        # Classic prompt-freshness rule: alias drift resets the freshness clock.
        if recorded_model != entry.model:
            entry.status = "stale"
            continue
        entry.status = _classify_age(last_ts, entry.warn_after, entry.error_after)

    return FreshnessSnapshot(
        entries=list(seen.values()),
        manifest_found=True,
        state_found=state_path.exists(),
    )


_DURATION_UNITS = {
    "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800,
}


def _parse_duration(value: str | None) -> int | None:
    """'14d' -> 1209600. Mirrors prompt-freshness's parser."""
    if not value or not (v := value.strip()):
        return None
    try:
        return int(v[:-1]) * _DURATION_UNITS[v[-1].lower()]
    except (ValueError, KeyError, IndexError):
        return None


def _classify_age(last_ts: float, warn_after: str | None, error_after: str | None) -> str:
    """Bucket (now - last_ts) against warn/error thresholds."""
    age = max(0.0, datetime.now(tz=timezone.utc).timestamp() - last_ts)
    warn_s = _parse_duration(warn_after)
    err_s = _parse_duration(error_after)
    if err_s is not None and age >= err_s:
        return "stale"
    if warn_s is not None and age >= warn_s:
        return "warning"
    return "fresh"


def _expand_pattern(base: Path, pattern: str) -> list[str]:
    """Manifest path/glob -> repo-relative POSIX paths."""
    if any(ch in pattern for ch in "*?["):
        return [
            f.resolve().relative_to(base).as_posix()
            for f in sorted(base.glob(pattern)) if f.is_file()
        ]
    candidate = (base / pattern).resolve()
    if not (candidate.exists() and candidate.is_file()):
        return []
    try:
        return [candidate.relative_to(base).as_posix()]
    except ValueError:
        return [candidate.as_posix()]
