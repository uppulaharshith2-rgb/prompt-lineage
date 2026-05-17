"""prompt-freshness manifest + state integration."""
from __future__ import annotations

import json
import time

from prompt_lineage.integrations.prompt_freshness import load_snapshot


def test_load_snapshot_missing_manifest_returns_flagged_empty(tmp_path):
    snap = load_snapshot(tmp_path)
    assert snap.entries == []
    assert snap.manifest_found is False
    assert snap.state_found is False


def test_load_snapshot_with_manifest_no_state(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    (tmp_path / "prompts.yml").write_text(
        "defaults:\n  warn_after: 30d\n  error_after: 90d\n"
        "prompts:\n  - path: prompts/p.md\n    model: m\n"
    )
    snap = load_snapshot(tmp_path)
    assert snap.manifest_found is True
    assert len(snap.entries) == 1
    e = snap.entries[0]
    assert e.path == "prompts/p.md"
    assert e.model == "m"
    assert e.status == "unevaluated"


def test_load_snapshot_with_fresh_state(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    (tmp_path / "prompts.yml").write_text(
        "defaults: { warn_after: 14d, error_after: 30d }\n"
        "prompts:\n  - path: prompts/p.md\n    model: m\n"
    )
    sd = tmp_path / ".prompt-freshness"
    sd.mkdir()
    (sd / "state.json").write_text(json.dumps({
        "prompts": {"prompts/p.md": {"model": "m", "last_evaluated": time.time() - 60}}
    }))
    snap = load_snapshot(tmp_path)
    assert snap.entries[0].status == "fresh"
    assert snap.entries[0].last_evaluated_iso is not None


def test_load_snapshot_model_drift_is_stale(tmp_path):
    """The classic prompt-freshness rule: alias drift resets freshness."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    (tmp_path / "prompts.yml").write_text(
        "defaults: { warn_after: 30d, error_after: 90d }\n"
        "prompts:\n  - path: prompts/p.md\n    model: claude-sonnet-4-7\n"
    )
    sd = tmp_path / ".prompt-freshness"
    sd.mkdir()
    (sd / "state.json").write_text(json.dumps({
        "prompts": {
            "prompts/p.md": {
                "model": "claude-sonnet-4-6",  # drifted
                "last_evaluated": time.time() - 60,
            }
        }
    }))
    snap = load_snapshot(tmp_path)
    assert snap.entries[0].status == "stale"


def test_load_snapshot_warning_when_past_warn_but_not_error(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    (tmp_path / "prompts.yml").write_text(
        "prompts:\n  - path: prompts/p.md\n    model: m\n"
        "    warn_after: 1s\n    error_after: 1000h\n"
    )
    sd = tmp_path / ".prompt-freshness"
    sd.mkdir()
    (sd / "state.json").write_text(json.dumps({
        "prompts": {"prompts/p.md": {"model": "m", "last_evaluated": time.time() - 60}}
    }))
    snap = load_snapshot(tmp_path)
    assert snap.entries[0].status == "warning"


def test_load_snapshot_handles_bad_manifest_yaml(tmp_path):
    (tmp_path / "prompts.yml").write_text(":\n  bad: : yaml")
    snap = load_snapshot(tmp_path)
    assert snap.manifest_found is True
    assert snap.entries == []


def test_load_snapshot_handles_bad_state_json(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    (tmp_path / "prompts.yml").write_text(
        "prompts:\n  - path: prompts/p.md\n    model: m\n"
    )
    sd = tmp_path / ".prompt-freshness"
    sd.mkdir()
    (sd / "state.json").write_text("not json{")
    snap = load_snapshot(tmp_path)
    # Just skips the corrupt state file; manifest entries still present.
    assert snap.state_found is True
    assert snap.entries[0].status == "unevaluated"


def test_load_snapshot_glob_expansion(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "a.md").write_text("a")
    (tmp_path / "prompts" / "b.md").write_text("b")
    (tmp_path / "prompts.yml").write_text(
        "prompts:\n  - path: prompts/*.md\n    model: m\n"
    )
    snap = load_snapshot(tmp_path)
    paths = sorted(e.path for e in snap.entries)
    assert paths == ["prompts/a.md", "prompts/b.md"]
