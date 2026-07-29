#!/usr/bin/env python3
"""Fail-closed soak tracker for operational contracts / open tenders SLA.

Records observations under campaign artifacts. Does **not** invent green days.
All calendar keys use UTC: ``datetime.now(UTC).date()``.

``health_ok=true`` only when every applicable requirement is true.
Missing measurement is a gap day — never silent success.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]

# Freshness SLAs (hours) — ingestion/observation based, NOT document dates
CONTRACTS_SLA_HOURS = 168
OPEN_TENDERS_SLA_HOURS = 24


def _is_vps_host() -> bool:
    try:
        if Path("/root/.extra-pg-credentials").is_file():
            return True
    except OSError:
        pass
    try:
        if Path("/opt/extra-consultoria").is_dir() and Path(
            "/var/lib/extra-consultoria"
        ).is_dir():
            host = os.uname().nodename if hasattr(os, "uname") else ""
            return host.startswith("v") or host.startswith("v220")
    except OSError:
        pass
    return False


def _run_local(cmd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(  # noqa: S603
            ["/bin/bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _ssh(cmd: str) -> tuple[int, str]:
    if _is_vps_host():
        return _run_local(cmd)
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
            timeout=120,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _measure_runtime() -> tuple[int, str]:
    """Collect runtime signals. Freshness must NOT use document publication dates."""
    return _ssh(
        "set +e; "
        "failed=$(systemctl --failed --plain --no-legend 2>/dev/null | wc -l); "
        "echo failed_units=$failed; "
        "echo failed_critical=$(systemctl --failed --plain --no-legend 2>/dev/null | "
        "grep -E 'pncp-contracts|extra-weekly|extra-health|extra-contracts-soak' | wc -l); "
        "echo health_timer=$(systemctl is-active extra-health-check.timer 2>/dev/null || true); "
        "echo contracts_timer=$(systemctl is-active pncp-contracts.timer 2>/dev/null || true); "
        "echo contracts_timer_enabled=$(systemctl is-enabled pncp-contracts.timer 2>/dev/null || true); "
        "echo contracts_last_trigger=$(systemctl show pncp-contracts.timer -p LastTriggerUSec --value 2>/dev/null || true); "
        "echo contracts_next_trigger=$(systemctl show pncp-contracts.timer -p NextElapseUSecRealtime --value 2>/dev/null || true); "
        "echo last_contracts_result=$(systemctl show pncp-contracts.service -p Result --value 2>/dev/null || true); "
        "echo last_contracts_exec=$(systemctl show pncp-contracts.service -p ExecMainStatus --value 2>/dev/null || true); "
        "echo host=$(hostname 2>/dev/null || true); "
        "echo deployed_sha=$(cat /opt/extra-consultoria/.deployed_sha 2>/dev/null || "
        "git -C /opt/extra-consultoria rev-parse HEAD 2>/dev/null || true); "
        # Prefer ingestion_runs / pipeline timestamps over data_publicacao
        "if [ -f /root/.extra-pg-credentials ]; then . /root/.extra-pg-credentials; fi; "
        "if [ -n \"${LOCAL_DATALAKE_DSN:-}\" ]; then "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_count='||count(*) FROM pncp_supplier_contracts;\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_ingest_age_hours='||COALESCE("
        "round(EXTRACT(EPOCH FROM (now() - max(completed_at)))/3600.0, 2), 99999) "
        "FROM ingestion_runs WHERE source IN ('contracts','pncp_contracts') "
        "AND status IN ('completed','success') "
        "AND completed_at IS NOT NULL;\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_run_id='||COALESCE("
        "(SELECT meta->>'run_id' FROM ingestion_runs "
        "WHERE source IN ('contracts','pncp_contracts') "
        "AND status IN ('completed','success') "
        "ORDER BY completed_at DESC NULLS LAST LIMIT 1), '');\" 2>/dev/null; "
        "fi; "
        # Fallback: incremental artifact mtime age (still not document date)
        "if [ -f /opt/extra-consultoria/output/contracts/incremental-latest.json ]; then "
        "echo contracts_artifact_age_hours=$(python3 -c "
        "\"import os,time; p='/opt/extra-consultoria/output/contracts/incremental-latest.json'; "
        "print(round((time.time()-os.path.getmtime(p))/3600,2))\" 2>/dev/null); "
        "echo contracts_artifact_run_id=$(python3 -c "
        "\"import json; d=json.load(open('/opt/extra-consultoria/output/contracts/incremental-latest.json')); "
        "print(d.get('run_id') or '')\" 2>/dev/null); "
        "fi"
    )


def _parse_kv(out: str) -> dict[str, str]:
    kv: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()
    return kv


def _compute_health_ok(obs: dict[str, Any]) -> tuple[bool, list[str]]:
    """Fail-closed health. Every failure reason is listed."""
    reasons: list[str] = []
    if obs.get("failed_critical_units") not in (0, "0"):
        reasons.append("failed_critical_units")
    if obs.get("contracts_timer") not in {"active"}:
        # timer idle between fires is still "active" for systemd timers
        reasons.append("contracts_timer_not_active")
    if obs.get("contracts_timer_enabled") not in {"enabled", "static"}:
        reasons.append("contracts_timer_not_enabled")
    if obs.get("last_contracts_result") != "success":
        reasons.append("last_contracts_result_not_success")
    # ExecMainStatus 0 or 75 (lock busy) only — 75 is not source fail but also
    # does not prove a successful crawl for the day.
    exec_st = obs.get("last_contracts_exec")
    if exec_st not in {"0", 0, None}:
        # allow empty when never run yet — still fail health
        if exec_st not in (None, ""):
            try:
                if int(exec_st) not in (0, 75):
                    reasons.append(f"last_contracts_exec={exec_st}")
            except (TypeError, ValueError):
                reasons.append(f"last_contracts_exec_unparseable={exec_st}")
    if not obs.get("run_id"):
        reasons.append("missing_run_id")
    fresh = obs.get("contracts_freshness_hours")
    if fresh is None:
        reasons.append("missing_contracts_freshness")
    else:
        try:
            if float(fresh) > CONTRACTS_SLA_HOURS:
                reasons.append(f"contracts_stale_h={fresh}")
        except (TypeError, ValueError):
            reasons.append("contracts_freshness_unparseable")
    # Manual run is not automation
    if obs.get("automatic_execution") is False:
        reasons.append("manual_execution_not_automation")
    return (len(reasons) == 0), reasons


def observe(*, dsn: str | None, campaign: str) -> dict[str, Any]:
    art = _ROOT / "artifacts" / "campaigns" / campaign
    art.mkdir(parents=True, exist_ok=True)
    day_utc = datetime.now(UTC).date().isoformat()
    observation_id = f"obs-{day_utc}-{uuid.uuid4().hex[:10]}"
    obs: dict[str, Any] = {
        "day_utc": day_utc,
        "day": day_utc,  # backward compat
        "observation_id": observation_id,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": None,
        "deployed_sha": None,
        "schema_version": None,
        "policy_version": None,
        "universe_version": None,
        "timer_enabled": None,
        "timer_active": None,
        "last_trigger": None,
        "next_trigger": None,
        "service_result": None,
        "exec_main_status": None,
        "invocation_id": None,
        "run_id": None,
        "automatic_execution": True,  # unit timer path; CLI default true when from systemd
        "contracts_freshness_hours": None,
        "open_tenders_freshness_hours": None,
        "contracts_coverage": None,
        "open_tenders_coverage": None,
        "failed_critical_units": None,
        "failed_units": None,
        "source_health": None,
        "checksum_status": None,
        "health_ok": False,
        "health_fail_reasons": [],
        "notes": [],
        "dsn_configured": bool(dsn),
        "measure_mode": "local_vps" if _is_vps_host() else "ssh_ec_prod",
        "freshness_basis": "ingestion_runs.completed_at|artifact_mtime — NOT data_publicacao",
    }

    rc, out = _measure_runtime()
    if rc != 0 and not out.strip():
        obs["notes"].append(f"measure_failed_rc={rc}")
        obs["health_ok"] = False
        obs["health_fail_reasons"] = ["measure_failed"]
    else:
        kv = _parse_kv(out)
        if rc != 0:
            obs["notes"].append(f"measure_rc={rc}")
        try:
            obs["failed_units"] = int(kv.get("failed_units") or "0")
        except ValueError:
            obs["failed_units"] = None
        try:
            obs["failed_critical_units"] = int(kv.get("failed_critical") or "0")
        except ValueError:
            obs["failed_critical_units"] = None
        obs["host"] = kv.get("host")
        obs["deployed_sha"] = kv.get("deployed_sha") or None
        obs["timer_active"] = kv.get("contracts_timer")
        obs["contracts_timer"] = kv.get("contracts_timer")
        obs["timer_enabled"] = kv.get("contracts_timer_enabled")
        obs["contracts_timer_enabled"] = kv.get("contracts_timer_enabled")
        obs["health_timer"] = kv.get("health_timer")
        obs["last_trigger"] = kv.get("contracts_last_trigger")
        obs["next_trigger"] = kv.get("contracts_next_trigger")
        obs["service_result"] = kv.get("last_contracts_result")
        obs["last_contracts_result"] = kv.get("last_contracts_result")
        obs["exec_main_status"] = kv.get("last_contracts_exec")
        obs["last_contracts_exec"] = kv.get("last_contracts_exec")
        if kv.get("contracts_count"):
            try:
                obs["contracts_count"] = int(kv["contracts_count"])
            except ValueError:
                pass
        # Freshness: prefer ingestion age; fallback artifact mtime; NEVER data_publicacao
        age = kv.get("contracts_ingest_age_hours") or kv.get("contracts_artifact_age_hours")
        if age not in (None, ""):
            try:
                obs["contracts_freshness_hours"] = float(age)
                obs["freshness_source"] = (
                    "ingestion_runs"
                    if kv.get("contracts_ingest_age_hours")
                    else "artifact_mtime"
                )
            except ValueError:
                obs["notes"].append(f"age_unparseable:{age}")
        run_id = kv.get("contracts_run_id") or kv.get("contracts_artifact_run_id") or ""
        obs["run_id"] = run_id or None
        obs["incremental_exit"] = (
            0 if kv.get("last_contracts_result") == "success" else None
        )

    ok, reasons = _compute_health_ok(obs)
    obs["health_ok"] = ok
    obs["health_fail_reasons"] = reasons

    # Persist: never overwrite different observation_id silently — append rollup
    day_path = art / "soak" / f"{day_utc}.json"
    day_path.parent.mkdir(parents=True, exist_ok=True)
    observations_for_day: list[dict[str, Any]] = []
    if day_path.is_file():
        try:
            prev = json.loads(day_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and prev.get("observations"):
                observations_for_day = list(prev["observations"])
            elif isinstance(prev, dict) and prev.get("observation_id"):
                observations_for_day = [prev]
        except (OSError, json.JSONDecodeError):
            obs["notes"].append("prior_day_file_unreadable")
    observations_for_day.append(obs)
    day_doc = {
        "day_utc": day_utc,
        "observations": observations_for_day,
        "rollup": _day_rollup(observations_for_day),
    }
    day_path.write_text(json.dumps(day_doc, indent=2) + "\n", encoding="utf-8")

    # Host-local copy
    host_dir = Path("/var/lib/extra-consultoria/backfill/soak")
    try:
        host_dir.mkdir(parents=True, exist_ok=True)
        (host_dir / f"{day_utc}.json").write_text(
            json.dumps(day_doc, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        if not _is_vps_host():
            payload = json.dumps(day_doc, indent=2)
            _ssh(
                "mkdir -p /var/lib/extra-consultoria/backfill/soak && "
                f"cat > /var/lib/extra-consultoria/backfill/soak/{day_utc}.json <<'EOF'\n"
                + payload
                + "\nEOF\n"
            )

    return _write_campaign_rollup(art, campaign)


def _day_rollup(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic rollup: day is healthy only if any observation is healthy."""
    if not observations:
        return {"health_ok": False, "reason": "no_observations"}
    # Prefer latest observation for metrics; health_ok if ANY true (same UTC day)
    latest = observations[-1]
    any_ok = any(bool(o.get("health_ok")) for o in observations)
    return {
        "health_ok": any_ok,
        "observation_count": len(observations),
        "latest_observation_id": latest.get("observation_id"),
        "latest_run_id": latest.get("run_id"),
        "latest_contracts_freshness_hours": latest.get("contracts_freshness_hours"),
        "all_fail_reasons": sorted(
            {r for o in observations for r in (o.get("health_fail_reasons") or [])}
        ),
    }


