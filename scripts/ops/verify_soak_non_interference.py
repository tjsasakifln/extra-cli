#!/usr/bin/env python3
"""Fail-closed soak non-interference gate for CONFENGE commercial campaign.

Compares baseline soak snapshot (captured before campaign work) with a final
snapshot. Any unknown/null field fails closed. Does not modify production.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAMPAIGN_ID = "CONFENGE-COMMERCIAL-READY-01"
REQUIRED_EVIDENCE_KEYS = (
    "no_write_proven",
)

REQUIRED_BOOL_KEYS = (
    "production_touched",
    "soak_touched",
    "timers_modified",
    "services_restarted",
    "operational_tables_written",
    "soak_artifacts_modified",
)

SOAK_UNITS = (
    "extra-contracts-soak.timer",
    "extra-contracts-soak.service",
    "pncp-contracts.timer",
    "pncp-contracts.service",
    "extra-weekly.timer",
    "extra-weekly.service",
    "extra-db-backup.timer",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def capture_remote_snapshot(ssh_host: str) -> dict[str, Any]:
    """Capture read-only soak state via ssh. Never restarts services."""
    remote = r"""
set -e
echo "HOSTNAME=$(hostname)"
echo "DEPLOY_SHA=$(cd /opt/extra-consultoria 2>/dev/null && git rev-parse HEAD 2>/dev/null || echo unknown)"
for u in extra-contracts-soak.timer extra-contracts-soak.service pncp-contracts.timer pncp-contracts.service extra-weekly.timer extra-weekly.service extra-db-backup.timer; do
  en=$(systemctl is-enabled "$u" 2>/dev/null || echo missing)
  ac=$(systemctl is-active "$u" 2>/dev/null || echo missing)
  echo "UNIT|$u|enabled=$en|active=$ac"
done
for f in /etc/systemd/system/extra-contracts-soak.service /etc/systemd/system/extra-contracts-soak.timer /etc/systemd/system/pncp-contracts.service /etc/systemd/system/pncp-contracts.timer /etc/systemd/system/extra-weekly.service /etc/systemd/system/extra-weekly.timer; do
  if [ -f "$f" ]; then
    h=$(sha256sum "$f" | awk '{print $1}')
    echo "UNITFILE_HASH|$f|$h"
  else
    echo "UNITFILE_HASH|$f|MISSING"
  fi
done
if [ -f /opt/extra-consultoria/artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/soak.json ]; then
  h=$(sha256sum /opt/extra-consultoria/artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/soak.json | awk '{print $1}')
  echo "SOAK_ARTIFACT_HASH|HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/soak.json|$h"
fi
if [ -f /opt/extra-consultoria/artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/soak.json ]; then
  h=$(sha256sum /opt/extra-consultoria/artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/soak.json | awk '{print $1}')
  echo "SOAK_ARTIFACT_HASH|OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/soak.json|$h"
