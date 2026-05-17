"""HTML renderer: produces a self-contained static site."""
from __future__ import annotations

from prompt_lineage.render.html import build_site
from prompt_lineage.scanner import scan


def test_build_site_writes_index_and_css(tmp_path, example_project):
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    assert (out / "index.html").is_file()
    assert (out / "style.css").is_file()


def test_build_site_writes_per_prompt_pages(tmp_path, example_project):
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    prompts_dir = out / "prompts"
    assert prompts_dir.is_dir()
    pages = sorted(p.name for p in prompts_dir.glob("*.html"))
    assert "prompts__support_triage.md.html" in pages
    assert "prompts__extract_invoice.md.html" in pages


def test_index_contains_prompt_ids(tmp_path, example_project):
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    body = (out / "index.html").read_text()
    assert "prompts/support_triage.md" in body
    assert "prompts/extract_invoice.md" in body


def test_index_contains_filter_buttons(tmp_path, example_project):
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    body = (out / "index.html").read_text()
    for filt in ("fresh", "warning", "stale", "unevaluated", "uncovered", "unenforced"):
        assert f'data-filter="{filt}"' in body, filt


def test_index_contains_sort_script(tmp_path, example_project):
    """The sort/filter JS must be inlined (no external <script src>)."""
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    body = (out / "index.html").read_text()
    assert "data-sort" in body
    assert "<script>" in body
    assert "src=" not in body.split("<script>")[1].split("</script>")[0]


def test_prompt_page_includes_source_excerpt(tmp_path, example_project):
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=example_project)
    page = (out / "prompts" / "prompts__support_triage.md.html").read_text()
    assert "# Support" in page or "Support" in page


def test_build_site_works_without_project_root(tmp_path, example_project):
    """`project_root=None` is allowed; the detail pages just skip the excerpt."""
    lineage = scan(example_project)
    out = build_site(lineage, tmp_path / "site", project_root=None)
    assert (out / "prompts" / "prompts__support_triage.md.html").is_file()
