#!/usr/bin/env python3
"""Release-candidate JSON for stratified recall campaign (fail-closed)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CAMPAIGN = "STRATIFIED-RECALL-SOURCE-RESILIENCE-01"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha(root: Path) -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()  # noqa: S607
        )
    except Exception:
        return "unknown"


def build_rc(root: Path) -> dict[str, Any]:
    art = root / "artifacts" / "campaigns" / CAMPAIGN
    pieces: dict[str, Any] = {}
    for name in (
        "baseline.json",
        "manifest.json",
        "recall.json",
        "sample-lock.json",
        "campaign-gate.json",
        "verify-isolated.json",
        "result.json",
    ):
        path = art / name
        if path.is_file():
            try:
                pieces[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pieces[name] = {"error": "invalid_json"}

    gate = pieces.get("campaign-gate.json") or {}
    recall = pieces.get("recall.json") or {}
    manifest = pieces.get("manifest.json") or {}
    result = pieces.get("result.json") or {}

    production_ok = manifest.get("production_touched") is False or not manifest
    gate_ok = gate.get("status") == "PASS"
    recall_status = recall.get("status") or result.get("status")
    recall_pass = recall_status == "PASS"

    if not gate_ok:
        status = "FAIL"
    elif not production_ok:
        status = "FAIL"
    elif recall_pass:
        status = "PASS"
    elif recall_status in {"BLOCKED", "PARTIAL", "NOT_READY"}:
        status = "BLOCKED"
    elif recall_status == "FAIL":
        status = "FAIL"
    else:
        status = "BLOCKED"

    return {
        "campaign": CAMPAIGN,
        "status": status,
        "sha": _git_sha(root),
        "generated_at": _utc_now(),
        "gate_status": gate.get("status"),
        "recall_status": recall_status,
        "recall_pct": recall.get("pct") or (result.get("recall") or {}).get("pct"),
        "production_touched": manifest.get("production_touched", None),
        "artifacts_present": sorted(pieces.keys()),
        "notes": (
            "RC PASS requires foundation gate PASS + recall PASS + production_touched=false. "
            "BLOCKED when gold/capture incomplete but foundation holds."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        default=str(
            _PROJECT_ROOT / "artifacts" / "campaigns" / CAMPAIGN / "release-candidate.json"
        ),
    )
    args = p.parse_args(argv)
    rc = build_rc(_PROJECT_ROOT)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(rc, indent=2, ensure_ascii=False))
    if rc["status"] == "PASS":
        return 0
    if rc["status"] == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
