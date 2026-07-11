#!/usr/bin/env python3
"""Health dashboard — resumo do estado do sistema (CLI).

Extra Consultoria — Story TD-5.5 (AC6)
Exibe:
    - Orgaos crawlados por fonte
    - Status do ultimo backup
    - Alertas ativos
    - Saude geral do sistema

Usage:
    python scripts/health-dashboard.py              # Dashboard completo
    python scripts/health-dashboard.py --summary    # Apenas resumo (uma linha)
    python scripts/health-dashboard.py --json       # JSON output
    python scripts/health-dashboard.py --watch      # Atualizacao a cada 60s

Exit codes:
    0 — All OK
    1 — Warnings
    2 — Critical
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging_config import get_logger, set_correlation_id
from config.settings import DEFAULT_DSN

logger = get_logger(__name__)

BACKUP_LOG_FILE = os.getenv("BACKUP_LOG_FILE", "/var/log/backup-database.log")
STORAGE_BOX_MOUNT = os.getenv("BACKUP_MOUNT_POINT", "/mnt/storage-box")
DISK_WARN_PCT = 80
DISK_CRIT_PCT = 90


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------


def get_db_conn():
    """Create database connection."""
    import psycopg2  # noqa: PLC0415
    return psycopg2.connect(DEFAULT_DSN)


def collect_system_health() -> dict[str, Any]:
    """Collect system-level health data."""
    health: dict[str, Any] = {"status": "unknown", "checks": {}}

    # DB connectivity
    try:
        result = subprocess.run(
            ["psql", DEFAULT_DSN, "-c", "SELECT 1", "-t", "-A"],
            capture_output=True, text=True, timeout=10,
        )
        db_ok = result.returncode == 0 and "1" in result.stdout.strip()
        health["checks"]["db"] = {
            "status": "pass" if db_ok else "fail",
            "message": "PostgreSQL OK" if db_ok else f"Error: {result.stderr.strip()[:100]}",
        }
    except Exception as e:
        health["checks"]["db"] = {"status": "fail", "message": str(e)[:100]}

    # Disk
    try:
        usage = shutil.disk_usage("/")
        pct = usage.used / usage.total * 100
        free_gb = usage.free / (1024**3)
        if pct >= DISK_CRIT_PCT:
            disk_status = "fail"
        elif pct >= DISK_WARN_PCT:
            disk_status = "warn"
        else:
            disk_status = "pass"
        health["checks"]["disk"] = {
            "status": disk_status,
            "message": f"{pct:.0f}% used ({free_gb:.1f}G free)",
        }
    except Exception as e:
        health["checks"]["disk"] = {"status": "fail", "message": str(e)[:100]}

    # Storage Box
    try:
        sb_ok = os.path.ismount(STORAGE_BOX_MOUNT)
        health["checks"]["storage_box"] = {
            "status": "pass" if sb_ok else "fail",
            "message": "Mounted" if sb_ok else "Not mounted",
        }
    except Exception as e:
        health["checks"]["storage_box"] = {"status": "fail", "message": str(e)[:100]}

    # Overall system status
    failures = [k for k, v in health["checks"].items() if v["status"] == "fail"]
    warnings = [k for k, v in health["checks"].items() if v["status"] == "warn"]
    if failures:
        health["status"] = "critical"
    elif warnings:
        health["status"] = "warning"
    else:
        health["status"] = "healthy"

    return health


def collect_crawl_stats() -> dict[str, Any]:
    """Collect crawl statistics for the dashboard."""
    stats: dict[str, Any] = {
        "sources": [],
        "total_today": 0,
        "total_week": 0,
        "error": None,
    }

    try:
        conn = get_db_conn()
        cur = conn.cursor()

        # Today's runs
        cur.execute(
            """SELECT source, COUNT(*) AS runs,
                      COUNT(*) FILTER (WHERE status = 'completed') AS ok,
                      COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                      COALESCE(SUM(records_fetched), 0) AS fetched
               FROM ingestion_runs
               WHERE started_at >= CURRENT_DATE
               GROUP BY source
               ORDER BY source"""
        )
        today_data = {r[0]: {"runs": r[1], "ok": r[2], "failed": r[3], "fetched": r[4]}
                      for r in cur.fetchall()}

        # This week's runs
        cur.execute(
            """SELECT COUNT(*) AS total
               FROM ingestion_runs
               WHERE started_at >= DATE_TRUNC('week', NOW())"""
        )
        stats["total_week"] = cur.fetchone()[0] or 0

        # Per-source summary (last 7 days)
        cur.execute(
            """SELECT source,
                      COUNT(*) AS total_runs,
                      COUNT(*) FILTER (WHERE status = 'completed') AS successful,
                      COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                      COALESCE(SUM(records_fetched), 0) AS fetched,
                      MAX(started_at) AS last_run
               FROM ingestion_runs
               WHERE started_at >= NOW() - INTERVAL '7 days'
               GROUP BY source
               ORDER BY source"""
        )
        for row in cur.fetchall():
            source = row[0]
            today = today_data.get(source, {})
            src = {
                "source": source,
                "total_runs": row[1],
                "successful": row[2],
                "failed": row[3],
                "fetched": row[4],
                "last_run": row[5].isoformat() if row[5] else None,
                "today_runs": today.get("runs", 0),
                "today_ok": today.get("ok", 0),
                "today_fetched": today.get("fetched", 0),
            }
            if src["total_runs"] > 0:
                src["success_rate"] = round(src["successful"] / src["total_runs"] * 100, 1)
            else:
                src["success_rate"] = 0.0
            stats["sources"].append(src)
            stats["total_today"] += src["today_runs"]

        cur.close()
        conn.close()

    except Exception as e:
        stats["error"] = str(e)[:200]

    return stats


def collect_backup_status() -> dict[str, Any]:
    """Collect backup status for the dashboard."""
    status: dict[str, Any] = {
        "last_backup": None,
        "status": "unknown",
        "size_mb": None,
        "hours_ago": None,
        "error": None,
    }

    log_path = Path(BACKUP_LOG_FILE)
    if not log_path.exists():
        status["status"] = "no_log"
        return status

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        status["error"] = str(e)
        return status

    for line in reversed(lines):
        if "LOG_JSON:" in line:
            try:
                entry = json.loads(line.split("LOG_JSON:", 1)[1].strip())
                status["last_backup"] = entry.get("timestamp")
                status["status"] = entry.get("status", "unknown")
                size_bytes = entry.get("size_bytes")
                if size_bytes is not None:
                    status["size_mb"] = round(int(size_bytes) / (1024 * 1024), 1)

                if entry.get("timestamp"):
                    try:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        hours_ago = (datetime.now(UTC) - ts).total_seconds() / 3600
                        status["hours_ago"] = round(hours_ago, 1)
                    except (ValueError, TypeError):
                        pass
                break
            except (json.JSONDecodeError, IndexError):
                continue

    return status


def collect_alert_summary() -> dict[str, Any]:
    """Collect active alerts summary by running check-alerts in subprocess."""
    check_alerts = str(_PROJECT_ROOT / "scripts" / "check-alerts.py")
    if not os.path.isfile(check_alerts):
        return {"alerts": [], "total": 0, "critical": 0, "warnings": 0,
                "error": "check-alerts.py not found"}

    try:
        result = subprocess.run(
            [sys.executable, check_alerts, "--json", "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode in (0, 1, 2) and result.stdout.strip():
            data = json.loads(result.stdout)
            alerts = data.get("alerts", [])
            return {
                "alerts": alerts,
                "total": len(alerts),
                "critical": sum(1 for a in alerts if a["severity"] >= 2),
                "warnings": sum(1 for a in alerts if a["severity"] == 1),
            }
        return {"alerts": [], "total": 0, "critical": 0, "warnings": 0,
                "error": f"check-alerts returned {result.returncode}: {result.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"alerts": [], "total": 0, "critical": 0, "warnings": 0,
                "error": "check-alerts timed out"}
    except json.JSONDecodeError as e:
        return {"alerts": [], "total": 0, "critical": 0, "warnings": 0,
                "error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"alerts": [], "total": 0, "critical": 0, "warnings": 0,
                "error": str(e)[:200]}


# ---------------------------------------------------------------------------
# Dashboard display
# ---------------------------------------------------------------------------


def _status_icon(status: str) -> str:
    icons = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "healthy": "OK",
             "critical": "CRIT", "warning": "WARN", "ok": "OK",
             "success": "OK", "unknown": "?"}
    return icons.get(status, "?")


def print_dashboard() -> None:
    """Print full dashboard to stdout."""
    system = collect_system_health()
    crawl = collect_crawl_stats()
    backup = collect_backup_status()

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    print()
    print("=" * 70)
    print("  DASHBOARD DE MONITORAMENTO — Extra Consultoria")
    print(f"  {timestamp}")
    print(f"  Host: {os.uname().nodename}")
    print("=" * 70)

    # System health
    print()
    print("  --- SAUDE DO SISTEMA ---")
    for check_name, check in system.get("checks", {}).items():
        icon = _status_icon(check["status"])
        print(f"    [{icon}] {check_name:20s} {check['message']}")

    overall_icon = _status_icon(system.get("status", "unknown"))
    print("    ---")
    print(f"    [{overall_icon}] Overall: {system.get('status', 'unknown').upper()}")

    # Crawl stats
    print()
    print("  --- CRAWL ---")
    if crawl.get("error"):
        print(f"    ERROR: {crawl['error']}")
    else:
        print(f"    Runs today: {crawl.get('total_today', 0)}  |  "
              f"Runs this week: {crawl.get('total_week', 0)}")
        print(f"    {'Source':20s} {'Runs':>5s} {'OK':>4s} {'Fail':>5s} "
              f"{'Rate':>7s} {'Fetched':>8s} {'Last run':>20s}")
        print(f"    {'-'*20} {'-'*5} {'-'*4} {'-'*5} {'-'*7} {'-'*8} {'-'*20}")
        for src in crawl.get("sources", []):
            rate = f"{src.get('success_rate', 0):.0f}%"
            last = (src.get("last_run") or "N/A")[:19]
            print(f"    {src['source']:20s} "
                  f"{src['total_runs']:5d} "
                  f"{src['successful']:4d} "
                  f"{src['failed']:5d} "
                  f"{rate:>7s} "
                  f"{src['fetched']:8d} "
                  f"{last:>20s}")

    # Backup
    print()
    print("  --- BACKUP ---")
    if backup.get("error"):
        print(f"    ERROR: {backup['error']}")
    elif backup["status"] == "no_log":
        print(f"    No backup log found at {BACKUP_LOG_FILE}")
    else:
        bk_icon = _status_icon(backup.get("status", "unknown"))
        print(f"    [{bk_icon}] Last backup: {backup.get('last_backup', 'N/A')}")
        print(f"         Status:     {backup.get('status', 'unknown')}")
        if backup.get("size_mb"):
            print(f"         Size:       {backup['size_mb']} MB")
        if backup.get("hours_ago") is not None:
            print(f"         Hours ago:  {backup['hours_ago']}h")

    # Active alerts
    try:
        alerts = collect_alert_summary()
    except Exception:
        alerts = {"alerts": [], "total": 0, "critical": 0, "warnings": 0, "error": "Failed to check"}

    print()
    print("  --- ALERTAS ATIVOS ---")
    if alerts.get("error"):
        print(f"    NOTE: {alerts['error']}")
    elif alerts["total"] == 0:
        print("    No active alerts.")
    else:
        for a in alerts.get("alerts", []):
            sev = {0: "INFO", 1: "WARN", 2: "CRIT"}.get(a["severity"], "?")
            print(f"    [{sev}] [{a['category']}] {a['title']}")
    print(f"    Total: {alerts.get('total', 0)} "
          f"(critical={alerts.get('critical', 0)}, "
          f"warnings={alerts.get('warnings', 0)})")

    print()
    print("=" * 70)
    print()

    # Determine exit code
    if system.get("status") == "critical" or alerts.get("critical", 0) > 0:
        # Return exit code will be set by caller
        pass


def print_summary_line() -> None:
    """Print a one-line summary suitable for monitoring or status bars."""
    system = collect_system_health()
    try:
        alerts = collect_alert_summary()
    except Exception:
        alerts = {"total": 0, "critical": 0, "warnings": 0}

    print(
        f"status={system.get('status', 'unknown')} "
        f"db={system['checks'].get('db', {}).get('status', '?')} "
        f"disk={system['checks'].get('disk', {}).get('status', '?')} "
        f"storage={system['checks'].get('storage_box', {}).get('status', '?')} "
        f"alerts={alerts.get('total', 0)} "
        f"critical={alerts.get('critical', 0)} "
        f"warnings={alerts.get('warnings', 0)}"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extra Consultoria — Health Dashboard",
    )
    p.add_argument("--summary", action="store_true",
                   help="One-line summary suitable for monitoring")
    p.add_argument("--json", action="store_true",
                   help="JSON output")
    p.add_argument("--watch", action="store_true",
                   help="Auto-refresh every 60 seconds")
    p.add_argument("--interval", type=int, default=60,
                   help="Refresh interval in seconds (default: 60)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    set_correlation_id()

    if args.watch:
        try:
            while True:
                print_dashboard()
                print(f"  Auto-refresh every {args.interval}s (Ctrl+C to stop)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n  Dashboard stopped.")
            return 0

    if args.summary:
        print_summary_line()
        return 0

    if args.json:
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "host": os.uname().nodename,
            "system": collect_system_health(),
            "crawl": collect_crawl_stats(),
            "backup": collect_backup_status(),
        }
        data["alerts"] = collect_alert_summary()
        print(json.dumps(data, ensure_ascii=False, default=str, indent=2))
        return 0

    print_dashboard()

    # Exit code
    system = collect_system_health()
    alerts = collect_alert_summary()
    if system.get("status") == "critical" or alerts.get("critical", 0) > 0:
        return 2
    if system.get("status") == "warning" or alerts.get("warnings", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
