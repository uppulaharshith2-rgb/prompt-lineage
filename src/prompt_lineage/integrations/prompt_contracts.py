"""prompt-contracts AST integration.

Walks Python source, finds `@prompt_contract(...)` decorator usages from
github.com/uppulaharshith2-rgb/prompt-contracts, returns one ParsedContract
per decorated function.

AST-only (no exec, no import) for security + robustness. Wraps-prompt inference:
explicit `prompt=` kwarg > body string literal that matches a known prompt path
> None. v0.2 may add explicit annotations.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


DECORATOR_NAME = "prompt_contract"


@dataclass
class ParsedContract:
    """One @prompt_contract usage we found."""

    source_path: Path  # absolute
    func_name: str
    lineno: int
    schema_ref: str | None
    on_violation: str | None
    explicit_prompt: str | None  # literal value of `prompt=` kwarg if present
    body_strings: list[str]  # all string literals in the body, for fuzzy match


def discover_python_sources(root: Path) -> list[Path]:
    """Return all .py files under root, skipping common non-source dirs."""
    root = root.resolve()
    skip = {".venv", "venv", "__pycache__", ".git", "build", "dist", "node_modules"}
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        if any(part in skip for part in p.parts):
            continue
        out.append(p)
    return out


def parse_source(source_path: Path) -> list[ParsedContract]:
    """Return one ParsedContract per `@prompt_contract(...)` in this file.

    Never raises on syntax error: we return [] and let the scan continue."""
    sp = source_path.resolve()
    try:
        tree = ast.parse(sp.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []

    out: list[ParsedContract] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not _is_prompt_contract_call(dec):
                continue
            kwargs = _extract_kwargs(dec)
            body_strings = _collect_strings_in_body(node)
            out.append(
                ParsedContract(
                    source_path=sp,
                    func_name=node.name,
                    lineno=node.lineno,
                    schema_ref=_as_str(kwargs.get("schema")),
                    on_violation=_as_str(kwargs.get("on_violation")),
                    explicit_prompt=_as_str(kwargs.get("prompt")),
                    body_strings=body_strings,
                )
            )
    return out


def _is_prompt_contract_call(dec: ast.expr) -> bool:
    """Match `@prompt_contract(...)` and `@module.prompt_contract(...)`. Bare
    `@prompt_contract` is intentionally not matched -- the real decorator
    requires arguments, so a bare-name match would mostly be false positives."""
    if not isinstance(dec, ast.Call):
        return False
    func = dec.func
    if isinstance(func, ast.Name) and func.id == DECORATOR_NAME:
        return True
    if isinstance(func, ast.Attribute) and func.attr == DECORATOR_NAME:
        return True
    return False


def _extract_kwargs(call: ast.Call) -> dict[str, ast.expr]:
    """Return mapping kwarg-name -> AST value node."""
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def _as_str(node: ast.expr | None) -> str | None:
    """String-literal Constant -> value; else None. We don't evaluate names /
    calls / f-strings (security). v0.2 could add a const-folder."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _collect_strings_in_body(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """String literals in the function body. Filtered to slash-containing
    .md paths so the wraps-prompt heuristic isn't noisy."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            s = sub.value
            if "/" in s and s.endswith(".md"):
                out.append(s)
    return out
