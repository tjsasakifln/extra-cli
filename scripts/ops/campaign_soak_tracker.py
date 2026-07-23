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


def _ssh(cmd: str) -> tuple[int, str]:
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
            timeout=60,
            check=False,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


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
    }

    rc, out = _ssh(
        "systemctl --failed --plain --no-legend 2>/dev/null | wc -l; "
        "systemctl is-active extra-health-check.timer 2>/dev/null || true"
    )
    if rc == 0:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        obs["failed_units"] = int(lines[0]) if lines and lines[0].isdigit() else None
        obs["health_timer"] = lines[1] if len(lines) > 1 else None
        obs["health_ok"] = obs["failed_units"] == 0
    else:
        obs["notes"].append(f"ssh_failed:{out[:200]}")

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
    rollup = {
        "campaign": campaign,
        "required_consecutive_days": 7,
        "observations_last_7d": days,
        "complete": len(days) >= 7
        and all(x.get("health_ok") for x in days)
        and all(
            (x.get("contracts_freshness_hours") is not None)
            and float(x["contracts_freshness_hours"]) <= 168
            for x in days
            if x.get("contracts_freshness_hours") is not None
        ),
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
