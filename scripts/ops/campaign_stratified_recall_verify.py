#!/usr/bin/env python3
"""Isolated verify for stratified recall campaign.

Runs sample validation, lock integrity, evaluate (fail-closed), and optional
auto-match against RECALL_ISOLATED_DSN / --dsn only. Never uses production DSN
heuristics (ec-prod, /opt/extra-consultoria).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.recall_benchmark import (  # noqa: E402
    assert_denominator_unchanged,
    evaluate_sample,
    try_match_against_system,
    validate_sample_schema,
)

CAMPAIGN = "STRATIFIED-RECALL-SOURCE-RESILIENCE-01"
FORBIDDEN_DSN = re.compile(r"ec-prod|/opt/extra-consultoria|5432.*(prod|vps)", re.I)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_verify(
    *,
    sample_path: Path,
    lock_path: Path | None,
    dsn: str | None,
    auto_match: bool,
    art: Path,
) -> dict[str, Any]:
    production_touched = False
    errors: list[str] = []

    if dsn and FORBIDDEN_DSN.search(dsn):
        return {
            "status": "FAIL",
            "production_touched": True,
            "error": "DSN looks like production — refused",
            "generated_at": _utc_now(),
        }

    if not sample_path.is_file():
        return {
            "status": "NOT_READY",
            "production_touched": False,
            "error": f"missing sample {sample_path}",
            "generated_at": _utc_now(),
        }

    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    validation = validate_sample_schema(sample)
    lock = None
    if lock_path and lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        try:
            assert_denominator_unchanged(sample, lock)
        except RuntimeError as exc:
            errors.append(str(exc))

    match_error = None
    if auto_match:
        try:
            sample = try_match_against_system(sample, dsn=dsn, fail_closed=True)
            sample_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except RuntimeError as exc:
            match_error = str(exc)
            errors.append(match_error)

    if lock:
        try:
            assert_denominator_unchanged(sample, lock)
        except RuntimeError as exc:
            errors.append(str(exc))

    result = evaluate_sample(sample)
    recall_path = art / "recall.json"
    recall_path.parent.mkdir(parents=True, exist_ok=True)
    recall_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_stratum = {
        "strata_coverage": result.get("strata_coverage"),
        "stratum_pct": result.get("stratum_pct"),
        "floors_failed": result.get("floors_failed"),
        "stratum_floor_pct": result.get("stratum_floor_pct"),
        "denominator_hash": result.get("denominator_hash"),
    }
    (art / "recall-by-stratum.json").write_text(
        json.dumps(by_stratum, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    misses = [
        {
            "sample_id": i.get("sample_id"),
            "external_id": i.get("external_id"),
            "portal_url": i.get("portal_url"),
            "source_platform": i.get("source_platform"),
            "miss_reason": i.get("miss_reason"),
            "strata": i.get("strata"),
        }
        for i in (sample.get("portal_items") or [])
        if i.get("captured_by_system") is False
    ]
    (art / "misses.json").write_text(json.dumps({"misses": misses, "count": len(misses)}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    status = result.get("status")
    if errors and status == "PASS":
        status = "FAIL"
    if match_error and status not in {"FAIL", "NOT_READY"}:
        status = "NOT_READY"

    out = {
        "campaign": CAMPAIGN,
        "status": status,
        "production_touched": production_touched,
        "generated_at": _utc_now(),
        "sample": str(sample_path),
        "validation": validation,
        "recall": {
            "status": result.get("status"),
            "pct": result.get("pct"),
            "captured": result.get("captured"),
            "published_in_sample": result.get("published_in_sample"),
            "denominator_hash": result.get("denominator_hash"),
            "forbidden_proxy_used": result.get("forbidden_proxy_used"),
            "gate_exit": result.get("gate_exit"),
        },
        "miss_count": len(misses),
        "errors": errors,
        "dsn_used": bool(dsn),
        "auto_match": auto_match,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    art_default = _PROJECT_ROOT / "artifacts" / "campaigns" / CAMPAIGN
    p = argparse.ArgumentParser()
    p.add_argument("--sample", default=str(art_default / "gold-sample.json"))
    p.add_argument("--lock", default=str(art_default / "sample-lock.json"))
    p.add_argument("--dsn", default=os.getenv("RECALL_ISOLATED_DSN") or os.getenv("LOCAL_DATALAKE_DSN"))
    p.add_argument("--auto-match", action="store_true")
    p.add_argument("--out", default=str(art_default / "verify-isolated.json"))
    args = p.parse_args(argv)

    art = Path(args.out).parent
    result = run_verify(
        sample_path=Path(args.sample),
        lock_path=Path(args.lock) if args.lock else None,
        dsn=args.dsn,
        auto_match=args.auto_match,
        art=art,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("production_touched"):
        return 3
    status = result.get("status")
    if status == "PASS":
        return 0
    if status in {"NOT_READY", "PARTIAL", "BLOCKED"}:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
