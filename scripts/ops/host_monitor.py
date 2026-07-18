"""Local host / resource monitoring (DoD §23).

Reports disk, memory, load average, journald config presence, and optional
PostgreSQL growth signals. Fail-closed thresholds; never invents green.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
JOURNALD_CONF = REPO / "config" / "journald" / "00-extra-consultoria.conf"

# Soft thresholds (warn) — not production SLAs.
DISK_WARN_PCT = 85.0
DISK_CRIT_PCT = 95.0
MEM_WARN_PCT = 90.0
LOAD_WARN_FACTOR = 2.0  # load1 > cpus * factor → warn


@dataclass
class CheckResult:
    name: str
    status: str  # ok | warn | crit | unknown | configured
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_meminfo() -> dict[str, int]:
    path = Path("/proc/meminfo")
    if not path.exists():
        return {}
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        parts = v.strip().split()
        if parts and parts[0].isdigit():
            out[k] = int(parts[0])  # kB
    return out


def _cpu_count() -> int:
    return os.cpu_count() or 1


def _loadavg() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except (OSError, AttributeError):
        return None


def check_disk(path: str = "/") -> CheckResult:
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return CheckResult("disk", "unknown", f"disk_usage failed: {exc}")
    used_pct = (usage.used / usage.total) * 100 if usage.total else 0.0
    metrics = {
        "path": path,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_pct": round(used_pct, 2),
    }
    if used_pct >= DISK_CRIT_PCT:
        return CheckResult("disk", "crit", f"disk {used_pct:.1f}% used", metrics)
    if used_pct >= DISK_WARN_PCT:
        return CheckResult("disk", "warn", f"disk {used_pct:.1f}% used", metrics)
    return CheckResult("disk", "ok", f"disk {used_pct:.1f}% used", metrics)


def check_memory() -> CheckResult:
    info = _read_meminfo()
    if not info or "MemTotal" not in info:
        return CheckResult("memory", "unknown", "/proc/meminfo unavailable")
    total = info["MemTotal"]
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(total - available, 0)
    used_pct = (used / total) * 100 if total else 0.0
    metrics = {
        "total_kb": total,
        "available_kb": available,
        "used_kb": used,
        "used_pct": round(used_pct, 2),
    }
    if used_pct >= MEM_WARN_PCT:
        return CheckResult("memory", "warn", f"memory {used_pct:.1f}% used", metrics)
    return CheckResult("memory", "ok", f"memory {used_pct:.1f}% used", metrics)


def check_load() -> CheckResult:
    loads = _loadavg()
    cpus = _cpu_count()
    if loads is None:
        return CheckResult("load", "unknown", "loadavg unavailable on this OS")
    load1, load5, load15 = loads
    metrics = {
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "cpus": cpus,
        "warn_threshold": cpus * LOAD_WARN_FACTOR,
    }
    if load1 > cpus * LOAD_WARN_FACTOR:
        return CheckResult(
            "load",
            "warn",
            f"load1={load1:.2f} > {cpus * LOAD_WARN_FACTOR:.1f}",
            metrics,
        )
    return CheckResult("load", "ok", f"load1={load1:.2f} cpus={cpus}", metrics)


def check_journald_config(conf: Path | None = None) -> CheckResult:
    path = conf or JOURNALD_CONF
    if not path.is_file():
        return CheckResult(
            "journald_retention",
            "crit",
            f"missing project journald config: {path}",
            {"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")
    required = ("SystemMaxUse=", "MaxRetentionSec=")
    missing = [k for k in required if k not in text]
    metrics = {
        "path": str(path),
        "applied_on_host": Path("/etc/systemd/journald.conf.d/00-extra-consultoria.conf").is_file(),
        "required_keys_present": not missing,
    }
    if missing:
        return CheckResult(
            "journald_retention",
            "crit",
            f"config incomplete missing {missing}",
            metrics,
        )
    status = "configured"
    msg = "project journald retention config present"
    if metrics["applied_on_host"]:
        msg += " and drop-in applied on host"
        status = "ok"
    else:
        msg += " (not yet installed under /etc — local stage source of truth)"
    return CheckResult("journald_retention", status, msg, metrics)


def check_postgres_growth(dsn: str | None = None) -> CheckResult:
    """Optional: DB size + dead tuples + autovacuum hint when DSN available."""
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        return CheckResult(
            "postgres",
            "unknown",
            "no DSN (LOCAL_DATALAKE_DSN/DATABASE_URL) — skip PG growth",
        )
    try:
        try:
            import psycopg2 as _pg  # project standard

            conn = _pg.connect(dsn, connect_timeout=5)
        except ImportError:
            import psycopg as _pg  # optional v3

            conn = _pg.connect(dsn, connect_timeout=5)

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_database_size(current_database())")
                size = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT COALESCE(SUM(n_dead_tup), 0), COALESCE(SUM(n_live_tup), 0)
                    FROM pg_stat_user_tables
                    """
                )
                dead, live = cur.fetchone()
                cur.execute(
                    """
                    SELECT COUNT(*) FROM pg_stat_user_tables
                    WHERE last_autovacuum IS NOT NULL
                    """
                )
                auto_n = cur.fetchone()[0]
        finally:
            conn.close()
        metrics = {
            "db_size_bytes": int(size),
            "dead_tuples": int(dead),
            "live_tuples": int(live),
            "tables_with_autovacuum": int(auto_n),
        }
        return CheckResult(
            "postgres",
            "ok",
            f"db_size={size} dead_tuples={dead} autovacuum_tables={auto_n}",
            metrics,
        )
    except Exception as exc:  # noqa: BLE001 — health must not crash
        return CheckResult("postgres", "unknown", f"pg query failed: {exc}")


def collect_host_report(
    *,
    disk_path: str = "/",
    dsn: str | None = None,
    include_postgres: bool = True,
) -> dict[str, Any]:
    checks = [
        check_journald_config(),
        check_disk(disk_path),
        check_memory(),
        check_load(),
    ]
    if include_postgres:
        checks.append(check_postgres_growth(dsn))
    statuses = {c.status for c in checks}
    if "crit" in statuses:
        overall = "crit"
    elif "warn" in statuses:
        overall = "warn"
    elif statuses <= {"ok", "configured"}:
        overall = "ok"
    else:
        overall = "degraded"
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "overall": overall,
        "checks": [c.to_dict() for c in checks],
        "claims": {
            "allowed": [
                "Report disk/memory/load from live host stats",
                "Journald retention configured in-repo; applied_on_host may be false locally",
            ],
            "forbidden": [
                "Claim VPS timers healthy from host_monitor alone",
                "Treat unknown postgres as green",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Host/resource monitor (DoD §23)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--disk-path", default="/")
    p.add_argument("--no-postgres", action="store_true")
    p.add_argument("--fail-on-warn", action="store_true")
    args = p.parse_args(argv)
    report = collect_host_report(
        disk_path=args.disk_path,
        include_postgres=not args.no_postgres,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"overall={report['overall']} at={report['generated_at']}")
        for c in report["checks"]:
            print(f"  [{c['status']}] {c['name']}: {c['message']}")
    if report["overall"] == "crit":
        return 2
    if args.fail_on_warn and report["overall"] in {"warn", "degraded"}:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
