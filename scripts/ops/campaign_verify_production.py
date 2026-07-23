#!/usr/bin/env python3
"""Transparent verify-production gate for HISTORICAL-CONTRACTS campaign.

Emits a single JSON with measured fields. Missing/unknown values are failures
for production claims — never invent green status.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _git_sha() -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _ssh_ec_prod(cmd: str, timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(  # noqa: S603
            [
                "/usr/bin/ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "ec-prod",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def build_report(campaign: str) -> dict[str, Any]:
    art = _ROOT / "artifacts" / "campaigns" / campaign
    ckpt = _ROOT / "data" / "contracts_checkpoints" / "hc_closure_3y" / "contracts_full.json"
    dual = _ROOT / "output" / "coverage" / "dual-coverage-historical_contracts.json"
    baseline = art / "baseline.json"

    ck = _load_json(ckpt) or {}
    completed = ck.get("completed_windows") or []
    dual_data = _load_json(dual) or {}

    rc, failed_units = _ssh_ec_prod(
        "systemctl --failed --no-pager --plain 2>/dev/null | head -20"
    )
    _rc2, health = _ssh_ec_prod(
        "systemctl is-active extra-health-check.timer 2>/dev/null; "
        "systemctl show extra-health-check.service -p Result --value 2>/dev/null"
    )

    report: dict[str, Any] = {
        "campaign": campaign,
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_sha": _git_sha(),
        "baseline_present": baseline.is_file(),
        "checkpoint": {
            "path": str(ckpt),
            "completed_windows": len(completed),
            "planned_windows_target": 37,
            "current_window_start": ck.get("current_window_start"),
            "total_windows_failed": ck.get("total_windows_failed"),
            "complete": len(completed) >= 37,
        },
        "dual_historical_contracts": {
            "coverage_pct": dual_data.get("coverage_pct"),
            "gate_status": dual_data.get("gate_status"),
            "applicable_denominator": dual_data.get("applicable_denominator"),
            "covered_numerator": dual_data.get("covered_numerator"),
            "applicability_unknown_count": dual_data.get("applicability_unknown_count"),
            "as_of": dual_data.get("as_of"),
        },
        "vps": {
            "ssh_ok": rc != 99,
            "failed_units_snippet": failed_units.strip()[:2000]
            if rc == 0
            else failed_units[:500],
            "health_timer": health.strip()[:500],
        },
        "gates": {},
        "status": "incomplete",
        "claims_authorized": [],
        "non_claims": [
            "LOCAL_READY",
            "VPS_OPERATIONAL",
            "PROJECT_DONE",
            "open_tenders>=95%",
        ],
    }

    offsite = _load_json(art / "backup-offsite.json") or {}
    soak = _load_json(art / "soak.json") or {}
    cutover = _load_json(art / "cutover.json") or {}

    gates = {
        "baseline": baseline.is_file(),
        "checkpoint_complete": len(completed) >= 37,
        "dual_pass": dual_data.get("gate_status") == "PASS"
        and (
            isinstance(dual_data.get("coverage_pct"), (int, float))
            and float(dual_data["coverage_pct"]) >= 95.0
        ),
        "vps_ssh": rc != 99,
        "no_failed_units_text": rc == 0 and "0 loaded units listed" in failed_units,
        "cutover_ok": cutover.get("status") == "ok" or cutover.get("count_match") is True,
        "offsite_ok": offsite.get("status") == "ok",
        "soak_7d": bool(soak.get("complete")),
    }
    report["gates"] = gates
    report["offsite"] = {
        "status": offsite.get("status"),
        "blockers": offsite.get("blockers"),
    }
    report["soak"] = {
        "complete": soak.get("complete"),
        "observations": len(soak.get("observations_last_7d") or []),
    }
    report["status"] = "pass" if all(gates.values()) else "fail"
    # Full operational claim only when every gate including off-site + soak holds.
    if report["status"] == "pass":
        report["claims_authorized"] = ["HISTORICAL_CONTRACTS_OPERATIONAL_COVERAGE_PASS"]
    else:
        report["claims_authorized"] = []
        if gates.get("checkpoint_complete") and gates.get("dual_pass") and gates.get(
            "cutover_ok"
        ):
            report["claims_authorized"].extend(
                [
                    "HISTORICAL_CONTRACTS_BACKFILL_37_WINDOWS",
                    "HISTORICAL_CONTRACTS_DUAL_GATE_PASS_LOCAL",
                    "CUTOVER_RESTORE_OK",
                ]
            )
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", default="HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args(argv)
    report = build_report(args.campaign)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
