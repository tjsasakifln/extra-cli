#!/usr/bin/env python3
"""Regenerate ARCH-RESET baseline inventory JSON (docs/ops evidence).

Does not change product behavior. Safe to run on any clean checkout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sh(root: Path, *args: str) -> str:
    # Fixed argv from trusted callers (git inventory only).
    return subprocess.check_output(  # noqa: S603
        list(args), text=True, cwd=root
    ).strip()


def _count_lines(root: Path, paths: list[str]) -> int:
    total = 0
    for rel in paths:
        fp = root / rel
        if not fp.is_file():
            continue
        try:
            with fp.open("rb") as fh:
                total += sum(1 for _ in fh)
        except OSError:
            continue
    return total


def build_baseline(root: Path) -> dict[str, Any]:
    main_sha = _sh(root, "git", "rev-parse", "HEAD")
    main_short = _sh(root, "git", "rev-parse", "--short", "HEAD")
    main_subject = _sh(root, "git", "log", "-1", "--format=%s")
    files = _sh(root, "git", "ls-tree", "-r", "HEAD", "--name-only").splitlines()
    py_scripts = [f for f in files if f.startswith("scripts/") and f.endswith(".py")]
    py_tests = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
    migrations = [
        f for f in files if f.startswith("db/migrations/") and f.endswith(".sql")
    ]
    adrs = [
        f
        for f in files
        if f.startswith("docs/architecture/adr/")
        and f.endswith(".md")
        and "INDEX" not in f
    ]
    workflows = [f for f in files if f.startswith(".github/workflows/")]

    makefile = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    targets = sorted(set(re.findall(r"^([a-zA-Z0-9_.-]+):", makefile, flags=re.M)))

    product_entrypoints = {
        "extra-weekly": {
            "impl": "python3 -m scripts.ops.weekly_cycle --strict",
            "class": "canonical",
        },
        "golden-path": {
            "impl": "python scripts/golden_path.py",
            "class": "diagnostic",
        },
        "run-pipeline": {
            "impl": "bootstrap + crawl + intel_pipeline + report",
            "class": "legacy_composite",
        },
        "report-executivo": {
            "impl": "scripts/reports/executive_report.py + executive_excel.py",
            "class": "component",
        },
        "resilient-local-cycle": {
            "impl": "scripts.ops.resilient_cycle --env fixture",
            "class": "diagnostic",
        },
        "force-next": {
            "impl": "squads/extra-dod-roi/scripts/cli.py force-next",
            "class": "campaign_governance",
        },
    }

    orchestrators = [
        {
            "id": "weekly_cycle",
            "path": "scripts/ops/weekly_cycle.py",
            "role": "canonical_product",
        },
        {
            "id": "golden_path",
            "path": "scripts/golden_path.py",
            "role": "diagnostic_validation",
        },
        {
            "id": "resilient_cycle",
            "path": "scripts/ops/resilient_cycle.py",
            "role": "resilience_fixture",
        },
        {
            "id": "run_pipeline_make",
            "path": "Makefile:run-pipeline",
            "role": "legacy_composite",
        },
        {
            "id": "intel_pipeline",
            "path": "scripts/intel_pipeline.py",
            "role": "intel_component",
        },
        {
            "id": "opportunity_intel_cli",
            "path": "scripts/opportunity_intel/cli.py",
            "role": "intel_component",
        },
        {
            "id": "workspace_cli",
            "path": "scripts/workspace/cli.py",
            "role": "operator_facade",
        },
        {
            "id": "extra_dod_roi",
            "path": "squads/extra-dod-roi/scripts/cli.py",
            "role": "campaign_governance",
        },
    ]

    def existing(paths: list[str]) -> list[str]:
        return [p for p in paths if (root / p).exists()]

    coverage_impls = existing(
        [
            "scripts/coverage/coverage_contract.py",
            "scripts/coverage_gate.py",
            "scripts/coverage_truth.py",
            "scripts/coverage/multi_source_coverage.py",
            "scripts/coverage/session_coverage_pipeline.py",
            "scripts/coverage/entity_freshness.py",
        ]
    )
    freshness_impls = existing(
        [
            "scripts/freshness_gate.py",
            "scripts/coverage/entity_freshness.py",
        ]
    )
    ledger_impls = existing(
        [
            "scripts/extra_ledger/cli.py",
            "scripts/lib/manual_override_ledger.py",
            "scripts/fix/rebuild_evidence_ledger.py",
            "scripts/ops/alert_pipeline.py",
            "db/migrations/024_coverage_evidence_ledger.sql",
            "scripts/ops/run_execution_ledger.py",
        ]
    )

    req_path = root / "requirements.txt"
    deps: list[str] = []
    if req_path.is_file():
        for ln in req_path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                deps.append(s)

    dod_path = root / "DOD.md"
    open_items = done_items = 0
    if dod_path.is_file():
        dod = dod_path.read_text(encoding="utf-8", errors="replace")
        open_items = len(re.findall(r"^- \[ \]", dod, flags=re.M))
        done_items = len(re.findall(r"^- \[x\]", dod, flags=re.M))

    return {
        "campaign": "ARCH-RESET-2026-07-20",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "main_sha": main_sha,
        "main_short": main_short,
        "main_subject": main_subject,
        "metrics": {
            "tracked_files": len(files),
            "py_scripts_files": len(py_scripts),
            "py_tests_files": len(py_tests),
            "scripts_loc_approx": _count_lines(root, py_scripts),
            "tests_loc_approx": _count_lines(root, py_tests),
            "migrations_sql": len(migrations),
            "adrs": len(adrs),
            "workflows": len(workflows),
            "makefile_targets": len(targets),
            "direct_requirements": len(deps),
            "dod_open_checkboxes": open_items,
            "dod_done_checkboxes": done_items,
            "product_entrypoints_classified": len(product_entrypoints),
            "orchestrators_listed": len(orchestrators),
            "coverage_impl_paths": len(coverage_impls),
            "freshness_impl_paths": len(freshness_impls),
            "ledger_impl_paths": len(ledger_impls),
        },
        "product_entrypoints": product_entrypoints,
        "orchestrators": orchestrators,
        "coverage_implementations": coverage_impls,
        "freshness_implementations": freshness_impls,
        "ledger_implementations": ledger_impls,
        "makefile_targets": targets,
        "requirements_direct": deps,
        "adrs": adrs,
        "migrations": migrations,
        "claims": {
            "LOCAL_READY": "NOT_CLAIMED",
            "operational_coverage_95": "NOT_CLAIMED",
            "VPS_OPERATIONAL": "NOT_CLAIMED",
            "PROJECT_DONE": "NOT_CLAIMED",
            "PRE_VPS_FINAL_READY": "NOT_READY",
            "LOCAL_RESILIENCE_READY": "NOT_READY",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/ops/campaigns/ARCH-RESET-2026-07-20/baseline.json"),
        help="Output JSON path",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    baseline = build_baseline(root)
    out = args.out if args.out.is_absolute() else root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(baseline["metrics"], indent=2, ensure_ascii=False))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
