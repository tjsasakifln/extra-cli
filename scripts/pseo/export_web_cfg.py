"""Canonical public export for web-cfg pSEO (durable pipeline).

Usage (equivalent):
  python -m scripts.pseo.export_web_cfg --out /path/to/webcfg/data/pseo --as-of YYYY-MM-DD --validate
  python -m scripts.pseo.cli_export --out /path/to/webcfg/data/pseo --as-of YYYY-MM-DD --validate
  python -m scripts.pseo ...

Delegates to scripts.pseo.pipeline (multi-layer classifier, open-status filter,
comparison groups, PNCP deep-links, provenance/hash validation).
"""
from __future__ import annotations

from scripts.pseo.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
