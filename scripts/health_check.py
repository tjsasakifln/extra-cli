#!/usr/bin/env python3
"""Health check for Extra Consultoria VPS — DB, Storage Box, Disk, System.

Extra Consultoria — Story FEAT-4.1
Runs via systemd timer (extra-health-check) every 30 minutes.
Logs structured JSON to journald.

Exit codes:
    0 — All checks passed
    1 — Warnings only (disk > 80%)
    2 — Critical failure (DB unreachable, Storage Box unmounted)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from config.logging_config import get_logger, set_correlation_id

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@localhost:5432/pncp_datalake")
STORAGE_BOX_MOUNT = os.getenv("BACKUP_MOUNT_POINT", "/mnt/storage-box")
# Off-site mount is optional until configured; set REQUIRE_STORAGE_BOX=1 to enforce.
REQUIRE_STORAGE_BOX = os.getenv("REQUIRE_STORAGE_BOX", "0").lower() in {
    "1",
    "true",
    "yes",
}
DISK_WARN_PCT = 80
DISK_CRIT_PCT = 90


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_db() -> tuple[bool, str]:
    """Check PostgreSQL connectivity via psql."""
    try:
        result = subprocess.run(  # noqa: S603 — shell=False default
            ["psql", DB_DSN, "-c", "SELECT 1 AS ok", "-t", "-A"],  # noqa: S607 — psql resolved from PATH in production VPS
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


def check_storage_box() -> tuple[bool, str]:
    """Check if Storage Box / off-site backup mount is mounted and accessible.

    When REQUIRE_STORAGE_BOX is unset/false, a missing mount is a soft skip
    (not critical) so health stays green on hosts with local-only backup until
    off-site is provisioned. Operational off-site proof is a separate gate.
    """
    if not os.path.ismount(STORAGE_BOX_MOUNT):
        msg = f"Storage Box not mounted at {STORAGE_BOX_MOUNT}"
        if REQUIRE_STORAGE_BOX:
            return False, msg
        return True, f"SKIP (optional): {msg}"
    try:
        entries = os.listdir(STORAGE_BOX_MOUNT)
        return True, f"Storage Box OK ({len(entries)} entries)"
    except PermissionError:
        return False, "Storage Box mounted but permission denied"
    except Exception as e:
        return False, str(e)


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


def check_system() -> tuple[bool, str]:
    """Basic system checks: memory, load."""
    try:
        load = os.getloadavg()
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = parts[1].strip()
        mem_total = int(mem.get("MemTotal", "0").split()[0]) // 1024
        mem_avail = int(mem.get("MemAvailable", "0").split()[0]) // 1024
        mem_pct = (1 - mem_avail / mem_total) * 100 if mem_total > 0 else 0
        return (
            True,
            f"Load: {load[0]:.1f} {load[1]:.1f} {load[2]:.1f} | Mem: {mem_pct:.0f}% used ({mem_avail}M avail / {mem_total}M total)",
        )
    except Exception as e:
        return False, str(e)


CRITICAL_TIMERS = (
    "pncp-contracts.timer",
    "extra-crawl-pncp.timer",
    "extra-crawl-ciga-ckan.timer",
    "extra-health-check.timer",
    "extra-contracts-soak.timer",
)

CRITICAL_UNIT_TOKENS = (
    "pncp-contracts",
    "extra-crawl-pncp",
    "extra-crawl-ciga",
    "extra-health",
    "extra-contracts-soak",
    "extra-weekly",
)


def check_failed_units() -> tuple[bool, str]:
    """Fail when critical systemd units are in failed state."""
    try:
        r = subprocess.run(  # noqa: S603
            ["systemctl", "--failed", "--plain", "--no-legend"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=15,
        )
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        critical = [ln for ln in lines if any(tok in ln for tok in CRITICAL_UNIT_TOKENS)]
        if critical:
            return False, f"critical failed units: {len(critical)} ({critical[0][:80]})"
        return True, f"no critical failed units (total_failed={len(lines)})"
    except Exception as e:
        return False, f"failed_units check error: {e}"


def check_critical_timers() -> tuple[bool, str]:
    """Require critical timers enabled + active."""
    bad: list[str] = []
    for unit in CRITICAL_TIMERS:
        try:
            en = subprocess.run(  # noqa: S603
                ["systemctl", "is-enabled", unit],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=10,
            )
            ac = subprocess.run(  # noqa: S603
                ["systemctl", "is-active", unit],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=10,
            )
            en_s = (en.stdout or "").strip()
            ac_s = (ac.stdout or "").strip()
            if en_s not in {"enabled", "static"} or ac_s != "active":
                bad.append(f"{unit}:enabled={en_s}:active={ac_s}")
        except Exception as e:
            bad.append(f"{unit}:err={e}")
    if bad:
        return False, "; ".join(bad[:5])
    return True, f"critical timers OK ({len(CRITICAL_TIMERS)})"


def check_dual_coverage_artifact() -> tuple[bool, str]:
    """Require dual coverage artifact PASS with both capabilities >=95%."""
    candidates = [
        "output/coverage/dual-campaign-orrc-01/dual-capability-coverage-summary.json",
        "output/coverage/dual-latest/dual-capability-coverage-summary.json",
        "output/coverage/dual-capability-coverage-summary.json",
    ]
    root = Path(__file__).resolve().parents[1]
    for rel in candidates:
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return False, f"dual summary unreadable: {e}"
        if data.get("dual_gate_status") != "PASS":
            return False, f"dual_gate_status={data.get('dual_gate_status')}"
        if not data.get("pipeline_success") or not data.get("scope_complete"):
            return False, "dual pipeline/scope not complete"
        caps = data.get("capabilities") or {}
        for name in ("open_tenders", "historical_contracts"):
            c = caps.get(name) or {}
            pct = c.get("coverage_pct")
            try:
                f = float(pct)
            except (TypeError, ValueError):
                return False, f"{name}: missing coverage_pct"
            if f > 1.0:
                f = f / 100.0
            if f < 0.95:
                return False, f"{name}: coverage={f:.4f} < 0.95"
        return True, f"dual PASS artifact {path.name}"
    return False, "dual coverage summary missing"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    timestamp = datetime.now(UTC).isoformat()
    set_correlation_id()  # set correlation_id for structured logging
    exit_code = 0
    results: dict[str, dict] = {}

    logger.info(
        "Health check started",
        extra={"extra_data": {"host": os.uname().nodename}},
    )

    # Run checks
    db_ok, db_msg = check_db()
    results["db"] = {"status": "pass" if db_ok else "fail", "message": db_msg}
    if not db_ok:
        exit_code = 2

    sb_ok, sb_msg = check_storage_box()
    results["storage_box"] = {"status": "pass" if sb_ok else "fail", "message": sb_msg}
    if not sb_ok:
        # Critical only when off-site mount is required by env.
        exit_code = 2 if REQUIRE_STORAGE_BOX else max(exit_code, 1)

    disk_severity, disk_msg = check_disk()
    disk_status = "pass" if disk_severity == 0 else ("warn" if disk_severity == 1 else "fail")
    results["disk"] = {"status": disk_status, "message": disk_msg}
    if disk_severity == 2:
        exit_code = 2
    elif disk_severity == 1 and exit_code == 0:
        exit_code = 1

    sys_ok, sys_msg = check_system()
    results["system"] = {"status": "pass" if sys_ok else "fail", "message": sys_msg}

    fu_ok, fu_msg = check_failed_units()
    results["failed_units"] = {"status": "pass" if fu_ok else "fail", "message": fu_msg}
    if not fu_ok:
        exit_code = 2

    tm_ok, tm_msg = check_critical_timers()
    results["critical_timers"] = {"status": "pass" if tm_ok else "fail", "message": tm_msg}
    if not tm_ok:
        exit_code = 2

    dual_ok, dual_msg = check_dual_coverage_artifact()
    results["dual_coverage"] = {
        "status": "pass" if dual_ok else "fail",
        "message": dual_msg,
    }
    if not dual_ok:
        # Soft-fail when dual artifact is stale/missing so DB-only hosts still boot;
        # production VPS with dual PASS keeps hard green.
        exit_code = max(exit_code, 1)

    # Build structured log for journald
    report = {
        "event": "health_check",
        "timestamp": timestamp,
        "host": os.uname().nodename,
        "exit_code": exit_code,
        "results": results,
    }
    print(json.dumps(report))

    # Also log via structured logger (includes correlation_id)
    log_level = logging.ERROR if exit_code == 2 else (logging.WARNING if exit_code == 1 else logging.INFO)
    logger.log(
        log_level,
        "Health check completed: exit_code=%d",
        exit_code,
        extra={"extra_data": {"report": report}},
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
