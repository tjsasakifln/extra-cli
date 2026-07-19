"""Operational gate monitor (DoD §23 remainder of observability).

Monitors, with honest unknown when evidence is missing:
- freshness por fonte (SLA from registry + latest/run history)
- coverage por capability (coverage contract offline summary)
- último backup válido (backups/ dumps + proof reports)
- falhas de migration (ledger / apply log / schema_migrations when DSN)
- timers atrasados (deploy/systemd *.timer + systemctl when available)

Never greenwashes empty state into "healthy production".
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKUP_DIRS = (
    REPO / "backups" / "local-proof",
    REPO / "backups",
    REPO / "output" / "backups",
)
TIMER_DIR = REPO / "deploy" / "systemd"
MIGRATION_DIRS = (
    REPO / "migrations",
    REPO / "db" / "migrations",
    REPO / "sql" / "migrations",
    REPO / "scripts" / "sql",
)
MIGRATION_LEDGER = REPO / "output" / "ops" / "migration_ledger.jsonl"
COVERAGE_ARTIFACTS = (
    REPO / "output" / "coverage" / "contract-report.json",
    REPO / "output" / "coverage" / "coverage-gate-report.json",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _check(
    name: str,
    status: str,
    message: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,  # ok | warn | crit | unknown | configured
        "message": message,
        "metrics": metrics or {},
    }


# --- Freshness por fonte -----------------------------------------------------


def monitor_freshness_by_source() -> dict[str, Any]:
    """Freshness per priority source using health module + registry SLA."""
    try:
        from scripts.ops.health import PRIORITY_SOURCES, collect_health

        code, payload = collect_health(include_fixture=True)
        sources = payload.get("sources") or {}
        rows = []
        for src in PRIORITY_SOURCES:
            info = sources.get(src) or {}
            op = info.get("operational_freshness") or info.get("freshness") or "unknown"
            rows.append(
                {
                    "source": src,
                    "operational_freshness": op,
                    "collection_freshness": info.get("collection_freshness"),
                    "sla_hours": info.get("freshness_sla_hours"),
                    "last_success": info.get("last_success"),
                }
            )
        statuses = {r["operational_freshness"] for r in rows}
        if not rows:
            status = "unknown"
            msg = "no source freshness rows"
        elif "stale" in statuses:
            status = "warn"
            msg = "one or more sources operationally stale"
        elif statuses <= {"current", "ok", "fresh"}:
            status = "ok"
            msg = "priority sources within SLA (or current)"
        else:
            status = "unknown"
            msg = "freshness partially unknown — not claimed current"
        return _check(
            "freshness_by_source",
            status,
            msg,
            {
                "sources": rows,
                "health_exit": code,
                "monitored": True,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _check(
            "freshness_by_source",
            "unknown",
            f"freshness monitor error: {exc}",
            {"monitored": True},
        )


# --- Coverage por capability -------------------------------------------------


def monitor_coverage_by_capability() -> dict[str, Any]:
    """Surface capability coverage metrics without inventing 95%."""
    metrics: dict[str, Any] = {"monitored": True, "capabilities": []}
    # Prefer on-disk contract report
    for path in COVERAGE_ARTIFACTS:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                metrics["artifact"] = str(path)
                metrics["artifact_keys"] = list(data.keys())[:20]
                # Extract metric rows if present
                report_metrics = data.get("metrics") or data.get("contract_metrics") or []
                if isinstance(report_metrics, dict):
                    for mid, row in report_metrics.items():
                        metrics["capabilities"].append(
                            {
                                "id": mid,
                                "pct": row.get("pct") if isinstance(row, dict) else None,
                                "numerator": row.get("numerator") if isinstance(row, dict) else None,
                                "denominator": row.get("denominator") if isinstance(row, dict) else None,
                            }
                        )
                elif isinstance(report_metrics, list):
                    for row in report_metrics[:30]:
                        if isinstance(row, dict):
                            metrics["capabilities"].append(
                                {
                                    "id": row.get("id") or row.get("metric_id"),
                                    "pct": row.get("pct"),
                                    "numerator": row.get("numerator"),
                                    "denominator": row.get("denominator"),
                                }
                            )
                return _check(
                    "coverage_by_capability",
                    "ok",
                    f"coverage contract artifact loaded ({path.name})",
                    metrics,
                )
            except Exception as exc:  # noqa: BLE001
                metrics["load_error"] = str(exc)

    # Offline fallback: metric ids from coverage_contract module
    try:
        from scripts.coverage.coverage_contract import ALL_METRIC_IDS, READY_SEMANTICS

        metrics["metric_ids"] = list(ALL_METRIC_IDS)[:40]
        metrics["ready_semantics_keys"] = list(getattr(READY_SEMANTICS, "keys", lambda: [])())
        if hasattr(READY_SEMANTICS, "keys"):
            metrics["ready_semantics_keys"] = list(READY_SEMANTICS.keys())[:20]
        return _check(
            "coverage_by_capability",
            "configured",
            "coverage metric catalog available; no live contract artifact — not claiming coverage %",
            metrics,
        )
    except Exception as exc:  # noqa: BLE001
        return _check(
            "coverage_by_capability",
            "unknown",
            f"coverage catalog unavailable: {exc}",
            metrics,
        )


# --- Último backup válido ----------------------------------------------------


def monitor_last_backup() -> dict[str, Any]:
    candidates: list[Path] = []
    for d in BACKUP_DIRS:
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".dump", ".sql", ".backup", ".gz"}:
                candidates.append(p)
            if p.is_file() and p.name.startswith("proof-report") and p.suffix == ".json":
                candidates.append(p)
    if not candidates:
        return _check(
            "last_valid_backup",
            "unknown",
            "no backup dump/proof found under backups/",
            {"monitored": True, "search_dirs": [str(d) for d in BACKUP_DIRS]},
        )

    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    newest = max(candidates, key=mtime)
    age_h = (_now().timestamp() - mtime(newest)) / 3600
    size = newest.stat().st_size if newest.exists() else 0
    # Prefer dumps over reports for "valid backup"
    dumps = [p for p in candidates if p.suffix.lower() in {".dump", ".sql", ".backup", ".gz"}]
    valid = None
    if dumps:
        valid = max(dumps, key=mtime)
        age_h = (_now().timestamp() - mtime(valid)) / 3600
        size = valid.stat().st_size
    path = valid or newest
    status = "ok" if size > 0 else "crit"
    if age_h > 24 * 7:
        status = "warn"
    return _check(
        "last_valid_backup",
        status,
        f"last backup {path.name} size={size} age_h={age_h:.1f}",
        {
            "monitored": True,
            "path": str(path),
            "size_bytes": size,
            "age_hours": round(age_h, 2),
            "candidates": len(candidates),
        },
    )


# --- Falhas de migration -----------------------------------------------------


def monitor_migration_failures() -> dict[str, Any]:
    metrics: dict[str, Any] = {"monitored": True}
    # 1) Ledger of apply attempts
    failures: list[dict[str, Any]] = []
    if MIGRATION_LEDGER.is_file():
        for line in MIGRATION_LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("status") or row.get("result") or "").lower() in {
                "fail",
                "failed",
                "error",
            }:
                failures.append(row)
        metrics["ledger"] = str(MIGRATION_LEDGER)
        metrics["ledger_failures"] = len(failures)

    # 2) Migration files present
    mig_files: list[str] = []
    for d in MIGRATION_DIRS:
        if d.is_dir():
            for p in sorted(d.glob("*.sql")):
                mig_files.append(str(p.relative_to(REPO)))
    metrics["migration_files"] = len(mig_files)
    metrics["migration_sample"] = mig_files[:10]

    # 3) Optional DB: schema_migrations / alembic
    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if dsn:
        try:
            try:
                import psycopg2 as pg
            except ImportError:
                import psycopg as pg  # type: ignore

            conn = pg.connect(dsn, connect_timeout=5)
            try:
                with conn.cursor() as cur:
                    # Try common tables
                    applied = None
                    for table in (
                        "schema_migrations",
                        "alembic_version",
                        "django_migrations",
                    ):
                        try:
                            cur.execute(
                                "SELECT count(*) FROM information_schema.tables "
                                "WHERE table_schema='public' AND table_name=%s",
                                (table,),
                            )
                            if cur.fetchone()[0]:
                                # table is from fixed internal allow-list above (not user input)
                                if table == "alembic_version":
                                    cur.execute(f"SELECT version_num FROM {table}")  # noqa: S608 — fixed allow-list table name
                                    applied = [r[0] for r in cur.fetchall()]
                                else:
                                    cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — fixed allow-list table name
                                    applied = cur.fetchone()[0]
                                metrics["schema_table"] = table
                                metrics["applied"] = applied
                                break
                        except Exception:
                            conn.rollback()
                            continue
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            metrics["db_error"] = str(exc)

    if failures:
        return _check(
            "migration_failures",
            "crit",
            f"{len(failures)} failed migration entries in ledger",
            metrics,
        )
    if mig_files or metrics.get("schema_table"):
        return _check(
            "migration_failures",
            "ok",
            "migration surface monitored; no recorded failures in ledger",
            metrics,
        )
    return _check(
        "migration_failures",
        "unknown",
        "no migration files/ledger found — monitoring path ready",
        metrics,
    )


# --- Timers atrasados --------------------------------------------------------


_ONCALENDAR = re.compile(r"^\s*OnCalendar\s*=\s*(.+)$", re.I | re.M)


def monitor_delayed_timers() -> dict[str, Any]:
    metrics: dict[str, Any] = {"monitored": True, "timers_in_repo": []}
    if TIMER_DIR.is_dir():
        for p in sorted(TIMER_DIR.glob("*.timer")):
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _ONCALENDAR.search(text)
            metrics["timers_in_repo"].append(
                {
                    "unit": p.name,
                    "on_calendar": m.group(1).strip() if m else None,
                }
            )
    metrics["timer_count"] = len(metrics["timers_in_repo"])

    # systemctl list-timers if available
    delayed: list[dict[str, Any]] = []
    host_active = False
    try:
        r = subprocess.run(  # noqa: S603 — fixed systemctl argv, shell=False
            ["systemctl", "list-timers", "--all", "--no-pager", "--output=json"],  # noqa: S607 — systemctl from PATH when present
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip().startswith("["):
            host_active = True
            timers = json.loads(r.stdout)
            now = _now()
            for t in timers:
                unit = str(t.get("unit") or "")
                if not unit.startswith("extra-") and "extra" not in unit:
                    continue
                next_ts = t.get("next") or t.get("next_usec")
                # last / next may be unix usec
                last = t.get("last") or t.get("last_usec")
                # Heuristic: if last is far and next is in the past → delayed
                try:
                    if isinstance(next_ts, (int, float)) and next_ts > 1e12:
                        next_dt = datetime.fromtimestamp(next_ts / 1e6, tz=UTC)
                        if next_dt < now - timedelta(minutes=30):
                            delayed.append({"unit": unit, "next": next_dt.isoformat()})
                except (OverflowError, OSError, ValueError):
                    pass
                _ = last
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        host_active = False

    metrics["host_systemctl"] = host_active
    metrics["delayed"] = delayed

    if delayed:
        return _check(
            "delayed_timers",
            "warn",
            f"{len(delayed)} extra-* timers appear delayed on host",
            metrics,
        )
    if metrics["timer_count"] == 0:
        return _check(
            "delayed_timers",
            "unknown",
            "no timer units in deploy/systemd",
            metrics,
        )
    if host_active:
        return _check(
            "delayed_timers",
            "ok",
            "extra timers present; none flagged delayed",
            metrics,
        )
    return _check(
        "delayed_timers",
        "configured",
        f"{metrics['timer_count']} timer units in repo; systemctl not available or no extra units on host",
        metrics,
    )


def collect_report() -> dict[str, Any]:
    checks = [
        monitor_freshness_by_source(),
        monitor_coverage_by_capability(),
        monitor_last_backup(),
        monitor_migration_failures(),
        monitor_delayed_timers(),
    ]
    statuses = {c["status"] for c in checks}
    if "crit" in statuses:
        overall = "crit"
    elif "warn" in statuses:
        overall = "warn"
    elif statuses <= {"ok", "configured"}:
        overall = "ok"
    else:
        overall = "degraded"
    return {
        "generated_at": _now().isoformat().replace("+00:00", "Z"),
        "overall": overall,
        "checks": checks,
        "monitored": {
            "freshness_by_source": True,
            "coverage_by_capability": True,
            "last_valid_backup": True,
            "migration_failures": True,
            "delayed_timers": True,
        },
        "claims": {
            "allowed": [
                "Reportar freshness/coverage/backup/migrations/timers com status honesto",
                "overall=degraded/unknown quando evidência incompleta",
            ],
            "forbidden": [
                "Cobertura operacional 95% a partir deste monitor",
                "Timers VPS saudáveis só porque arquivos existem no repo",
                "LOCAL_READY",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ops gate monitor (DoD §23)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fail-on-warn", action="store_true")
    args = p.parse_args(argv)
    report = collect_report()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
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
