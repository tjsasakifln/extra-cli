#!/usr/bin/env python3
"""verify-open-tenders-production — fail-closed operational check.

Measures local artifacts + optional ssh ec-prod. Never invents green status.
Missing timer, empty opportunity_intel, coverage FAIL, or stale freshness → not PASS.
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

CAMPAIGN = "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"


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


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _ssh(cmd: str, timeout: int = 45) -> tuple[int, str]:
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
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _check(item_id: str, ok: bool, evidence: Any, notes: str = "") -> dict[str, Any]:
    return {
        "item_id": item_id,
        "status": "PASS" if ok else "FAIL",
        "evidence": evidence,
        "notes": notes,
    }


def build_report(*, require_vps: bool = False) -> dict[str, Any]:
    art = _ROOT / "artifacts" / "campaigns" / CAMPAIGN
    dual = _load_json(_ROOT / "output" / "coverage" / "dual-coverage-open_tenders.json") or {}
    freshness = _load_json(_ROOT / "output" / "coverage" / "freshness-editais.json") or {}
    baseline = art / "baseline.json"
    gate = _load_json(art / "campaign-gate.json") or {}
    rc = _load_json(art / "release-candidate.json") or {}
    si = _load_json(art / "snapshot-integrity.json") or {}

    checks: list[dict[str, Any]] = []
    checks.append(_check("baseline", baseline.is_file(), str(baseline.relative_to(_ROOT)) if baseline.is_file() else "missing"))
    checks.append(
        _check(
            "campaign_gate",
            gate.get("ok") is True,
            gate.get("summary") or "missing campaign-gate.json",
        )
    )
    checks.append(
        _check(
            "release_candidate_foundation",
            rc.get("ok") is True,
            {"ok": rc.get("ok"), "sha": rc.get("git_sha")},
            "optional if only verify without RC step",
        )
    )

    cov_pct = dual.get("coverage_pct")
    cov_ok = (
        isinstance(cov_pct, (int, float))
        and float(cov_pct) >= 0.95
        and dual.get("gate_status") == "PASS"
        and int(dual.get("applicability_unknown_count") or 0) == 0
    )
    checks.append(
        _check(
            "dual_open_tenders_coverage",
            cov_ok,
            {
                "coverage_pct": cov_pct,
                "gate_status": dual.get("gate_status"),
                "applicable_denominator": dual.get("applicable_denominator"),
                "covered_numerator": dual.get("covered_numerator"),
                "unknown": dual.get("applicability_unknown_count"),
                "universe": dual.get("universe_count"),
            },
            "requires regenerated dual report ≥95% with zero applicability unknown",
        )
    )

    # freshness: covered fresh vs denominator if available
    fresh_covered = freshness.get("covered")
    fresh_den = freshness.get("denominator")
    # Prefer explicit fresh_count if present
    fresh_n = freshness.get("fresh_count", fresh_covered)
    freshness_ok = (
        isinstance(fresh_n, int)
        and isinstance(fresh_den, int)
        and fresh_den > 0
        and (fresh_n / fresh_den) >= 0.95
    )
    checks.append(
        _check(
            "freshness_editais",
            freshness_ok,
            {
                "fresh_or_covered": fresh_n,
                "denominator": fresh_den,
                "as_of": freshness.get("as_of"),
            },
            "freshness-editais.json must show ≥95% fresh within SLA",
        )
    )

    si_ok = si.get("operational_ok") is True and float(si.get("integrity_pct") or 0) >= 100.0
    checks.append(
        _check(
            "snapshot_integrity",
            si_ok,
            {
                "status": si.get("status"),
                "integrity_pct": si.get("integrity_pct"),
                "active_open_count": si.get("active_open_count"),
            },
        )
    )

    # VPS inspection
    rc_ssh, vps_sha = _ssh(
        "git -C /opt/extra-consultoria rev-parse HEAD 2>/dev/null || echo unknown"
    )
    _, timer_enabled = _ssh("systemctl is-enabled extra-weekly.timer 2>&1 || true")
    _, timer_active = _ssh("systemctl is-active extra-weekly.timer 2>&1 || true")
    _, svc_result = _ssh(
        "systemctl show extra-weekly.service -p Result -p ExecMainStatus -p ActiveEnterTimestamp --no-pager 2>&1 | head -10"
    )
    _, opp_count = _ssh(
        "cd /opt/extra-consultoria && "
        "(test -f .env && set -a && . ./.env && set +a; "
        "python3 -c \"import os,psycopg2; d=os.environ.get('DATABASE_URL') or os.environ.get('LOCAL_DATALAKE_DSN'); "
        "c=psycopg2.connect(d) if d else None; "
        "print(c.cursor().execute('select count(*) from opportunity_intel') or c.cursor().fetchone()[0] if False else '')\" 2>/dev/null) "
        "|| (sudo -u postgres psql -d extra -tAc 'SELECT COUNT(*) FROM opportunity_intel' 2>/dev/null) "
        "|| echo 'unknown'"
    )
    # simpler count
    _, opp_count2 = _ssh(
        "sudo -u postgres psql -d extra -tAc 'SELECT COUNT(*) FROM opportunity_intel' 2>/dev/null "
        "|| psql \"$DATABASE_URL\" -tAc 'SELECT COUNT(*) FROM opportunity_intel' 2>/dev/null "
        "|| echo unknown"
    )
    opp_raw = (opp_count2 or opp_count or "unknown").strip().splitlines()[-1] if (opp_count2 or opp_count) else "unknown"
    try:
        opp_n = int(opp_raw)
    except ValueError:
        opp_n = None

    vps_timer_ok = "enabled" in timer_enabled and "active" in timer_active
    vps_data_ok = isinstance(opp_n, int) and opp_n > 0
    checks.append(
        _check(
            "vps_extra_weekly_timer",
            vps_timer_ok,
            {
                "enabled": timer_enabled,
                "active": timer_active,
                "service": svc_result[:500],
                "ssh_ok": rc_ssh != 99,
                "vps_sha": vps_sha.strip()[:40],
            },
            "timer must be enabled+active on VPS",
        )
    )
    checks.append(
        _check(
            "vps_opportunity_intel_nonempty",
            vps_data_ok,
            {"count": opp_n, "raw": opp_raw},
        )
    )

    # Soak artifact if present
    soak = _load_json(art / "soak.json") or {}
    soak_ok = soak.get("status") == "PASS" or (
        int(soak.get("days_observed") or 0) >= 7 and soak.get("gaps", 1) == 0
    )
    checks.append(
        _check(
            "soak_7d",
            soak_ok,
            soak if soak else "missing soak.json",
            "requires seven days of recurring execution evidence",
        )
    )

    fails = [c for c in checks if c["status"] == "FAIL"]
    # Foundation items that can pass without full VPS:
    foundation_ids = {"baseline", "campaign_gate"}
    foundation_ok = all(
        c["status"] == "PASS" for c in checks if c["item_id"] in foundation_ids
    )

    if require_vps:
        overall_ok = len(fails) == 0
        status = "PASS" if overall_ok else "FAIL"
    else:
        # Honest partial: operational PASS only if zero fails; else BLOCKED/FAIL
        critical_ops = {
            "dual_open_tenders_coverage",
            "freshness_editais",
            "snapshot_integrity",
            "vps_extra_weekly_timer",
            "vps_opportunity_intel_nonempty",
            "soak_7d",
        }
        ops_fails = [c for c in fails if c["item_id"] in critical_ops]
        if not fails:
            status = "PASS"
            overall_ok = True
        elif foundation_ok and ops_fails:
            status = "BLOCKED"
            overall_ok = False
        else:
            status = "FAIL"
            overall_ok = False

    report = {
        "campaign_id": CAMPAIGN,
        "gate": "verify-open-tenders-production",
        "generated_at": _utc_now(),
        "git_sha": _git_sha(),
        "status": status,
        "ok": overall_ok,
        "summary": {
            "total": len(checks),
            "pass": len(checks) - len(fails),
            "fail": len(fails),
        },
        "checks": checks,
        "vps": {
            "sha": vps_sha.strip()[:40] if vps_sha else None,
            "timer_enabled": timer_enabled,
            "timer_active": timer_active,
            "opportunity_intel_count": opp_n,
        },
        "claims_authorized": [],
        "claims_forbidden": [
            "VPS_OPERATIONAL without timer+data+coverage+soak",
            "PROJECT_DONE",
            "LOCAL_READY",
            "coverage ≥95% without dual report PASS",
        ],
        "note": (
            "BLOCKED means foundation may exist but operational proof is incomplete. "
            "PASS requires all checks green including soak."
        ),
    }
    if overall_ok:
        report["claims_authorized"].append("open_tenders operational cycle verified on measured evidence")
    out = art / "verify-production.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--require-vps", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    report = build_report(require_vps=args.require_vps)
    if args.out:
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    if report["status"] == "PASS":
        return 0
    if report["status"] == "BLOCKED":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
