"""Durable pSEO export entry.

Canonical: python -m scripts.pseo.cli_export
"""
from __future__ import annotations
from scripts.pseo.pipeline import main
if __name__ == '__main__':
    raise SystemExit(main())
