"""CLI: python3 -m scripts.bofu_evidence --out DIR [--as-of ISO]."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts.bofu_evidence.fixtures import load_snapshot
from scripts.bofu_evidence.models import SCHEMA
from scripts.bofu_evidence.producer import build_packs, write_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build public-read-bofu-evidence/1.0 packs (producer-only).")
    parser.add_argument("--out", required=True, help="Output directory for the versioned pack")
    parser.add_argument(
        "--as-of",
        default=None,
        help="Frozen snapshot cutoff (default: snapshot as_of, never wall-clock)",
    )
    args = parser.parse_args(argv)

    snapshot = load_snapshot()
    as_of = args.as_of or snapshot["as_of"]
    bundle = build_packs(snapshot=snapshot, as_of=as_of)
    dest = write_packs(bundle, args.out)
    payload: dict[str, Any] = {
        "ok": True,
        "out": str(dest),
        "schema": SCHEMA,
        "as_of": bundle["as_of"],
        "pack_count": len(bundle["packs"]),
        "pack_ids": [item["pack_id"] for item in bundle["packs"]],
        "states": {item["family"]: item["state"] for item in bundle["packs"]},
        "hashes": {item["pack_id"]: item["content_hash"] for item in bundle["packs"]},
        "publication": False,
        "index": False,
        "national": False,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return 0
