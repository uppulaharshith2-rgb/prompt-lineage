"""Lineage diff: structural comparison of two scans."""
from __future__ import annotations

from prompt_lineage.diff import (
    diff_lineages, parse_ref_pair,
)
from prompt_lineage.model import Contract, Lineage, Prompt, Suite


def _make(prompts, suites=None, contracts=None) -> Lineage:
    return Lineage(
        prompts=list(prompts),
        suites=list(suites or []),
        contracts=list(contracts or []),
    )


def test_diff_no_changes_when_identical():
    a = _make([Prompt(id="p.md", path="p.md")])
    b = _make([Prompt(id="p.md", path="p.md")])
    report = diff_lineages(a, b)
    assert not report.has_changes
    assert report.total_changes == 0


def test_diff_detects_added_prompt():
    a = _make([Prompt(id="p.md", path="p.md")])
    b = _make([Prompt(id="p.md", path="p.md"), Prompt(id="q.md", path="q.md")])
    report = diff_lineages(a, b)
    assert report.total_changes == 1
    assert report.prompt_changes[0].id == "q.md"
    assert report.prompt_changes[0].kind == "added"


def test_diff_detects_removed_prompt():
    a = _make([Prompt(id="p.md", path="p.md"), Prompt(id="q.md", path="q.md")])
    b = _make([Prompt(id="p.md", path="p.md")])
    report = diff_lineages(a, b)
    assert report.total_changes == 1
    assert report.prompt_changes[0].id == "q.md"
    assert report.prompt_changes[0].kind == "removed"


def test_diff_detects_model_alias_bump():
    a = _make([Prompt(id="p.md", path="p.md", model_alias="claude-sonnet-4-6")])
    b = _make([Prompt(id="p.md", path="p.md", model_alias="claude-sonnet-4-7")])
    report = diff_lineages(a, b)
    assert report.total_changes == 1
    change = report.prompt_changes[0]
    assert change.kind == "modified"
    assert "model" in change.field_changes
    assert change.field_changes["model"] == ("claude-sonnet-4-6", "claude-sonnet-4-7")


def test_diff_detects_suite_coverage_change():
    a = _make([Prompt(id="p.md", path="p.md", evaluated_by=["s1.yml"])])
    b = _make([Prompt(id="p.md", path="p.md", evaluated_by=["s1.yml", "s2.yml"])])
    report = diff_lineages(a, b)
    assert "eval suites" in report.prompt_changes[0].field_changes


def test_diff_detects_added_suite():
    a = _make([], suites=[])
    b = _make([], suites=[Suite(id="s.yml")])
    report = diff_lineages(a, b)
    assert len(report.suite_changes) == 1
    assert report.suite_changes[0].kind == "added"


def test_diff_detects_added_contract():
    a = _make([])
    b = _make([], contracts=[Contract(id="c.py:f", source_path="c.py", func_name="f")])
    report = diff_lineages(a, b)
    assert len(report.contract_changes) == 1
    assert report.contract_changes[0].kind == "added"


def test_diff_terminal_output_for_no_changes():
    report = diff_lineages(_make([]), _make([]))
    out = report.as_terminal()
    assert "no lineage changes" in out


def test_diff_terminal_output_includes_change_summary():
    a = _make([Prompt(id="p.md", path="p.md", model_alias="m1")])
    b = _make([Prompt(id="p.md", path="p.md", model_alias="m2")])
    report = diff_lineages(a, b)
    out = report.as_terminal()
    assert "p.md" in out
    assert "modified" in out
    assert "m1" in out and "m2" in out


def test_diff_markdown_output():
    a = _make([Prompt(id="old.md", path="old.md")])
    b = _make([Prompt(id="new.md", path="new.md")])
    report = diff_lineages(a, b)
    md = report.as_markdown()
    assert "old.md" in md
    assert "new.md" in md
    assert md.startswith("## prompt-lineage diff")


def test_diff_as_dict_serializable():
    a = _make([Prompt(id="p.md", path="p.md", model_alias="m1")])
    b = _make([Prompt(id="p.md", path="p.md", model_alias="m2")])
    import json
    out = json.dumps(diff_lineages(a, b).as_dict())
    assert "p.md" in out


def test_parse_ref_pair_two_dots():
    assert parse_ref_pair("main..HEAD") == ("main", "HEAD")


def test_parse_ref_pair_three_dots():
    assert parse_ref_pair("main...HEAD") == ("main", "HEAD")


def test_parse_ref_pair_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_ref_pair("no-double-dots")
    with pytest.raises(ValueError):
        parse_ref_pair("..HEAD")
    with pytest.raises(ValueError):
        parse_ref_pair("main..")
