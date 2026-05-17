# prompt-lineage example

A minimal end-to-end project for exercising `prompt-lineage`.

```
examples/
├── prompts.yml                 prompt-freshness manifest
├── prompts/
│   ├── support_triage.md       prompt template
│   └── extract_invoice.md      prompt template
├── evals/
│   ├── support_triage.yml      dbt-eval suite covering support_triage
│   └── extract_invoice.yml     dbt-eval suite covering extract_invoice
├── src/
│   └── handlers.py             @prompt_contract usage that wraps each prompt
└── .github/workflows/
    └── lineage.yml             PR sticky-comment Action
```

## Run the build

From the repo root:

```bash
pip install -e .
prompt-lineage build examples/
open examples/lineage-site/index.html
```

You should see two prompts, two suites, two contracts, four edges, and a
sortable table with searches + status filters.

## Run the diff (against itself, as a smoke test)

```bash
prompt-lineage build examples/ --json-only --out /tmp/before
# (edit a prompt, e.g. bump a model alias in evals/support_triage.yml)
prompt-lineage build examples/ --json-only --out /tmp/after
prompt-lineage diff --before /tmp/before/lineage.json --after /tmp/after/lineage.json
```
