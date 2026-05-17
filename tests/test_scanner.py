"""Scanner: walks a project root and produces a Lineage."""
from __future__ import annotations

import pytest

from prompt_lineage.scanner import ScanError, scan


def test_scan_missing_root_raises(tmp_path):
    with pytest.raises(ScanError):
        scan(tmp_path / "nonexistent")


def test_scan_root_must_be_directory(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("not a dir")
    with pytest.raises(ScanError):
        scan(f)


def test_scan_empty_project_returns_empty_lineage(tmp_path):
    out = scan(tmp_path)
    assert out.prompts == []
    assert out.suites == []
    assert out.contracts == []
    assert out.edges == []
    assert out.generated_at is not None


def test_scan_full_example(example_project):
    lineage = scan(example_project)

    assert {p.id for p in lineage.prompts} == {
        "prompts/support_triage.md", "prompts/extract_invoice.md",
    }
    assert {s.id for s in lineage.suites} == {
        "evals/support_triage.yml", "evals/extract_invoice.yml",
    }
    assert len(lineage.contracts) == 1
    contract = lineage.contracts[0]
    assert contract.func_name == "triage"
    assert contract.wraps_prompt == "prompts/support_triage.md"
    assert contract.on_violation == "quarantine"


def test_scan_populates_back_pointers(example_project):
    lineage = scan(example_project)
    support = lineage.prompt_by_id("prompts/support_triage.md")
    assert support is not None
    assert support.evaluated_by == ["evals/support_triage.yml"]
    assert support.enforced_by == ["src/handlers.py:triage"]


def test_scan_freshness_status_propagates(example_project):
    lineage = scan(example_project)
    support = lineage.prompt_by_id("prompts/support_triage.md")
    invoice = lineage.prompt_by_id("prompts/extract_invoice.md")
    assert support.freshness is not None
    assert support.freshness.status == "fresh"
    assert invoice.freshness is not None
    # No state for invoice in the fixture -> unevaluated.
    assert invoice.freshness.status == "unevaluated"


def test_scan_dedups_evaluated_by(tmp_project):
    """A suite that mentions the same prompt twice (top-level + per-case)
    should still produce a single edge."""
    root = tmp_project(
        {
            "prompts.yml": """
                defaults: { warn_after: 30d, error_after: 90d }
                prompts:
                  - path: prompts/p.md
                    model: m
            """,
            "prompts/p.md": "x",
            "evals/s.yml": """
                name: s
                prompt: ../prompts/p.md
                model: m
                cases:
                  - id: c1
                    prompt: ../prompts/p.md
            """,
        }
    )
    lineage = scan(root)
    p = lineage.prompt_by_id("prompts/p.md")
    assert p.evaluated_by == ["evals/s.yml"]
    evaluated_edges = [e for e in lineage.edges if e.kind == "evaluated_by"]
    assert len(evaluated_edges) == 1


def test_scan_edges_count(example_project):
    lineage = scan(example_project)
    # 2 suites x 2 (evaluated_by + covers) = 4
    # 1 contract -> 1 wraps + 1 enforced_by = 2
    # total 6
    assert len(lineage.edges) == 6
    kinds = sorted(e.kind for e in lineage.edges)
    assert kinds.count("evaluated_by") == 2
    assert kinds.count("covers") == 2
    assert kinds.count("enforced_by") == 1
    assert kinds.count("wraps") == 1


def test_scan_handles_missing_freshness_files(tmp_project):
    """Scan must still work without prompts.yml / state.json -- the suite is
    optional, and v0 should not error when only one tool is in use."""
    root = tmp_project(
        {
            "evals/x.yml": """
                name: x
                prompt: ../prompts/x.md
                model: claude-sonnet-4-6
                cases:
                  - id: c
            """,
            "prompts/x.md": "hello",
        }
    )
    lineage = scan(root)
    assert len(lineage.prompts) == 1
    p = lineage.prompts[0]
    assert p.freshness is None