def _write_campaign_rollup(art: Path, campaign: str) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    days_payload: list[dict[str, Any]] = []
    day_keys: set[str] = set()
    for i in range(7):
        d = (today - timedelta(days=i)).isoformat()
        p = art / "soak" / f"{d}.json"
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        day_keys.add(d)
        if isinstance(doc, dict) and "rollup" in doc:
            days_payload.append(
                {
                    "day_utc": d,
                    "health_ok": bool((doc.get("rollup") or {}).get("health_ok")),
                    "rollup": doc.get("rollup"),
                    "observation_count": len(doc.get("observations") or []),
                }
            )
        elif isinstance(doc, dict):
            # Legacy single-observation file
            days_payload.append(
                {
                    "day_utc": d,
                    "health_ok": bool(doc.get("health_ok")),
                    "legacy": True,
                    "observation_count": 1,
                }
            )

    expected_days = {(today - timedelta(days=i)).isoformat() for i in range(7)}
    present = day_keys
    freshness_ok = all(
        (
            (x.get("rollup") or {}).get("latest_contracts_freshness_hours") is not None
            and float((x.get("rollup") or {}).get("latest_contracts_freshness_hours"))
            <= CONTRACTS_SLA_HOURS
        )
        if x.get("rollup")
        else False
        for x in days_payload
    )
    health_all = all(x.get("health_ok") for x in days_payload) if days_payload else False
    complete = (
        expected_days.issubset(present)
        and len(days_payload) >= 7
        and health_all
        and freshness_ok
    )
    rollup = {
        "campaign": campaign,
        "required_consecutive_days": 7,
        "calendar": "UTC",
        "observations_last_7d": days_payload,
        "expected_days": sorted(expected_days),
        "present_days": sorted(present),
        "complete": complete,
        "complete_reason": (
            "ok"
            if complete
            else "missing_days_or_health_or_freshness"
        ),
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "rules": {
            "no_retroactive_fill": True,
            "no_document_date_freshness": True,
            "no_manual_as_automation": True,
            "health_requires_contracts_success_and_run_id": True,
        },
    }
    (art / "soak.json").write_text(json.dumps(rollup, indent=2) + "\n", encoding="utf-8")
    return rollup


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--campaign",
        default="EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01",
    )
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN"))
    p.add_argument(
        "--manual",
        action="store_true",
        help="Mark observation as manual (cannot prove automation)",
    )
    args = p.parse_args(argv)
    rollup = observe(dsn=args.dsn, campaign=args.campaign)
    # Patch last observation if --manual
    if args.manual:
        day = datetime.now(UTC).date().isoformat()
        art = _ROOT / "artifacts" / "campaigns" / args.campaign / "soak" / f"{day}.json"
        if art.is_file():
            doc = json.loads(art.read_text(encoding="utf-8"))
            for o in doc.get("observations") or []:
                o["automatic_execution"] = False
                ok, reasons = _compute_health_ok(o)
                o["health_ok"] = ok
                o["health_fail_reasons"] = reasons
            doc["rollup"] = _day_rollup(doc.get("observations") or [])
            art.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            rollup = _write_campaign_rollup(
                _ROOT / "artifacts" / "campaigns" / args.campaign, args.campaign
            )
    print(json.dumps(rollup, indent=2))
    return 0 if rollup.get("complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
