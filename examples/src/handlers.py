"""Example application code that wraps each prompt behind a prompt-contracts
schema. prompt-lineage AST-walks this file and connects:

    handlers.py:triage            -> prompts/support_triage.md
    handlers.py:extract_invoice   -> prompts/extract_invoice.md

This file does NOT need to be runnable -- prompt-lineage uses AST, never
imports the module. We import prompt_contracts only for type-checking flavor;
the lineage scan succeeds even if prompt_contracts is not installed.
"""
from __future__ import annotations

try:
    from prompt_contracts import prompt_contract
except ImportError:
    def prompt_contract(*a, **kw):  # type: ignore[no-redef]
        def _wrap(f):
            return f
        return _wrap


@prompt_contract(
    schema="contracts/support_triage.json",
    on_violation="quarantine",
    quarantine_path="./_rejected.jsonl",
    coerce=True,
)
def triage(message: str) -> dict:
    """Triage a support ticket. Returns a dict matching support_triage.json.

    The string literal "prompts/support_triage.md" below is what prompt-lineage
    matches on -- the AST scan picks up `.md` path literals inside the function
    body and links them to discovered prompt files. In a real app this line
    would be a real file read, not a tagging hack.
    """
    prompt = "prompts/support_triage.md"
    _ = prompt
    return {
        "category": "bug",
        "confidence": 0.8,
        "rationale": "Stub response for " + message[:40],
    }


@prompt_contract(
    schema="contracts/extract_invoice.json",
    on_violation="raise",
)
def extract_invoice(pdf_text: str) -> dict:
    """Extract invoice fields. The "prompts/extract_invoice.md" literal below
    is the link prompt-lineage's AST scan uses to associate this contract
    with the prompt template."""
    prompt = "prompts/extract_invoice.md"
    _ = prompt
    return {
        "vendor": "Acme",
        "invoice_number": "1234",
        "total_amount": 99.0,
        "currency": "USD",
        "issue_date": "2026-03-15",
    }
