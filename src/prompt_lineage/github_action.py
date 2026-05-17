"""GitHub Action runner: posts/updates a sticky PR comment with the lineage diff.

    python -m prompt_lineage.github_action --repo OWNER/REPO --pr 42 --base main

Stickiness: comment tagged with `<!-- prompt-lineage-bot -->`; the runner
finds and updates it in place each PR push instead of stacking new comments.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from prompt_lineage.diff import GitDiffError, diff_lineages, lineage_at_ref
from prompt_lineage.scanner import ScanError


COMMENT_MARKER = "<!-- prompt-lineage-bot -->"


def run_action(
    repo: str, pr_number: str, base_ref: str, repo_root: str = ".",
) -> int:
    """Build the diff and post/update the PR comment. Returns process exit code."""
    full_base = f"origin/{base_ref}" if "/" not in base_ref else base_ref

    try:
        before = lineage_at_ref(repo_root, full_base)
        # HEAD here means the workflow's checked-out commit; scan it in-place.
        from prompt_lineage.scanner import scan
        after = scan(repo_root)
    except (GitDiffError, ScanError) as exc:
        sys.stderr.write(f"prompt-lineage action: {exc}\n")
        return 1

    report = diff_lineages(before, after)

    if not report.has_changes:
        body = (
            COMMENT_MARKER
            + "\n## prompt-lineage diff\n\n"
            + "_No lineage changes in this PR._\n"
        )
    else:
        body = COMMENT_MARKER + "\n" + report.as_markdown()

    return _post_or_update_comment(repo, pr_number, body)


def _post_or_update_comment(repo: str, pr_number: str, body: str) -> int:
    """Use `gh` CLI for marker-find + update/create. Falls back to printing
    the body if `gh` isn't installed (still lands in action logs)."""
    if not _have_gh():
        sys.stderr.write(
            "prompt-lineage: gh CLI not available; printing diff to stdout\n"
        )
        sys.stdout.write(body + "\n")
        return 0

    existing_id = _find_existing_comment(repo, pr_number)
    try:
        if existing_id is not None:
            subprocess.run(
                ["gh", "api", "--method", "PATCH",
                 f"repos/{repo}/issues/comments/{existing_id}",
                 "-f", f"body={body}"],
                check=True, capture_output=True, text=True,
            )
        else:
            subprocess.run(
                ["gh", "pr", "comment", str(pr_number),
                 "-R", repo, "--body", body],
                check=True, capture_output=True, text=True,
            )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"prompt-lineage: gh command failed: {exc.stderr.strip()}\n"
        )
        return 1
    return 0


def _have_gh() -> bool:
    try:
        subprocess.run(
            ["gh", "--version"], check=True, capture_output=True, text=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _find_existing_comment(repo: str, pr_number: str) -> str | None:
    """Return the id of the existing sticky comment, or None."""
    try:
        result = subprocess.run(
            ["gh", "api",
             f"repos/{repo}/issues/{pr_number}/comments",
             "--paginate", "--jq",
             f'.[] | select(.body | startswith("{COMMENT_MARKER}")) | .id'],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError:
        return None
    ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return ids[0] if ids else None  # duplicates: first-match wins (one-shot cleanup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m prompt_lineage.github_action",
        description="Run prompt-lineage as a GitHub Action: diff and post a PR comment.",
    )
    parser.add_argument("--repo", required=True, help="owner/repo (e.g. acme/widgets)")
    parser.add_argument("--pr", required=True, help="PR number")
    parser.add_argument(
        "--base", default=os.environ.get("GITHUB_BASE_REF", "main"),
        help="Base ref to diff against (default: $GITHUB_BASE_REF or 'main')",
    )
    parser.add_argument(
        "--repo-root", default=".", help="Path to checked-out repo (default: .)",
    )
    args = parser.parse_args(argv)
    return run_action(args.repo, args.pr, args.base, repo_root=args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
