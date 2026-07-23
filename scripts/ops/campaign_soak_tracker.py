#!/usr/bin/env python3
"""Persistent soak tracker for contracts SLA (7 consecutive days).

Records one observation per invocation under the campaign artifacts dir.
Does not invent green days — missing measurement is a gap day.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]


def _is_vps_host() -> bool:
    """True when running on the production host (no SSH hop needed)."""
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
            timeout=90,
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
            timeout=90,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _measure_runtime() -> tuple[int, str]:
    return _ssh(
        "set +e; "
        "failed=$(systemctl --failed --plain --no-legend 2>/dev/null | wc -l); "
        "echo failed_units=$failed; "
        "echo health_timer=$(systemctl is-active extra-health-check.timer 2>/dev/null || true); "
        "echo contracts_timer=$(systemctl is-active pncp-contracts.timer 2>/dev/null || true); "
        "if [ -f /root/.extra-pg-credentials ]; then . /root/.extra-pg-credentials; fi; "
        "if [ -n \"${LOCAL_DATALAKE_DSN:-}\" ]; then "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'contracts_count='||count(*) FROM pncp_supplier_contracts;\" 2>/dev/null; "
        "psql \"$LOCAL_DATALAKE_DSN\" -Atc "
        "\"SELECT 'age_hours='||COALESCE("
        "round(EXTRACT(EPOCH FROM (now() - max(ts)))/3600.0, 2), 99999) "
        "FROM ("
        "SELECT COALESCE(data_publicacao, data_assinatura) AS ts "
        "FROM pncp_supplier_contracts "
        "WHERE COALESCE(data_publicacao, data_assinatura) IS NOT NULL "
        "AND COALESCE(data_publicacao, data_assinatura) < TIMESTAMP '2100-01-01'"
        ") s;\" 2>/dev/null; "
        "fi; "
        "echo last_contracts_result=$(systemctl show pncp-contracts.service -p Result --value 2>/dev/null || true)"
    )


def observe(*, dsn: str | None, campaign: str) -> dict[str, Any]:
    art = _ROOT / "artifacts" / "campaigns" / campaign
    art.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    obs: dict[str, Any] = {
        "day": day,
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "contracts_freshness_hours": None,
        "incremental_exit": None,
        "health_ok": None,
        "failed_units": None,
        "notes": [],
        "dsn_configured": bool(dsn),
        "measure_mode": "local_vps" if _is_vps_host() else "ssh_ec_prod",
    }

    # Prefer VPS runtime measurement so soak does not depend on laptop fixtures.
    rc, out = _measure_runtime()
    if rc == 0:
        kv: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if "=" in line:
                k, _, v = line.partition("=")
                kv[k.strip()] = v.strip()
        try:
            obs["failed_units"] = int(kv.get("failed_units") or "0")
        except ValueError:
            obs["failed_units"] = None
        obs["health_timer"] = kv.get("health_timer")
        obs["contracts_timer"] = kv.get("contracts_timer")
        obs["health_ok"] = obs["failed_units"] == 0 and obs.get("health_timer") in {
            "active",
            "inactive",  # oneshot timer idle between fires is still ok if not failed
        }
        # Prefer active health timer; accept 0 failed units even if timer shows inactive briefly
        if obs["failed_units"] == 0 and obs.get("health_timer") != "failed":
            obs["health_ok"] = True
        if kv.get("age_hours") not in (None, ""):
            try:
                obs["contracts_freshness_hours"] = float(kv["age_hours"])
            except ValueError:
                obs["notes"].append(f"age_hours_unparseable:{kv.get('age_hours')}")
        if kv.get("contracts_count"):
            try:
                obs["contracts_count"] = int(kv["contracts_count"])
            except ValueError:
                pass
        obs["last_contracts_result"] = kv.get("last_contracts_result")
        obs["incremental_exit"] = 0 if kv.get("last_contracts_result") == "success" else None
        # Persist host-local copy under state dir.
        host_dir = Path("/var/lib/extra-consultoria/backfill/soak")
        try:
            host_dir.mkdir(parents=True, exist_ok=True)
            (host_dir / f"{day}.json").write_text(
                json.dumps(obs, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            # When measuring via SSH from laptop, write remote copy.
            if not _is_vps_host():
                _ssh(
                    "mkdir -p /var/lib/extra-consultoria/backfill/soak && "
                    f"cat > /var/lib/extra-consultoria/backfill/soak/{day}.json <<'EOF'\n"
                    + json.dumps(obs, indent=2)
                    + "\nEOF\n"
                )
    else:
        obs["notes"].append(f"measure_failed:{out[:200]}")
        fresh = _ROOT / "output" / "coverage" / "freshness-contracts.json"
        if fresh.is_file():
            try:
                data = json.loads(fresh.read_text(encoding="utf-8"))
                obs["contracts_freshness_hours"] = data.get("age_hours") or data.get(
                    "max_age_hours"
                )
            except (OSError, json.JSONDecodeError):
                obs["notes"].append("freshness_artifact_unreadable")

    path = art / "soak" / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obs, indent=2) + "\n", encoding="utf-8")

    days = []
    for i in range(7):
        d = (date.today() - timedelta(days=i)).isoformat()
        p = art / "soak" / f"{d}.json"
        if p.is_file():
            days.append(json.loads(p.read_text(encoding="utf-8")))
    # Complete only with 7 consecutive calendar days present, all healthy,
    # and every measured freshness within 168h (missing freshness is a gap).
    day_keys = {(x.get("day") or "") for x in days}
    expected_days = {
        (date.today() - timedelta(days=i)).isoformat() for i in range(7)
    }
    freshness_ok = all(
        (x.get("contracts_freshness_hours") is not None)
        and float(x["contracts_freshness_hours"]) <= 168
        for x in days
    )
    rollup = {
        "campaign": campaign,
        "required_consecutive_days": 7,
        "observations_last_7d": days,
        "expected_days": sorted(expected_days),
        "present_days": sorted(day_keys),
        "complete": expected_days.issubset(day_keys)
        and len(days) >= 7
        and all(x.get("health_ok") for x in days)
        and freshness_ok,
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (art / "soak.json").write_text(json.dumps(rollup, indent=2) + "\n", encoding="utf-8")
    return rollup


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", default="HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01")
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN"))
    args = p.parse_args(argv)
    rollup = observe(dsn=args.dsn, campaign=args.campaign)
    print(json.dumps(rollup, indent=2))
    return 0 if rollup.get("complete") else 2


if __name__ == "__main__":
    raise SystemExit(main())
