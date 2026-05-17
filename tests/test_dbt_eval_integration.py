"""dbt-eval suite parser integration."""
from __future__ import annotations

from prompt_lineage.integrations.dbt_eval import (
    discover_suites, parse_suite,
)


def test_discover_suites_under_evals_dir(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "a.yml").write_text("name: a")
    (tmp_path / "evals" / "b.yaml").write_text("name: b")
    found = discover_suites(tmp_path)
    assert {s.name for s in found} == {"a.yml", "b.yaml"}


def test_discover_suites_without_evals_dir_falls_back_to_recursive(tmp_path):
    (tmp_path / "x.yml").write_text("name: x")
    found = discover_suites(tmp_path)
    assert {s.name for s in found} == {"x.yml"}


def test_discover_suites_skips_prompts_yml(tmp_path):
    (tmp_path / "prompts.yml").write_text("defaults: {}")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "real.yml").write_text("name: real")
    found = discover_suites(tmp_path)
    assert {s.name for s in found} == {"real.yml"}


def test_parse_suite_extracts_top_level_prompt(tmp_path):
    suite = tmp_path / "evals" / "s.yml"
    suite.parent.mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    suite.write_text(
        "name: s\nprompt: ../prompts/p.md\nmodel: claude-sonnet-4-6\n"
        "cases:\n  - id: c1\n  - id: c2\n"
    )
    parsed = parse_suite(suite)
    assert parsed.name == "s"
    assert parsed.model == "claude-sonnet-4-6"
    assert len(parsed.prompt_paths) == 1
    assert parsed.prompt_paths[0].name == "p.md"
    assert parsed.case_count == 2


def test_parse_suite_counts_assertions(tmp_path):
    suite = tmp_path / "evals" / "s.yml"
    suite.parent.mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    suite.write_text(
        """\
name: s
prompt: ../prompts/p.md
model: m
cases:
  - id: c1
    assertions:
      - regex_match: { field: x, pattern: "y" }
      - json_schema: { schema: { type: object } }
  - id: c2
    assertions:
      - faithful: { to: input, claim_field: rationale, threshold: 0.5 }
"""
    )
    parsed = parse_suite(suite)
    assert parsed.case_count == 2
    assert parsed.assertion_count == 3


def test_parse_suite_handles_bad_yaml_gracefully(tmp_path):
    suite = tmp_path / "bad.yml"
    suite.write_text(":\n  bad: : yaml")
    parsed = parse_suite(suite)
    assert parsed.case_count == 0
    assert parsed.assertion_count == 0
    assert parsed.prompt_paths == []


def test_parse_suite_deduplicates_repeat_prompt_refs(tmp_path):
    suite = tmp_path / "evals" / "s.yml"
    suite.parent.mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("hi")
    suite.write_text(
        """\
name: s
prompt: ../prompts/p.md
model: m
cases:
  - id: c1
    prompt: ../prompts/p.md
  - id: c2
    prompt: ../prompts/p.md
"""
    )
    parsed = parse_suite(suite)
    assert len(parsed.prompt_paths) == 1


def test_parse_suite_skips_unresolvable_prompts(tmp_path):
    """A missing referenced prompt should not break the suite parse -- we
    just record fewer paths and let lineage report the gap."""
    suite = tmp_path / "evals" / "s.yml"
    suite.parent.mkdir()
    suite.write_text("name: s\nprompt: ../prompts/missing.md\nmodel: m\ncases: []\n")
    parsed = parse_suite(suite)
    assert parsed.prompt_paths == []
