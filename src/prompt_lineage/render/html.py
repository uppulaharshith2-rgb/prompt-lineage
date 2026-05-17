"""HTML site renderer: index.html, style.css, prompts/<slug>.html.

No JS framework. Vanilla sort/filter is inlined in index.html.j2. Pages
open via `file://`; no server required.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from prompt_lineage import SCHEMA_VERSION, __version__
from prompt_lineage.model import Lineage, Prompt

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _env() -> Environment:
    """Jinja env, autoescape on (prompt names are user-controlled paths)."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        keep_trailing_newline=True,
    )


def build_site(
    lineage: Lineage,
    out_dir: str | Path,
    *,
    project_root: Optional[Path] = None,
) -> Path:
    """Render `lineage` to `out_dir`. Returns the output directory path.

    project_root is used to read the original prompt markdown to inline an
    excerpt in the prompt detail page. If None, no excerpt is shown."""
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    prompts_dir = out / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    # Copy the single CSS file so the site is self-contained.
    shutil.copy(STATIC_DIR / "style.css", out / "style.css")

    env = _env()
    base_ctx = {
        "counts": lineage.counts(),
        "generated_at_display": (lineage.generated_at or "").replace("T", " ").split(".")[0],
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
    }

    # index.html
    idx_tpl = env.get_template("index.html.j2")
    (out / "index.html").write_text(
        idx_tpl.render(
            page_title="prompt-lineage",
            root_prefix="",
            prompts=lineage.prompts,
            suites=lineage.suites,
            contracts=lineage.contracts,
            **base_ctx,
        )
    )

    # per-prompt detail pages
    detail_tpl = env.get_template("prompt.html.j2")
    for p in lineage.prompts:
        slug = p.id.replace("/", "__")
        excerpt = _read_prompt_excerpt(project_root, p) if project_root else None
        (prompts_dir / f"{slug}.html").write_text(
            detail_tpl.render(
                page_title=f"{p.id} | prompt-lineage",
                root_prefix="../",
                prompt=p,
                source_excerpt=excerpt,
                **base_ctx,
            )
        )

    return out


def _read_prompt_excerpt(
    project_root: Optional[Path], prompt: Prompt, max_lines: int = 40
) -> Optional[str]:
    """First N lines of the prompt file for the detail page. Capped so a
    huge prompt doesn't bloat the HTML."""
    if not project_root:
        return None
    candidate = project_root / prompt.path
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        text = candidate.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
