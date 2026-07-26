#!/usr/bin/env python3
"""Makefile-backed CONFENGE gate helpers (real checks, no silent green)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
RUN = ART / "run" / "run-result.json"


def _load_run() -> dict[str, Any]:
    if not RUN.is_file():
        return {}
    return json.loads(RUN.read_text(encoding="utf-8"))


def cmd_full_candidate_history(_: argparse.Namespace) -> int:
    d = _load_run()
    lm = d.get("load_meta") or {}
    ok = (
        lm.get("history_expansion_mode") == "FULL_CANDIDATE_HISTORY"
        and lm.get("history_is_full") is True
        and not lm.get("per_supplier_limit")
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "history_expansion_mode": lm.get("history_expansion_mode"),
                "history_is_full": lm.get("history_is_full"),
                "mismatches": lm.get("snapshot_count_mismatch_n"),
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def cmd_registry_coverage(_: argparse.Namespace) -> int:
    d = _load_run()
    cov = d.get("registry_coverage") or (d.get("metrics") or {}).get("registry_coverage") or {}
    t20 = cov.get("registry_coverage_top20") or {}
    ok = bool(cov.get("top20_coverage_100pct"))
    print(json.dumps({"ok": ok, "top20": t20, "block": cov.get("block_reason")}, indent=2))
    return 0 if ok else 2


def cmd_full_population(_: argparse.Namespace) -> int:
    d = _load_run()
    mode = d.get("population_mode")
    disc = d.get("discovery_mode")
    hist = d.get("history_expansion_mode")
    lim = (d.get("load_meta") or {}).get("limit_applied") or (d.get("metrics") or {}).get(
        "limit_applied"
    )
    ok = mode == "FULL_POPULATION" and not lim and hist == "FULL_CANDIDATE_HISTORY"
    print(
        {
            "population_mode": mode,
            "discovery_mode": disc,
            "history_expansion_mode": hist,
            "limit_applied": lim,
            "ok": ok,
        }
    )
    return 0 if ok else 1


def cmd_prefilter_recall(_: argparse.Namespace) -> int:
    p = ART / "prefilter-recall.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    recall = d.get("candidate_discovery_recall")
    ok = recall is not None and float(recall) >= 0.95
    print(d if d else {"status": "BLOCKED_PREFILTER_RECALL_NOT_PROVEN"})
    return 0 if ok else 2


def cmd_ranking_quality(_: argparse.Namespace) -> int:
    d = _load_run()
    leads = d.get("leads") or []
    top = leads[:10]
    oos = sum(1 for L in top if L.get("supplier_sector_fit") == "OUT_OF_SCOPE")
    strong = (
        all(
            L.get("supplier_sector_fit")
            in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT")
            for L in top
        )
        if top
        else False
    )
    print({"top10": len(top), "oos": oos, "strong": strong})
    return 0 if strong and oos == 0 and top else 1


def cmd_ranking_stability(_: argparse.Namespace) -> int:
    p = ART / "ranking-stability.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    print(d)
    return 0 if d.get("ok") else 1


def cmd_baseline_superiority(_: argparse.Namespace) -> int:
    d = _load_run()
    b = d.get("baseline_comparison") or {}
    hm = d.get("human_metrics") or {}
    if hm.get("human_review_status") != "COMPLETE" or hm.get("precision_at_10") is None:
        print(
            {
                "ok": False,
                "status": "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
                "baseline": b,
            }
        )
        return 2
    print(b)
    return 0 if b.get("proposed_better") else 1


def cmd_package_evidence(_: argparse.Namespace) -> int:
    out = ART / "evidence-package"
    out.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
    ).strip()
    files = [
        "result.json",
        "queue-summary.json",
        "denominator-integrity.json",
        "contract-relevance-holdout.json",
        "gold-standard-baseline.json",
    ]
    checks: dict[str, Any] = {}
    for f in files:
        p = ART / f
        checks[f] = {
            "exists": p.is_file(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        }
    pkg = {
        "executed_git_sha": sha,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "created_at": datetime.now(UTC).isoformat(),
        "checksums": checks,
        "note": "execution artifacts; not self-referential commit SHA of this package",
    }
    (out / "attestation.json").write_text(
        json.dumps(pkg, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(pkg, indent=2))
    return 0


def cmd_verify_attestation(_: argparse.Namespace) -> int:
    p = ART / "evidence-package" / "attestation.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    head = subprocess.check_output(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
    ).strip()
    ok = d.get("executed_git_sha") == head and all(
        (d.get("checksums") or {}).get(f, {}).get("exists")
        for f in ["gold-standard-baseline.json"]
    )
    print({"ok": ok, "executed": d.get("executed_git_sha"), "head": head})
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mapping = {
        "full-candidate-history": cmd_full_candidate_history,
        "registry-coverage": cmd_registry_coverage,
        "full-population": cmd_full_population,
        "prefilter-recall": cmd_prefilter_recall,
        "ranking-quality": cmd_ranking_quality,
        "ranking-stability": cmd_ranking_stability,
        "baseline-superiority": cmd_baseline_superiority,
        "package-evidence": cmd_package_evidence,
        "verify-attestation": cmd_verify_attestation,
    }
    for name in mapping:
        sub.add_parser(name)
    args = ap.parse_args(argv)
    return mapping[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
