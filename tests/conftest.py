"""Shared fixtures: a `tmp_project` factory that builds tiny scan roots."""
from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_project(tmp_path: Path):
    """Return a builder that materializes a small project tree.

    Each call writes the given file map under tmp_path, then yields the
    resolved tmp_path. We pass it as a callable so individual tests can shape
    their fixture (e.g. add a single prompt with no suite vs. the full
    quartet)."""
    def _build(files: dict[str, str], state: dict | None = None) -> Path:
        for rel, content in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(content))
        if state is not None:
            sd = tmp_path / ".prompt-freshness"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "state.json").write_text(json.dumps(state))
        return tmp_path

    return _build


@pytest.fixture()
def example_project(tmp_project):
    """The canonical fixture used by integration tests. Two prompts, two
    suites, one wrapping contract."""
    return tmp_project(
        {
            "prompts.yml": """
                defaults:
                  warn_after: 30d
                  error_after: 90d
                prompts:
                  - path: prompts/support_triage.md
                    model: claude-sonnet-4-6
                  - path: prompts/extract_invoice.md
                    model: claude-haiku-4-5
            """,
            "prompts/support_triage.md": "# Support\n\nA prompt.",
            "prompts/extract_invoice.md": "# Invoice\n\nAnother prompt.",
            "evals/support_triage.yml": """
                name: support_triage
                prompt: ../prompts/support_triage.md
                model: claude-sonnet-4-6
                cases:
                  - id: a
                    assertions:
                      - regex_match: { field: x, pattern: "y" }
                  - id: b
                    assertions:
                      - regex_match: { field: x, pattern: "y" }
            """,
            "evals/extract_invoice.yml": """
                name: extract_invoice
                prompt: ../prompts/extract_invoice.md
                model: claude-haiku-4-5
                cases:
                  - id: c
                    assertions:
                      - json_schema: { schema: { type: object } }
            """,
            "src/handlers.py": """
                from prompt_contracts import prompt_contract  # noqa

                @prompt_contract(
                    schema="contracts/support_triage.json",
                    on_violation="quarantine",
                )
                def triage(message: str) -> dict:
                    _ = "prompts/support_triage.md"
                    return {}
            """,
        },
        state={
            "prompts": {
                "prompts/support_triage.md": {
                    "model": "claude-sonnet-4-6",
                    "last_evaluated": time.time() - 60,
                },
            }
        },
    )
