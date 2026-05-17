"""prompt-lineage CLI.

Subcommands:
  build     scan a project, emit lineage.json + static HTML site
  diff      compare two scans (file paths or git ref pair)
  serve     local http.server wrapper for the built site
  schema    print the lineage.json schema doc

Exit codes:
  0  success
  1  scan / IO error
  2  bad CLI arguments / unparseable JSON
"""
from __future__ import annotations

import http.server
import json
import socketserver
import sys
from pathlib import Path
from typing import Optional

import click

from prompt_lineage import __version__, SCHEMA_VERSION
from prompt_lineage.diff import (
    GitDiffError, diff_lineages, lineage_at_ref, parse_ref_pair,
)
from prompt_lineage.model import (
    Contract, Edge, FreshnessInfo, Lineage, Prompt, Suite,
)
from prompt_lineage.render.html import build_site
from prompt_lineage.render.json import to_json
from prompt_lineage.scanner import ScanError, scan


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", "-V", prog_name="prompt-lineage")
def main() -> None:
    """dbt-docs for prompts. See https://github.com/uppulaharshith2-rgb/prompt-lineage"""


@main.command("build")
@click.argument("path", type=click.Path(), default=".")
@click.option(
    "--out", "out_dir", type=click.Path(file_okay=False), default="lineage-site",
    help="Output directory (default: lineage-site).",
)
@click.option("--json-only", is_flag=True, help="Emit only lineage.json (skip HTML).")
@click.option("--quiet", is_flag=True, help="Suppress the summary line.")
def build_cmd(path: str, out_dir: str, json_only: bool, quiet: bool) -> None:
    """Scan PATH and emit lineage.json (+ HTML site unless --json-only)."""
    try:
        lineage = scan(path)
    except ScanError as exc:
        click.echo(f"scan error: {exc}", err=True)
        sys.exit(1)

    project_root = Path(path).expanduser().resolve()

    if json_only:
        out_file = Path(out_dir).expanduser().resolve()
        if out_file.suffix != ".json":
            out_file.mkdir(parents=True, exist_ok=True)
            out_file = out_file / "lineage.json"
        else:
            out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(to_json(lineage))
        if not quiet:
            click.echo(f"wrote {out_file}")
        return

    out_path = build_site(lineage, out_dir, project_root=project_root)
    (out_path / "lineage.json").write_text(to_json(lineage))

    if not quiet:
        counts = lineage.counts()
        click.echo(
            f"built {counts['prompts']} prompts, "
            f"{counts['suites']} suites, "
            f"{counts['contracts']} contracts -> {out_path}/"
        )
        click.echo(f"  open {out_path}/index.html")


@main.command("diff")
@click.argument("refs", required=False, default=None)
@click.option(
    "--before", type=click.Path(exists=True, dir_okay=False), default=None,
    help="Path to a previous lineage.json. Pairs with --after.",
)
@click.option(
    "--after", type=click.Path(exists=True, dir_okay=False), default=None,
    help="Path to a current lineage.json. Pairs with --before.",
)
@click.option(
    "--repo", type=click.Path(file_okay=False), default=".",
    help="Repo root for git-ref mode (default: current directory).",
)
@click.option(
    "--path", "sub_path", type=str, default=".",
    help="Subdirectory inside the repo to scan (default: repo root).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of text.")
