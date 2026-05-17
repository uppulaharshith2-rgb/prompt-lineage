"""prompt-contracts AST integration."""
from __future__ import annotations

from prompt_lineage.integrations.prompt_contracts import (
    discover_python_sources, parse_source,
)


def test_parse_source_finds_decorated_function(tmp_path):
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract(schema="x.json", on_violation="quarantine")
def triage(msg):
    s = "prompts/support.md"
    return {}
'''
    )
    parsed = parse_source(f)
    assert len(parsed) == 1
    contract = parsed[0]
    assert contract.func_name == "triage"
    assert contract.schema_ref == "x.json"
    assert contract.on_violation == "quarantine"
    assert "prompts/support.md" in contract.body_strings


def test_parse_source_finds_multiple_decorated_functions(tmp_path):
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract(schema="a.json")
def fa(x): return {}

@prompt_contract(schema="b.json")
def fb(x): return {}
'''
    )
    parsed = parse_source(f)
    names = sorted(c.func_name for c in parsed)
    assert names == ["fa", "fb"]


def test_parse_source_handles_qualified_decorator(tmp_path):
    """`@module.prompt_contract(...)` should match too."""
    f = tmp_path / "h.py"
    f.write_text(
        '''\
import prompt_contracts as pc

@pc.prompt_contract(schema="x.json")
def f(x): return {}
'''
    )
    parsed = parse_source(f)
    assert len(parsed) == 1
    assert parsed[0].func_name == "f"


def test_parse_source_ignores_unrelated_decorators(tmp_path):
    f = tmp_path / "h.py"
    f.write_text(
        '''\
def dec(f): return f

@dec
def not_a_contract(x): return {}
'''
    )
    assert parse_source(f) == []


def test_parse_source_ignores_bare_name_decorator(tmp_path):
    """`@prompt_contract` (no call) is intentionally not matched."""
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract
def f(x): return {}
'''
    )
    assert parse_source(f) == []


def test_parse_source_tolerates_syntax_errors(tmp_path):
    f = tmp_path / "h.py"
    f.write_text("def broken(:\n")
    assert parse_source(f) == []


def test_parse_source_async_functions(tmp_path):
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract(schema="x.json")
async def af(x): return {}
'''
    )
    parsed = parse_source(f)
    assert len(parsed) == 1
    assert parsed[0].func_name == "af"


def test_parse_source_extracts_explicit_prompt_kwarg(tmp_path):
    """Forward-compat with a v0.x prompt-contracts feature that lets users
    pass `prompt="path/to/x.md"` directly to the decorator."""
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract(schema="x.json", prompt="prompts/exact.md")
def f(x): return {}
'''
    )
    parsed = parse_source(f)
    assert parsed[0].explicit_prompt == "prompts/exact.md"


def test_parse_source_only_collects_md_path_strings(tmp_path):
    """Non-.md strings shouldn't show up in the inference candidates -- they
    create false positives in the wraps-prompt heuristic."""
    f = tmp_path / "h.py"
    f.write_text(
        '''\
from prompt_contracts import prompt_contract

@prompt_contract(schema="x.json")
def f(x):
    irrelevant = "hello world"
    referenced = "prompts/right.md"
    return {}
'''
    )
    parsed = parse_source(f)
    assert "prompts/right.md" in parsed[0].body_strings
    assert "hello world" not in parsed[0].body_strings


def test_discover_python_sources_skips_common_junk_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "good.py").write_text("x = 1")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "skip.py").write_text("x = 1")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.py").write_text("x = 1")
    found = [p.name for p in discover_python_sources(tmp_path)]
    assert found == ["good.py"]