fi
systemctl show extra-contracts-soak.timer -p ActiveState,UnitFileState,LastTriggerUSec,NextElapseUSecRealtime --value 2>/dev/null | tr '\n' '|'
echo
systemctl show pncp-contracts.timer -p ActiveState,UnitFileState,LastTriggerUSec,NextElapseUSecRealtime --value 2>/dev/null | tr '\n' '|'
echo
"""
    code, out, err = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_host, remote], timeout=60)
    if code != 0:
        return {
            "ok": False,
            "error": "ssh_failed",
            "exit_code": code,
            "stderr": err[-2000:],
            "stdout": out[-2000:],
            "captured_at": utc_now(),
        }

    units: dict[str, dict[str, str]] = {}
    unit_hashes: dict[str, str] = {}
    soak_hashes: dict[str, str] = {}
    deploy_sha = "unknown"
    hostname = "unknown"
    for line in out.splitlines():
        if line.startswith("HOSTNAME="):
            hostname = line.split("=", 1)[1]
        elif line.startswith("DEPLOY_SHA="):
            deploy_sha = line.split("=", 1)[1]
        elif line.startswith("UNIT|"):
            parts = line.split("|")
            if len(parts) >= 4:
                name = parts[1]
                units[name] = {
                    "enabled": parts[2].replace("enabled=", ""),
                    "active": parts[3].replace("active=", ""),
                }
        elif line.startswith("UNITFILE_HASH|"):
            parts = line.split("|")
            if len(parts) >= 3:
                unit_hashes[parts[1]] = parts[2]
        elif line.startswith("SOAK_ARTIFACT_HASH|"):
            parts = line.split("|")
            if len(parts) >= 3:
                soak_hashes[parts[1]] = parts[2]

    return {
        "ok": True,
        "captured_at": utc_now(),
        "hostname": hostname,
        "deploy_sha": deploy_sha,
        "units": units,
        "unit_file_hashes": unit_hashes,
        "soak_artifact_hashes": soak_hashes,
        "raw_tail": out[-1500:],
        "campaign_id": CAMPAIGN_ID,
        "mode": "remote_readonly",
    }


def compare_snapshots(baseline: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []

    def _req(obj: dict[str, Any], key: str) -> Any:
        if key not in obj or obj[key] is None:
            reasons.append(f"missing_or_null:{key}")
            return None
        return obj[key]

    if not baseline.get("ok"):
        reasons.append("baseline_not_ok")
    if not final.get("ok"):
        reasons.append("final_not_ok")

    production_touched = False
    soak_touched = False
    # Objective §18: never auto-fill false without observation. UNKNOWN fails closed.
    timers_modified: bool | str = "UNKNOWN"
    services_restarted: bool | str = "UNKNOWN"
    operational_tables_written: bool | str = "UNKNOWN"
    soak_artifacts_modified: bool | str = "UNKNOWN"
    no_write_proven = False
    no_write_observed: bool | None = None
    campaign_did_not_request_write = True
    _timer_observed = False

    b_units = baseline.get("units") or {}
    f_units = final.get("units") or {}
    for name in SOAK_UNITS:
        bu = b_units.get(name)
        fu = f_units.get(name)
        if bu is None or fu is None:
            # unit may be static/missing on some hosts — only fail if present in baseline then gone
            if bu is not None and fu is None:
                reasons.append(f"unit_missing_in_final:{name}")
                soak_touched = True
            continue
        _timer_observed = True
        if bu.get("enabled") != fu.get("enabled"):
            reasons.append(f"enabled_changed:{name}")
            timers_modified = True
            soak_touched = True
        if bu.get("active") != fu.get("active"):
            # active can flap for oneshot services; timer enabled is stronger signal
            if name.endswith(".timer"):
                reasons.append(f"timer_active_changed:{name}")
                timers_modified = True

    b_hash = baseline.get("unit_file_hashes") or {}
    f_hash = final.get("unit_file_hashes") or {}
    for path, bh in b_hash.items():
        _timer_observed = True
        fh = f_hash.get(path)
        if fh is None:
            reasons.append(f"unitfile_missing_final:{path}")
            soak_touched = True
            continue
        if bh != fh:
            reasons.append(f"unitfile_hash_changed:{path}")
            timers_modified = True
            soak_touched = True
            production_touched = True
    if _timer_observed and timers_modified == "UNKNOWN":
        timers_modified = False  # observed units, no change detected

    b_art = baseline.get("soak_artifact_hashes") or {}
    f_art = final.get("soak_artifact_hashes") or {}
    for path, bh in b_art.items():
        fh = f_art.get(path)
        if fh is None:
            reasons.append(f"soak_artifact_missing_final:{path}")
            soak_artifacts_modified = True
            soak_touched = True
        elif fh != bh:
            # soak.json may grow legitimately during soak window — flag but distinguish
            reasons.append(f"soak_artifact_hash_changed:{path}")
            soak_artifacts_modified = True
            # Not necessarily campaign interference; still report honestly
            # Campaign must not have written these files. Hash change alone is not production_touched
            # unless we prove our process wrote them. Keep soak_artifacts_modified true.
    if (b_art or f_art) and soak_artifacts_modified == "UNKNOWN":
        soak_artifacts_modified = False

    if baseline.get("deploy_sha") and final.get("deploy_sha"):
        if baseline["deploy_sha"] != final["deploy_sha"] and final["deploy_sha"] != "unknown":
            # deploy SHA change is not automatically our fault; note only
            reasons.append("deploy_sha_changed_observe_only")

    # Derive services_restarted only from real evidence fields when present
    svc_evidence = final.get("service_restart_evidence") or baseline.get("service_restart_evidence")
    if isinstance(svc_evidence, dict) and svc_evidence.get("NRestarts") is not None:
        b_n = (baseline.get("service_restart_evidence") or {}).get("NRestarts")
        f_n = (final.get("service_restart_evidence") or {}).get("NRestarts")
        if b_n is not None and f_n is not None:
            services_restarted = int(f_n) > int(b_n)
        else:
            services_restarted = "UNKNOWN"
            reasons.append("services_restarted_incomplete_evidence")
    else:
        services_restarted = "UNKNOWN"
        reasons.append("services_restarted_unobserved")

    table_evidence = final.get("operational_table_write_evidence")
    if isinstance(table_evidence, dict) and table_evidence.get("no_write_proven") is True:
        operational_tables_written = False
        no_write_proven = True
        no_write_observed = True
    elif isinstance(table_evidence, dict) and table_evidence.get("writes_observed") is True:
        operational_tables_written = True
        no_write_proven = False
        no_write_observed = False
    else:
        operational_tables_written = "UNKNOWN"
        no_write_proven = False
        no_write_observed = None
        reasons.append("operational_tables_unobserved")

    if soak_artifacts_modified == "UNKNOWN":
        # if we compared hashes, we have observation
        if b_art or f_art:
            soak_artifacts_modified = bool(
                any(
                    (f_art.get(p) != bh)
                    for p, bh in b_art.items()
                )
            )

    result = {
        "campaign_id": CAMPAIGN_ID,
        "compared_at": utc_now(),
        "production_touched": production_touched,
        "soak_touched": soak_touched,
        "timers_modified": timers_modified,
        "services_restarted": services_restarted,
        "operational_tables_written": operational_tables_written,
        "soak_artifacts_modified": soak_artifacts_modified,
        "campaign_did_not_request_write": campaign_did_not_request_write,
        "no_write_observed": no_write_observed,
        "no_write_proven": no_write_proven,
        "reasons": reasons,
        "baseline_captured_at": baseline.get("captured_at"),
        "final_captured_at": final.get("captured_at"),
        "baseline_deploy_sha": baseline.get("deploy_sha"),
        "final_deploy_sha": final.get("deploy_sha"),
    }

    # Fail closed: nulls or UNKNOWN on observation keys
    for k in REQUIRED_BOOL_KEYS:
        if result.get(k) is None:
            reasons.append(f"null_bool:{k}")
            result[k] = "UNKNOWN"
    result["reasons"] = reasons

    unknown_obs = any(
        result.get(k) == "UNKNOWN"
        for k in ("services_restarted", "operational_tables_written", "timers_modified")
    )
    # Interference: proven true OR unobserved (UNKNOWN fail-closed) OR structural unit changes
    interference = (
        production_touched is True
        or timers_modified is True
        or services_restarted is True
        or operational_tables_written is True
        or unknown_obs
        or (
            soak_touched
            and any(
                r.startswith("unitfile_hash_changed") or r.startswith("enabled_changed")
                for r in reasons
            )
        )
    )
    # Strong PASS only when no_write_proven and no interference
    ok = (
        not interference
        and no_write_proven
        and not any(
            r.startswith("baseline_not_ok")
            or r.startswith("final_not_ok")
            or r.startswith("missing_or_null")
            for r in reasons
        )
    )
    result["ok"] = ok
    result["status"] = "PASS" if ok else "FAIL"
    result["interference"] = interference
    if unknown_obs and not ok:
        result["fail_reason"] = "UNKNOWN_observations_fail_closed"
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify soak non-interference (fail-closed)")
    p.add_argument("--baseline", required=True, help="Path to soak-baseline.json")
    p.add_argument("--final", default=None, help="Path to soak-final.json (capture if missing with --ssh)")
    p.add_argument("--ssh", default="ec-prod", help="SSH host for live capture")
    p.add_argument("--capture-only", action="store_true", help="Only write baseline/final capture")
    p.add_argument("--out", required=True, help="Output comparison JSON")
    args = p.parse_args(argv)

    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        snap = capture_remote_snapshot(args.ssh)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote baseline {baseline_path} ok={snap.get('ok')}")
        if args.capture_only:
            Path(args.out).write_text(json.dumps({"status": "CAPTURED", "path": str(baseline_path)}, indent=2) + "\n")
            return 0 if snap.get("ok") else 1

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    if args.final and Path(args.final).is_file():
        final = json.loads(Path(args.final).read_text(encoding="utf-8"))
    else:
        final = capture_remote_snapshot(args.ssh)
        final_path = Path(args.final) if args.final else Path(args.out).parent / "soak-final.json"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote final {final_path} ok={final.get('ok')}")

    if args.capture_only:
        return 0 if baseline.get("ok") and final.get("ok") else 1

    result = compare_snapshots(baseline, final)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} status={result.get('status')} ok={result.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