@click.option(
    "--markdown", type=click.Path(dir_okay=False, writable=True), default=None,
    help="Also write a Markdown report to this path.",
)
def diff_cmd(
    refs: Optional[str], before: Optional[str], after: Optional[str],
    repo: str, sub_path: str, as_json: bool, markdown: Optional[str],
) -> None:
    """Compare two lineages. Two input modes:

    \b
      prompt-lineage diff main..HEAD             # git refs
      prompt-lineage diff --before a.json --after b.json
    """
    if refs and (before or after):
        click.echo("error: pass REFS or --before/--after, not both", err=True)
        sys.exit(2)
    if not refs and not (before and after):
        click.echo(
            "error: pass REFS like 'main..HEAD' OR --before AND --after", err=True,
        )
        sys.exit(2)

    if refs:
        try:
            base_ref, head_ref = parse_ref_pair(refs)
        except ValueError as exc:
            click.echo(f"error: {exc}", err=True)
            sys.exit(2)
        try:
            before_l = lineage_at_ref(repo, base_ref, sub_path=sub_path)
            after_l = lineage_at_ref(repo, head_ref, sub_path=sub_path)
        except (GitDiffError, ScanError) as exc:
            click.echo(f"error: {exc}", err=True)
            sys.exit(1)
    else:
        try:
            before_l = lineage_from_dict(json.loads(Path(before).read_text()))
            after_l = lineage_from_dict(json.loads(Path(after).read_text()))
        except (json.JSONDecodeError, KeyError) as exc:
            click.echo(f"error: failed to parse lineage JSON: {exc}", err=True)
            sys.exit(2)

    report = diff_lineages(before_l, after_l)

    if as_json:
        click.echo(json.dumps(report.as_dict(), indent=2))
    else:
        click.echo(report.as_terminal())

    if markdown:
        Path(markdown).write_text(report.as_markdown())
        click.echo(f"wrote markdown report -> {markdown}", err=True)


@main.command("serve")
@click.argument("path", type=click.Path(file_okay=False), default="lineage-site")
@click.option("--port", type=int, default=8765, help="HTTP port (default: 8765).")
def serve_cmd(path: str, port: int) -> None:
    """Start a local HTTP server for PATH."""
    serve_dir = Path(path).expanduser().resolve()
    if not serve_dir.is_dir():
        click.echo(
            f"error: {serve_dir} is not a directory. "
            "Did you run `prompt-lineage build` first?", err=True,
        )
        sys.exit(1)

    class _Handler(http.server.SimpleHTTPRequestHandler):
        # Pin the directory so we don't expose the CWD by accident.
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            sys.stderr.write(f"  {self.address_string()} {format % args}\n")

    with socketserver.TCPServer(("127.0.0.1", port), _Handler) as httpd:
        click.echo(f"serving {serve_dir} at http://127.0.0.1:{port}/")
        click.echo("ctrl-c to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nstopped")


_SCHEMA_DOC = """\
Top-level keys:
  schema_version  '0.1'
  generated_at    ISO8601 timestamp
  root_path       absolute path of the scan root
  counts          {prompts, suites, contracts, edges, uncovered_prompts, unenforced_prompts}
  prompts[]       {id, path, last_modified, model_alias, evaluated_by[], enforced_by[], freshness?}
  suites[]        {id, covers_prompts[], assertions, cases}
  contracts[]     {id, source_path, func_name, schema_ref, on_violation, wraps_prompt}
  edges[]         {from, to, kind}   kind in {evaluated_by, enforced_by, covers, wraps}"""


@main.command("schema")
def schema_cmd() -> None:
    """Print the lineage.json schema doc."""
    click.echo(f"prompt-lineage schema version {SCHEMA_VERSION}\n\n{_SCHEMA_DOC}")


def lineage_from_dict(data: dict) -> Lineage:
    """Reconstruct a Lineage from a serialized dict. CLI-side only -- adopters
    using the JSON schema directly are expected to roll their own loader."""

    def _p(d):
        f = d.get("freshness")
        return Prompt(
            id=d["id"], path=d["path"],
            last_modified=d.get("last_modified"),
            model_alias=d.get("model_alias"),
            evaluated_by=list(d.get("evaluated_by", [])),
            enforced_by=list(d.get("enforced_by", [])),
            freshness=FreshnessInfo(**f) if f else None,
        )

    return Lineage(
        prompts=[_p(p) for p in data.get("prompts", [])],
        suites=[Suite(**s) for s in data.get("suites", [])],
        contracts=[Contract(**c) for c in data.get("contracts", [])],
        edges=[
            Edge(src=e["from"], dst=e["to"], kind=e["kind"])
            for e in data.get("edges", [])
        ],
        generated_at=data.get("generated_at"),
        root_path=data.get("root_path"),
    )


if __name__ == "__main__":
    main()
