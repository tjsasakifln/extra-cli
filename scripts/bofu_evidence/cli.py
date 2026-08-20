"""CLI: python3 -m scripts.bofu_evidence --out DIR [--as-of ISO]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.bofu_evidence.fixtures import load_comparable, load_national_coverage, load_snapshot
from scripts.bofu_evidence.models import SCHEMA, BofuInputError
from scripts.bofu_evidence.producer import build_packs, write_packs


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BofuInputError(f"missing_input:{path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build public-read-bofu-evidence/1.0 packs (producer-only).")
    parser.add_argument("--out", required=True, help="Output directory for the versioned pack")
    parser.add_argument(
        "--as-of",
        default=None,
        help="Frozen snapshot cutoff (default: snapshot as_of, never wall-clock)",
    )
    parser.add_argument("--now", default=None, help="Evaluation clock (frozen or wall-clock ISO)")
    parser.add_argument("--as-of-source", default=None)
    parser.add_argument("--snapshot", default=None, help="Versioned snapshot JSON")
    parser.add_argument("--national-coverage", default=None, help="Versioned #437 evaluate payload")
    parser.add_argument("--comparable", default=None, help="Versioned #435 comparable payload")
    parser.add_argument(
        "--synthetic-fixture",
        action="store_true",
        help="Allow frozen test fixtures. Forbidden as live authority.",
    )
    args = parser.parse_args(argv)

    synthetic = bool(args.synthetic_fixture)
    if not synthetic and (not args.snapshot or not args.national_coverage):
        raise BofuInputError("missing_input:snapshot_or_national_coverage")
    snapshot = load_snapshot(Path(args.snapshot)) if args.snapshot else (load_snapshot() if synthetic else None)
    coverage = (
        _load_json(args.national_coverage)
        if args.national_coverage
        else (load_national_coverage() if synthetic else None)
    )
    comparable = _load_json(args.comparable) if args.comparable else (load_comparable() if synthetic else None)
    as_of = args.as_of or (snapshot or {}).get("as_of")
    bundle = build_packs(
        snapshot=snapshot,
        national_coverage=coverage,
        comparable=comparable,
        as_of=as_of,
        now=args.now,
        as_of_source=args.as_of_source,
        synthetic=synthetic,
    )
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
