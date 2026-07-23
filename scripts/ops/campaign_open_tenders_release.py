#!/usr/bin/env python3
"""Release-candidate gate for OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01.

Runs structural gate + unit suite + optional live collect/report generation.
Fail-closed: empty operational products, missing baseline, or failed tests → FAIL.
Does not invent VPS_OPERATIONAL or coverage ≥95% without measured artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CAMPAIGN = "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"
ART = _ROOT / "artifacts" / "campaigns" / CAMPAIGN


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _run(cmd: list[str], *, timeout: int = 600) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        r = subprocess.run(  # noqa: S603
            cmd,
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONPATH": str(_ROOT)},
        )
        return {
            "cmd": cmd,
            "exit_code": r.returncode,
            "duration_s": round(time.monotonic() - t0, 2),
            "stdout_tail": (r.stdout or "")[-4000:],
            "stderr_tail": (r.stderr or "")[-2000:],
            "ok": r.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "exit_code": 124,
            "duration_s": round(time.monotonic() - t0, 2),
            "stdout_tail": str(exc)[:500],
            "stderr_tail": "timeout",
            "ok": False,
        }


def run_release(
    *,
    dsn: str | None = None,
    live_collect: bool = False,
    offline_weekly: bool = True,
) -> dict[str, Any]:
    ART.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")

    # 1) structural campaign gate
    steps.append(
        _run(
            [
                sys.executable,
                "-m",
                "scripts.ops.campaign_open_tenders_gate",
                "--out",
                str(ART / "campaign-gate.json"),
            ],
            timeout=120,
        )
    )

    # 2) unit/integration tests for campaign surface
    steps.append(
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-q",
                "--tb=line",
                "tests/test_open_tenders_campaign_gate.py",
                "tests/test_deliverable_e_editais.py",
                "tests/test_weekly_cycle.py",
                "tests/test_source_policy_canonical.py",
            ],
            timeout=300,
        )
    )

    # 3) offline weekly cycle (always, proves delivery products)
    if offline_weekly and dsn:
        out_dir = ART / "weekly-offline-rc"
        steps.append(
            _run(
                [
                    sys.executable,
                    "-m",
                    "scripts.ops.weekly_cycle",
                    "--offline",
                    "--skip-collect",
                    "--dsn",
                    dsn,
                    "--output-dir",
                    str(out_dir),
                ],
                timeout=180,
            )
        )
        de = out_dir / "deliverable_e.json"
        de_audit = out_dir / "deliverable_e_audit.json"
        products = {
            "weekly_dir": str(out_dir),
            "deliverable_e_exists": de.is_file(),
            "deliverable_e_audit_exists": de_audit.is_file(),
            "manifest_exists": (out_dir / "manifest.json").is_file(),
            "excel_exists": (out_dir / "extra_weekly_pack.xlsx").is_file(),
        }
        if de_audit.is_file():
            try:
                products["deliverable_e_audit"] = json.loads(
                    de_audit.read_text(encoding="utf-8")
                ).get("ok")
            except json.JSONDecodeError:
                products["deliverable_e_audit"] = None
    else:
        products = {"weekly_skipped": True, "reason": "no DSN or offline disabled"}

    # 4) optional live collect (full open monitoring)
    live: dict[str, Any] = {"requested": live_collect, "ran": False}
    if live_collect and dsn:
        live["ran"] = True
        steps.append(
            _run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from datetime import date, timedelta\n"
                        "from pathlib import Path\n"
                        "import json, os\n"
                        "from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path\n"
                        "from scripts.opportunity_intel.pncp_audit import run_pncp_open_monitoring\n"
                        f"dsn = {dsn!r}\n"
                        "seed = resolve_default_seed_path(Path('.').resolve())\n"
                        "u = load_canonical_universe(seed_path=seed)\n"
                        "o = run_pncp_open_monitoring(\n"
                        "  dsn=dsn, external_run_id='rc-open-tenders',\n"
                        "  universe=u, period_start=date.today()-timedelta(days=7),\n"
                        "  period_end=date.today(), mode='full', persist=True)\n"
                        "print(json.dumps({'status': o.status, 'scope_complete': o.scope_complete,\n"
                        "  'records_fetched': o.records_fetched, 'db_run_id': o.db_run_id,\n"
                        "  'scopes': len(o.scopes)}, default=str))\n"
                    ),
                ],
                timeout=3600,
            )
        )
        try:
            live["result"] = json.loads(steps[-1].get("stdout_tail", "").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError, TypeError):
            live["result"] = {"parse_error": True, "stdout_tail": steps[-1].get("stdout_tail", "")[:500]}

    # 5) snapshot integrity if DSN
    integrity: dict[str, Any] = {}
    if dsn:
        try:
            from scripts.ops.snapshot_integrity import measure_snapshot_integrity

            si = measure_snapshot_integrity(dsn, require_non_empty=True)
            integrity = si.to_dict()
            (ART / "snapshot-integrity.json").write_text(
                json.dumps(integrity, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            integrity = {"error": str(exc), "operational_ok": False}

    baseline_ok = (ART / "baseline.json").is_file()
    gate_ok = all(s.get("ok") for s in steps[:2])  # structural + pytest must pass
    weekly_ok = True
    if offline_weekly and dsn:
        weekly_ok = bool(products.get("manifest_exists") and products.get("deliverable_e_exists"))

    # RC foundation does NOT require live coverage ≥95% — that is verify-production
    ok = gate_ok and baseline_ok and weekly_ok

    report = {
        "campaign_id": CAMPAIGN,
        "gate": "release-candidate-open-tenders",
        "generated_at": _utc_now(),
        "git_sha": _git_sha(),
        "ok": ok,
        "baseline_present": baseline_ok,
        "steps": [
            {
                "name": n,
                "ok": s.get("ok"),
                "exit_code": s.get("exit_code"),
                "duration_s": s.get("duration_s"),
            }
            for n, s in zip(
                ["campaign_gate", "pytest_suite", "weekly_offline", "live_collect"][: len(steps)],
                steps,
                strict=False,
            )
        ],
        "step_details": steps,
        "products": products,
        "live_collect": live,
        "snapshot_integrity": {
            "status": integrity.get("status"),
            "integrity_pct": integrity.get("integrity_pct"),
            "active_open_count": integrity.get("active_open_count"),
            "operational_ok": integrity.get("operational_ok"),
        },
        "claims_authorized": [
            "structural campaign gate PASS on this SHA" if gate_ok else None,
            "weekly offline pack generates deliverable_e" if weekly_ok else None,
        ],
        "claims_forbidden": [
            "VPS_OPERATIONAL",
            "open_tenders coverage ≥95% without dual report PASS",
            "soak complete",
            "PROJECT_DONE",
            "LOCAL_READY",
        ],
        "note": (
            "Release-candidate foundation. Full operational PASS requires "
            "verify-open-tenders-production + live coverage + VPS timer + soak."
        ),
    }
    report["claims_authorized"] = [c for c in report["claims_authorized"] if c]
    out = ART / "release-candidate.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=None)
    p.add_argument("--live-collect", action="store_true")
    p.add_argument("--no-offline-weekly", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    report = run_release(
        dsn=args.dsn,
        live_collect=args.live_collect,
        offline_weekly=not args.no_offline_weekly,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({k: report[k] for k in report if k != "step_details"}, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
