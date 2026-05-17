"""prompt-lineage: dbt-docs for prompts.

v0 surface:
  - scanner.scan(path)            -> Lineage
  - model.Lineage                 (dataclass; serializable)
  - render.json.to_json(lineage)  (THIS IS THE SCHEMA THAT LOCKS IN)
  - render.html.build_site(lineage, out_dir)
  - diff.diff_lineages(a, b)      -> DiffReport
"""
from __future__ import annotations

__version__ = "0.1.0"
SCHEMA_VERSION = "0.1"

__all__ = ["__version__", "SCHEMA_VERSION"]
