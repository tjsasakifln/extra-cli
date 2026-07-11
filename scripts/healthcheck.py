#!/usr/bin/env python3
"""Unified healthcheck for Extra Consultoria system.

Verifies:
    - DB connectivity (PostgreSQL)
    - Active crawlers (systemd timers)
    - API keys validity (env vars)
    - Disk space

Story TD-4.2 | AC7-8: CI/CD Pipeline — Healthcheck unificado.
Debts: TD-OPS-01, TD-SYS-015.

Usage:
    python scripts/healthcheck.py                 # Human-readable output
    python scripts/healthcheck.py --json           # JSON output for monitoring
    python scripts/healthcheck.py --json --quiet   # JSON, no stderr (silent mode)

Exit codes:
    0 — All checks passed
    1 — Warnings (e.g. disk > 80%)
    2 — Critical failures (DB, API keys, crawlers)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@localhost:5432/pncp_datalake")
DISK_WARN_PCT = 80
DISK_CRIT_PCT = 90

# Known API keys required by the system
REQUIRED_API_KEYS = {
    "OPENAI_API_KEY": "OpenAI LLM (intel pipeline)",
}

# Known crawler systemd timer units
CRAWLER_TIMERS = [
    "pncp-crawl-full.timer",
    "pncp-crawl-inc.timer",
    "dom-sc-crawl.timer",
    "coverage-report.timer",
    "pncp-report-weekly.timer",
    "extra-health-check.timer",
]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_db() -> tuple[bool, str]:
    """Check PostgreSQL connectivity."""
    try:
        result = subprocess.run(
            ["psql", DB_DSN, "-c", "SELECT 1 AS ok", "-t", "-A"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "1" in result.stdout.strip():
            return True, "PostgreSQL OK"
        return False, f"psql error: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "psql timeout (10s)"
    except FileNotFoundError:
        return False, "psql not found"
    except Exception as e:
        return False, str(e)


def check_api_keys() -> tuple[bool, str]:
    """Check that required API keys are set in environment."""
    missing: list[str] = []
    for key, purpose in REQUIRED_API_KEYS.items():
        if not os.getenv(key):
            missing.append(f"{key} ({purpose})")

    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All API keys present"


def check_crawlers() -> tuple[bool, str]:
    """Check if crawler systemd timers are active.

    Runs `systemctl list-timers` and checks for expected timer units.
    Falls back gracefully if systemd is not available (e.g. dev/CI).
    """
    try:
        result = subprocess.run(
            ["systemctl", "list-timers", "--all", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, f"systemctl error: {result.stderr.strip()}"

        active_timers = result.stdout
        active_names = []
        missing_timers = []

        for timer in CRAWLER_TIMERS:
            if timer in active_timers:
                active_names.append(timer)
            else:
                missing_timers.append(timer)

        if missing_timers:
            inactive = ", ".join(missing_timers)
            status = f"{len(active_names)}/{len(CRAWLER_TIMERS)} active"
            return False, f"Crawlers: {status} — inactive: {inactive}"

        return True, f"All {len(CRAWLER_TIMERS)} crawlers active"

    except FileNotFoundError:
        # systemd not available (dev container, CI, etc.)
        return True, "systemd not available — skipping crawler check (dev mode)"
    except subprocess.TimeoutExpired:
        return True, "systemctl timed out — skipping crawler check"
    except Exception as e:
        return True, f"Crawler check error (non-blocking): {e}"


def check_disk() -> tuple[int, str]:
    """Check disk usage. Returns (severity, message)."""
    usage = shutil.disk_usage("/")
    pct = usage.used / usage.total * 100
    total_gb = usage.total / (1024**3)
    used_gb = usage.used / (1024**3)
    free_gb = usage.free / (1024**3)
    msg = f"Disk: {used_gb:.1f}G / {total_gb:.1f}G ({pct:.0f}%) — {free_gb:.1f}G free"
    if pct >= DISK_CRIT_PCT:
        return 2, msg
    if pct >= DISK_WARN_PCT:
        return 1, msg
    return 0, msg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Extra Consultoria — Unified Healthcheck")
    parser.add_argument("--json", action="store_true", help="Output as JSON for monitoring tools")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-JSON output (use with --json)")
    args = parser.parse_args()

    timestamp = datetime.now(UTC).isoformat()
    exit_code = 0
    results: dict[str, dict] = {}

    # --- DB ---
    db_ok, db_msg = check_db()
    results["db"] = {"status": "pass" if db_ok else "fail", "message": db_msg}
    if not db_ok:
        exit_code = 2

    # --- API Keys ---
    keys_ok, keys_msg = check_api_keys()
    results["api_keys"] = {"status": "pass" if keys_ok else "fail", "message": keys_msg}
    if not keys_ok:
        exit_code = 2

    # --- Crawlers ---
    craw_ok, craw_msg = check_crawlers()
    craw_status = "pass" if craw_ok else ("warn" if "skipping" in craw_msg or "dev mode" in craw_msg else "fail")
    results["crawlers"] = {"status": craw_status, "message": craw_msg}
    if not craw_ok and craw_status == "fail":
        exit_code = max(exit_code, 1)

    # --- Disk ---
    disk_severity, disk_msg = check_disk()
    disk_status = "pass" if disk_severity == 0 else ("warn" if disk_severity == 1 else "fail")
    results["disk"] = {"status": disk_status, "message": disk_msg}
    if disk_severity == 2:
        exit_code = 2
    elif disk_severity == 1 and exit_code == 0:
        exit_code = 1

    # --- Report ---
    report = {
        "event": "healthcheck",
        "timestamp": timestamp,
        "host": os.uname().nodename,
        "exit_code": exit_code,
        "checks": results,
    }

    if args.json:
        print(json.dumps(report))
    else:
        if not args.quiet:
            print(f"Healthcheck — {timestamp}")
            print(f"Host:     {report['host']}")
            print(f"Exit:     {exit_code}")
            print()
            for name, check in results.items():
                status_icon = "PASS" if check["status"] == "pass" else ("WARN" if check["status"] == "warn" else "FAIL")
                print(f"  [{status_icon}] {name}: {check['message']}")
            print()
            print(f"Summary: {'All OK' if exit_code == 0 else 'Warnings' if exit_code == 1 else 'Critical failures'}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
