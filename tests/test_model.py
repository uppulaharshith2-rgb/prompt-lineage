"""Model dataclasses + Lineage helpers."""
from __future__ import annotations

from prompt_lineage.model import (
    Contract, FreshnessInfo, Lineage, Prompt, Suite,
)


def _lineage_with(n_prompts: int = 2, n_suites: int = 1, n_contracts: int = 1) -> Lineage:
    return Lineage(
        prompts=[
            Prompt(id=f"p/{i}.md", path=f"p/{i}.md", evaluated_by=[], enforced_by=[])
            for i in range(n_prompts)
        ],
        suites=[
            Suite(id=f"s/{i}.yml", covers_prompts=[], assertions=0, cases=0)
            for i in range(n_suites)
        ],
        contracts=[
            Contract(id=f"c/{i}.py:f", source_path=f"c/{i}.py", func_name="f")
            for i in range(n_contracts)
        ],
    )


def test_counts_basic():
    lineage = _lineage_with(3, 2, 1)
    c = lineage.counts()
    assert c["prompts"] == 3
    assert c["suites"] == 2
    assert c["contracts"] == 1


def test_counts_flags_uncovered_and_unenforced():
    lineage = _lineage_with(2, 0, 0)
    c = lineage.counts()
    assert c["uncovered_prompts"] == 2
    assert c["unenforced_prompts"] == 2


def test_counts_after_marking_covered():
    lineage = _lineage_with(2, 1, 1)
    lineage.prompts[0].evaluated_by.append("s/0.yml")
    lineage.prompts[0].enforced_by.append("c/0.py:f")
    c = lineage.counts()
    assert c["uncovered_prompts"] == 1
    assert c["unenforced_prompts"] == 1


def test_prompt_by_id_returns_none_when_missing():
    lineage = _lineage_with(1, 0, 0)
    assert lineage.prompt_by_id("does/not/exist") is None
    assert lineage.prompt_by_id("p/0.md") is not None


def test_add_edge_dedups():
    lineage = _lineage_with(1, 1, 0)
    lineage.add_edge("a", "b", "evaluated_by")
    lineage.add_edge("a", "b", "evaluated_by")  # duplicate
    lineage.add_edge("a", "b", "covers")  # different kind, kept
    assert len(lineage.edges) == 2


def test_freshness_info_optional_fields():
    info = FreshnessInfo()
    assert info.warn_after is None
    assert info.last_evaluated is None
    assert info.status is None
