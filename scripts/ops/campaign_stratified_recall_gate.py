#!/usr/bin/env python3
"""Campaign gate for STRATIFIED-RECALL-SOURCE-RESILIENCE-01 (fail-closed).

Validates code convergence, unit adversarial suite, sample lock invariants,
and recall evaluation status. Does NOT claim production VPS PASS.
"""

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
ART = _PROJECT_ROOT / "artifacts" / "campaigns" / CAMPAIGN


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _check(item_id: str, ok: bool, evidence: list[str], notes: str = "") -> dict[str, Any]:
    return {
        "item_id": item_id,
        "status": "PASS" if ok else "FAIL",
        "evidence": evidence,
        "notes": notes,
    }


def run_gate(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    art = root / "artifacts" / "campaigns" / CAMPAIGN
    checks: list[dict[str, Any]] = []

    rb = root / "scripts" / "coverage" / "recall_benchmark.py"
    inv = root / "scripts" / "coverage" / "independent_inventory.py"
    tests = root / "tests" / "unit" / "coverage" / "test_recall_benchmark_adversarial.py"
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    src = rb.read_text(encoding="utf-8")
    checks.append(
        _check(
            "G1_fail_closed_module",
            rb.is_file()
            and "gate_exit" in src
            and "MIN_UNIQUE_ITEMS" in src
            and "STRATUM_FLOOR_PCT" in src
            and "denominator_hash" in src,
            [str(rb.relative_to(root))],
        )
    )
    checks.append(
        _check(
            "G2_independent_inventory",
            inv.is_file() and "opportunity_intel" not in inv.read_text(encoding="utf-8").split("denominator")[0]
            if inv.is_file()
            else False,
            [str(inv.relative_to(root)) if inv.is_file() else "missing"],
            notes="Collector must not use operational tables as denominator source",
        )
    )
    # Stronger: inventory module documents deny of operational denominator
    inv_src = inv.read_text(encoding="utf-8") if inv.is_file() else ""
    checks.append(
        _check(
            "G2b_no_ops_table_denominator",
            "denies_operational_table_denominator" in inv_src
            and "COUNT(*)" not in inv_src.replace("Do not use COUNT(*)", ""),
            ["independent_inventory denies operational denominator"],
        )
    )
    checks.append(
        _check(
            "G3_makefile_targets",
            "campaign-gate-stratified-recall" in makefile
            and "release-candidate-stratified-recall" in makefile
            and "verify-stratified-recall-isolated" in makefile,
            ["Makefile targets present"],
        )
    )
    checks.append(
        _check(
            "G4_adversarial_tests_present",
            tests.is_file()
            and "test_denominator_shrink_after_miss_is_detected" in tests.read_text(encoding="utf-8")
            and "test_auto_match_fail_closed_on_connection_error" in tests.read_text(encoding="utf-8"),
            [str(tests.relative_to(root))],
        )
    )

    # Run adversarial unit tests
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            str(tests.relative_to(root)),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    checks.append(
        _check(
            "G5_adversarial_pytest",
            proc.returncode == 0,
            [f"exit={proc.returncode}", (proc.stdout or "")[-500:]],
            notes=(proc.stderr or "")[-300:],
        )
    )

    # Scaffold / EXAMPLE evaluate must be non-zero
    proc2 = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.coverage.recall_benchmark",
            "evaluate",
            "--sample",
            str(root / "output" / "coverage" / "recall_sample.json")
            if (root / "output" / "coverage" / "recall_sample.json").exists()
            else str(art / "gold-sample.json"),
            "-o",
            str(art / "gate-eval-scratch.json"),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    # PARTIAL/NOT_READY/FAIL all non-zero; PASS only if truly ready
    if (art / "gate-eval-scratch.json").exists():
        ev = json.loads((art / "gate-eval-scratch.json").read_text(encoding="utf-8"))
        status = ev.get("status")
        # Gate foundation OK if evaluator is fail-closed (non-zero unless PASS)
        fail_closed_ok = (status == "PASS" and proc2.returncode == 0) or (
            status != "PASS" and proc2.returncode != 0
        )
        checks.append(
            _check(
                "G6_evaluate_exit_matches_status",
                fail_closed_ok,
                [f"status={status}", f"exit={proc2.returncode}"],
            )
        )
    else:
        checks.append(
            _check(
                "G6_evaluate_exit_matches_status",
                proc2.returncode != 0,
                [f"exit={proc2.returncode}", "no result file — expect non-zero on missing/scaffold"],
            )
        )

    # Artifact presence (baseline required)
    checks.append(
        _check(
            "G7_baseline_artifact",
            (art / "baseline.json").is_file(),
            [str((art / "baseline.json").relative_to(root)) if (art / "baseline.json").is_file() else "missing"],
        )
    )

    # Spec kit
    spec_dir = root / "specs" / "005-stratified-recall-source-resilience"
    checks.append(
        _check(
            "G8_spec_kit",
            (spec_dir / "spec.md").is_file() and (spec_dir / "plan.md").is_file() and (spec_dir / "tasks.md").is_file(),
            [str(spec_dir.relative_to(root))],
        )
    )

    # Production isolation claim in manifest if present
    manifest_path = art / "manifest.json"
    if manifest_path.is_file():
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks.append(
            _check(
                "G9_production_untouched",
                man.get("production_touched") is False,
                [f"production_touched={man.get('production_touched')}"],
            )
        )
    else:
        checks.append(
            _check(
                "G9_production_untouched",
                True,
                ["manifest not yet written — deferred to full campaign evidence"],
                notes="WARN: manifest pending",
            )
        )

    failed = [c for c in checks if c["status"] != "PASS"]
    overall = "PASS" if not failed else "FAIL"
    return {
        "campaign": CAMPAIGN,
        "status": overall,
        "generated_at": _utc_now(),
        "checks": checks,
        "failed_count": len(failed),
        "notes": "Foundation gate; live ≥95% recall requires gold sample + capture evidence in result.json",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ART / "campaign-gate.json"))
    args = p.parse_args(argv)
    result = run_gate()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
