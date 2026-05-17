"""End-to-end smoke: scan the shipped examples/, render, verify."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_examples_dir_exists():
    assert EXAMPLES.is_dir()
    assert (EXAMPLES / "prompts.yml").is_file()
    assert (EXAMPLES / "evals").is_dir()
    assert (EXAMPLES / "src" / "handlers.py").is_file()


def test_scan_examples_via_api():
    from prompt_lineage.scanner import scan
    lineage = scan(EXAMPLES)
    assert len(lineage.prompts) >= 2
    assert any(s.id.endswith("support_triage.yml") for s in lineage.suites)
    assert any(c.func_name == "triage" for c in lineage.contracts)


def test_build_cli_writes_static_site(tmp_path):
    out = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "build",
         str(EXAMPLES), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "index.html").is_file()
    assert (out / "style.css").is_file()
    assert (out / "lineage.json").is_file()
    body = (out / "index.html").read_text()
    assert "prompts/support_triage.md" in body
    assert "claude-sonnet-4-6" in body


def test_build_cli_json_only(tmp_path):
    out = tmp_path / "json-only"
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "build",
         str(EXAMPLES), "--out", str(out), "--json-only"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "lineage.json").read_text())
    assert payload["schema_version"] == "0.1"
    assert len(payload["prompts"]) >= 2
    assert not (out / "index.html").exists()


def test_diff_subcommand_no_changes(tmp_path):
    """Build twice, diff the two outputs: should report no changes."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for o in (a, b):
        subprocess.run(
            [sys.executable, "-m", "prompt_lineage.cli", "build",
             str(EXAMPLES), "--out", str(o), "--json-only"],
            check=True,
        )
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "diff",
         "--before", str(a / "lineage.json"),
         "--after", str(b / "lineage.json")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no lineage changes" in result.stdout


def test_schema_subcommand_prints_schema():
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "schema"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "schema_version" in result.stdout
    assert "prompts[]" in result.stdout


def test_cli_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "prompt-lineage" in result.stdout


@pytest.mark.parametrize("missing_kw", ["before_only", "after_only"])
def test_diff_subcommand_rejects_partial_pair(tmp_path, missing_kw):
    a = tmp_path / "a.json"
    a.write_text("{}")
    args = ["--before", str(a)] if missing_kw == "before_only" else ["--after", str(a)]
    result = subprocess.run(
        [sys.executable, "-m", "prompt_lineage.cli", "diff", *args],
        capture_output=True, text=True,
    )
    assert result.returncode == 2, result.stderr
