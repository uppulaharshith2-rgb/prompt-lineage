"""JSON renderer: the schema that locks in."""
from __future__ import annotations

import json

from prompt_lineage import SCHEMA_VERSION
from prompt_lineage.render.json import to_dict, to_json
from prompt_lineage.scanner import scan


def test_to_dict_top_level_keys(example_project):
    lineage = scan(example_project)
    data = to_dict(lineage)
    assert set(data.keys()) >= {
        "schema_version", "generated_at", "root_path", "counts",
        "prompts", "suites", "contracts", "edges",
    }
    assert data["schema_version"] == SCHEMA_VERSION


def test_to_dict_edges_use_from_to_keys(example_project):
    lineage = scan(example_project)
    data = to_dict(lineage)
    for edge in data["edges"]:
        assert set(edge.keys()) == {"from", "to", "kind"}


def test_to_dict_prompt_has_required_fields(example_project):
    lineage = scan(example_project)
    data = to_dict(lineage)
    sample = data["prompts"][0]
    assert {"id", "path", "evaluated_by", "enforced_by"} <= set(sample.keys())


def test_to_dict_omits_freshness_when_none():
    """Don't serialize null freshness as a noisy {} -- omit instead."""
    from prompt_lineage.model import Lineage, Prompt
    lineage = Lineage(
        prompts=[Prompt(id="x.md", path="x.md", freshness=None)],
        generated_at="2026-05-17T00:00:00+00:00",
    )
    data = to_dict(lineage)
    assert "freshness" not in data["prompts"][0]


def test_to_json_is_valid_json(example_project):
    lineage = scan(example_project)
    out = to_json(lineage)
    assert json.loads(out)["schema_version"] == SCHEMA_VERSION


def test_to_json_indentation_is_2_spaces(example_project):
    lineage = scan(example_project)
    out = to_json(lineage)
    # First line is `{`, second should start with two spaces.
    second = out.splitlines()[1]
    assert second.startswith("  "), repr(second)


def test_schema_counts_match_lineage_counts(example_project):
    lineage = scan(example_project)
    data = to_dict(lineage)
    assert data["counts"]["prompts"] == len(data["prompts"])
    assert data["counts"]["suites"] == len(data["suites"])
    assert data["counts"]["contracts"] == len(data["contracts"])
