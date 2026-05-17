# prompt-lineage

> **dbt-docs for prompts.** Lineage graph: `prompts -> eval suites -> contracts -> callers`. CLI emits `lineage.json` + a static HTML navigation site.

Every analytics engineer has clicked through dbt-docs and immediately
understood the value: a single searchable view of every model, what feeds
it, what depends on it, and how stale it is. `prompt-lineage` ports that
pattern to LLM prompts. Point it at a repo, get a static HTML site that
answers, in one click:

- which prompts exist in this codebase?
- which eval suites cover which prompts?
- which production functions wrap which prompts behind a contract?
- which prompts are stale, uncovered, or unenforced?

That last one is the kill question. In a typical LLM codebase, prompts
drift out of test coverage and nobody notices until production breaks.
`prompt-lineage` makes the gap visible.

**Status**: v0.1 public alpha. ~1500 LOC Python, zero LLM calls, MIT.

---

## The suite

`prompt-lineage` is the **fourth and final** member of a dbt-style
governance suite for prompts:

| Tool | Role |
|------|------|
| [dbt-eval](https://github.com/uppulaharshith2-rgb/dbt-eval) | Declare what good output looks like (YAML test suites) |
| [prompt-contracts](https://github.com/uppulaharshith2-rgb/prompt-contracts) | Enforce it at runtime (`@prompt_contract` decorator) |
| [prompt-freshness](https://github.com/uppulaharshith2-rgb/prompt-freshness) | Keep both honest as models shift (per-(prompt, model) staleness) |
| **prompt-lineage** | The navigation surface that ties the trio into a platform |

The first three solve atomic problems. `prompt-lineage` is the
retroactive coherence layer: it reads each tool's existing files (no
re-instrumentation) and stitches them into one view. The trio works
without it. The suite *only feels like a platform* with it.

---

## Install

```bash
pip install prompt-lineage
pip install git+https://github.com/uppulaharshith2-rgb/prompt-lineage.git
curl -fsSL https://raw.githubusercontent.com/uppulaharshith2-rgb/prompt-lineage/main/install.sh | bash
```

Python 3.10+. Runtime deps: `pyyaml`, `click`, `jinja2`. `rich` optional.

---

## 30-second example

```bash
git clone https://github.com/uppulaharshith2-rgb/prompt-lineage.git
cd prompt-lineage
pip install -e .

prompt-lineage build examples/
open examples/lineage-site/index.html       # or just lineage-site/ at the repo root
```

You'll see something like:

```
prompt-lineage                                   built 2026-05-17 08:50 . 2 prompts . 2 suites . 2 contracts

  [ 2 ] PROMPTS    [ 2 ] EVAL SUITES   [ 2 ] CONTRACTS   [ 0 ] UNCOVERED   [ 0 ] UNENFORCED

  [search...]    all  fresh  warning  stale  unevaluated  uncovered  unenforced
  ----------------------------------------------------------------------------
  PROMPT                          MODEL              EVAL SUITES  CONTRACTS  FRESHNESS
  > prompts/support_triage.md    claude-sonnet-4-6     1             1       UNEVALUATED
  > prompts/extract_invoice.md   claude-haiku-4-5      1             1       UNEVALUATED
```

Click a prompt row -> per-prompt detail page with linked suites, linked
contracts, freshness metadata, and an inline prompt-source excerpt.

---

## The lineage.json schema (the part that locks in)

The HTML site is replaceable. The `lineage.json` shape is what adopters
write tooling against, so we treat it like a public API:

```json
{
  "schema_version": "0.1",
  "generated_at": "2026-05-17T08:50:03+00:00",
  "root_path": "/abs/path/to/scan/root",
  "counts": {
    "prompts": 2, "suites": 2, "contracts": 2, "edges": 8,
    "uncovered_prompts": 0, "unenforced_prompts": 0
  },
  "prompts": [
    {
      "id": "prompts/support_triage.md",
      "path": "prompts/support_triage.md",
      "last_modified": "2026-05-17T08:45:01+00:00",
      "model_alias": "claude-sonnet-4-6",
      "evaluated_by": ["evals/support_triage.yml"],
      "enforced_by": ["src/handlers.py:triage"],
      "freshness": {
        "warn_after": "14d", "error_after": "30d",
        "last_evaluated": null, "status": "unevaluated"
      }
    }
  ],
  "suites": [
    { "id": "evals/support_triage.yml",
      "covers_prompts": ["prompts/support_triage.md"],
      "assertions": 5, "cases": 2 }
  ],
  "contracts": [
    { "id": "src/handlers.py:triage",
      "source_path": "src/handlers.py", "func_name": "triage",
      "schema_ref": "contracts/support_triage.json",
      "on_violation": "quarantine",
      "wraps_prompt": "prompts/support_triage.md" }
  ],
  "edges": [
    { "from": "prompts/support_triage.md",
      "to": "evals/support_triage.yml", "kind": "evaluated_by" }
  ]
}
```

Edges use `{from, to, kind}` (matching dbt's lineage spec) so the JSON
reads like a graph spec. Adding optional fields is non-breaking; renames
or removals bump `schema_version`.

`prompt-lineage schema` prints the schema to stdout.

---

## CLI

```bash
prompt-lineage build [PATH]                     # scan + emit JSON + HTML site
prompt-lineage build [PATH] --out custom/       # custom output dir
prompt-lineage build [PATH] --json-only         # skip the HTML site
prompt-lineage diff main..HEAD                  # what changed (git refs)
prompt-lineage diff --before a.json --after b.json   # what changed (file refs)
prompt-lineage serve lineage-site/              # local http.server
prompt-lineage schema                           # print the lineage.json schema
prompt-lineage --version
```

Exit codes: `0` normal, `1` scan / IO error, `2` bad arguments / unparseable JSON.

---

## diff subcommand

`prompt-lineage diff main..HEAD` walks both refs, generates lineage for
each, prints a structured diff:

```
prompt-lineage diff

  prompt     [modified] prompts/support_triage.md
             model: claude-sonnet-4-6 -> claude-sonnet-4-7
             eval suites: [evals/support.yml] -> [evals/support.yml, evals/extra.yml]

  prompt     [added   ] prompts/new_classifier.md

  suite      [removed ] evals/old_suite.yml

3 change(s) -- 1 modified, 1 added, 1 removed
```

This is the cross-branch view a code reviewer needs: did this PR bump a
model alias? Did it add a prompt with no eval coverage? Did it delete a
suite that was covering production prompts?

The same output is what the GitHub Action posts as a sticky PR comment.

---

## GitHub Action

Drop this into your repo as `.github/workflows/lineage.yml`:

```yaml
name: prompt-lineage
on:
  pull_request:
    branches: [main]

permissions:
  pull-requests: write
  contents: read

jobs:
  lineage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }   # need history for git worktree
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install prompt-lineage
      - env: { GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
        run: |
          python -m prompt_lineage.github_action \
            --repo "${{ github.repository }}" \
            --pr "${{ github.event.pull_request.number }}" \
            --base "${{ github.base_ref }}"
```

The Action diffs `origin/<base>..HEAD`, then posts or updates a single
sticky PR comment (tagged with `<!-- prompt-lineage-bot -->`). Re-runs
update in place instead of stacking new comments.

---

## How the scan works

`prompt-lineage build` walks your repo and reads four sources, all
file-based -- no imports of user code, no network, no LLM calls:

1. **`prompts.yml`** (prompt-freshness manifest, if present) -> which
   `.md` files are declared prompts, their model alias, their
   warn/error thresholds.
2. **`.prompt-freshness/state.json`** (if present) -> last-evaluated
   timestamps. The classic prompt-freshness rule applies: an alias
   drift (e.g. `claude-sonnet-4-6 -> claude-sonnet-4-7`) marks the
   prompt stale even if the timestamp is recent.
3. **`evals/*.yml`** (dbt-eval suites) -> which prompts each suite
   covers, case count, assertion count.
4. **`**/*.py`** (AST walk) -> every `@prompt_contract(...)`
   decorator usage. The wrapped prompt is inferred from an explicit
   `prompt=` kwarg or from `.md` path string literals inside the
   function body.

Each tool's files are optional. Lineage degrades gracefully -- a repo
with only dbt-eval suites still produces a useful view; it just shows
freshness as "unevaluated" everywhere.

---

## Roadmap

v0.2 candidates:
- **Force-directed graph view** (the obvious next slot — the `lineage.json`
  schema is the contract that lets this ship without breaking adopters).
- **dbt-style column lineage** — for prompts that compose other prompts via
  templating.
- **Slack notifications** on diff (PR comment for code reviewers, Slack
  message for the on-call PM).
- **Multi-repo monorepo support** — scan multiple roots, merge into one
  lineage.
- **Cloud** — managed hosted version (lineage site at a stable URL,
  history graph of diffs over time).

---

## Compared to

- **[dbt-docs](https://docs.getdbt.com/docs/collaborate/documentation)** —
  the direct inspiration. dbt-docs is for SQL models; prompt-lineage is for
  prompt templates. The visual language is intentionally aligned.
- **CODEOWNERS** — both answer "this thing -> that responsibility." CODEOWNERS
  maps files to humans; prompt-lineage maps prompts to coverage.
- **[Datafold's data-diff](https://github.com/datafold/data-diff)** — the
  cross-branch lineage diff pattern. Their diff is over rows; ours is over
  the lineage graph.

---

## Status

v0.1 public alpha. ~1500 LOC Python. 78 tests. MIT licensed. No real LLM
calls anywhere in the codebase.

The schema (`lineage.json` shape) is the v0 commitment. The HTML view is
sortable + filterable but deliberately simple — force-directed graph
deferred to v0.2.

---

## License

MIT. See [LICENSE](./LICENSE).

---

## Author

[Harshith Uppula](https://github.com/uppulaharshith2-rgb) — founder of
[PipeCode](https://pipecode.ai) (data engineering interview platform).
`prompt-lineage` is the fourth in a four-repo dbt-style governance suite
for prompts, shipped in 24 hours alongside
[dbt-eval](https://github.com/uppulaharshith2-rgb/dbt-eval),
[prompt-contracts](https://github.com/uppulaharshith2-rgb/prompt-contracts),
and [prompt-freshness](https://github.com/uppulaharshith2-rgb/prompt-freshness).
