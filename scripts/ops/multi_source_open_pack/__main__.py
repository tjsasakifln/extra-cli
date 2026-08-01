"""CLI: python3 -m scripts.ops.multi_source_open_pack"""

from __future__ import annotations

from scripts.ops.multi_source_open_pack.pipeline import run_pack_cli

if __name__ == "__main__":
    raise SystemExit(run_pack_cli())
