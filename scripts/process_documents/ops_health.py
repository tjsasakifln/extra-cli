"""Operational health for process-documents daily path.

Timer active ≠ healthy service. Audits:

- raw/meta directories, user, env, deployed package version
- disk free space on roots
- optional PostgreSQL free space (when DSN available)
- abnormal growth signals from queue / manifests
- SLA lag alerts (delegates to entity_queue)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents import ADAPTER_VERSION
from scripts.process_documents.entity_queue import (
    SLA_HOURS,
    build_sla_alerts,
    load_entity_queue,
    queue_summary,
)
from scripts.process_documents.storage import DEFAULT_META_ROOT, DEFAULT_RAW_ROOT, ensure_roots, write_json

DISK_WARN_PCT = float(os.environ.get("PROCESS_DOCUMENTS_DISK_WARN_PCT", "85"))
DISK_CRIT_PCT = float(os.environ.get("PROCESS_DOCUMENTS_DISK_CRIT_PCT", "95"))
DB_WARN_PCT = float(os.environ.get("PROCESS_DOCUMENTS_DB_WARN_PCT", "85"))
GROWTH_WARN_RATIO = float(os.environ.get("PROCESS_DOCUMENTS_GROWTH_WARN_RATIO", "3.0"))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _git_sha(cwd: Path | None = None) -> str | None:
    try:
        git = shutil.which("git")
        if not git:
            return None
        out = subprocess.check_output(  # noqa: S603 — fixed argv [git, rev-parse, HEAD]
            [git, "rev-parse", "HEAD"],
            cwd=str(cwd or Path(__file__).resolve().parents[2]),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def disk_usage_report(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {"path": str(path), "ok": False, "error": str(exc)}
    used_pct = (usage.used / usage.total * 100.0) if usage.total else 100.0
    severity = "ok"
    if used_pct >= DISK_CRIT_PCT:
        severity = "critical"
    elif used_pct >= DISK_WARN_PCT:
        severity = "warning"
    return {
        "path": str(path),
        "ok": severity == "ok",
        "severity": severity,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(used_pct, 2),
    }


def audit_directories(raw: Path, meta: Path) -> dict[str, Any]:
    checks = {}
    for label, p in (("raw_root", raw), ("meta_root", meta)):
        exists = p.exists()
        is_dir = p.is_dir() if exists else False
        writable = os.access(p, os.W_OK) if is_dir else False
        checks[label] = {
            "path": str(p),
            "exists": exists,
            "is_dir": is_dir,
            "writable": writable,
            "ok": exists and is_dir and writable,
        }
    return checks


def postgres_space_report(dsn: str | None = None) -> dict[str, Any]:
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        return {"ok": None, "skipped": True, "reason": "no DSN configured"}
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      pg_database_size(current_database()) AS db_size,
                      (
                        SELECT setting::bigint * pg_size_bytes(unit)
                        FROM pg_settings
                        WHERE name = 'data_directory'
                      ) AS ignored
                    """
                )
                # Prefer filesystem of data directory when possible
                cur.execute("SHOW data_directory")
                data_dir = cur.fetchone()[0]
                cur.execute("SELECT pg_database_size(current_database())")
                db_size = int(cur.fetchone()[0])
        disk = disk_usage_report(Path(data_dir))
        used_pct = float(disk.get("used_percent") or 0)
        severity = "ok"
        if used_pct >= DB_WARN_PCT + 10:
            severity = "critical"
        elif used_pct >= DB_WARN_PCT:
            severity = "warning"
        return {
            "ok": severity == "ok",
            "severity": severity,
            "database_size_bytes": db_size,
            "data_directory": data_dir,
            "disk": disk,
            "skipped": False,
        }
    except Exception as exc:  # noqa: BLE001 — health must not crash
        return {"ok": False, "skipped": False, "error": str(exc), "severity": "warning"}


def abnormal_growth_signals(meta: Path) -> list[dict[str, Any]]:
    """Compare latest vs previous batch sizes if available."""
    signals: list[dict[str, Any]] = []
    latest = meta / "collect-batch-latest.json"
    prev = meta / "collect-batch-previous.json"
    if not latest.is_file():
        return signals
    try:
        cur = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return signals
    cur_count = int(cur.get("count") or 0)
    cur_docs = 0
    for r in cur.get("results") or []:
        if isinstance(r, dict):
            cur_docs += int(r.get("documents_downloaded") or 0) + int(r.get("documents_unchanged") or 0)
    if prev.is_file():
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            old_count = int(old.get("count") or 0) or 1
            old_docs = 0
            for r in old.get("results") or []:
                if isinstance(r, dict):
                    old_docs += int(r.get("documents_downloaded") or 0) + int(
                        r.get("documents_unchanged") or 0
                    )
            old_docs = old_docs or 1
            if cur_docs / old_docs >= GROWTH_WARN_RATIO and cur_docs > 50:
                signals.append(
                    {
                        "severity": "warning",
                        "kind": "abnormal_document_growth",
                        "previous_docs": old_docs,
                        "current_docs": cur_docs,
                        "ratio": round(cur_docs / old_docs, 2),
                        "message": f"Document volume grew {cur_docs / old_docs:.1f}x vs previous batch",
                    }
                )
            if cur_count / old_count >= GROWTH_WARN_RATIO and cur_count > 20:
                signals.append(
                    {
                        "severity": "warning",
                        "kind": "abnormal_entity_batch_growth",
                        "previous_entities": old_count,
                        "current_entities": cur_count,
                        "ratio": round(cur_count / old_count, 2),
                        "message": f"Entity batch size grew {cur_count / old_count:.1f}x",
                    }
                )
        except (OSError, json.JSONDecodeError, ZeroDivisionError):
            pass
    # Rotate previous snapshot pointer (caller may also do this)
    return signals


def collect_ops_health(
    *,
    discoveries: list[Any] | None = None,
    meta_root: Path | None = None,
    raw_root: Path | None = None,
    dsn: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    raw, meta = ensure_roots(raw_root=raw_root, meta_root=meta_root)
    dirs = audit_directories(raw, meta)
    disk_raw = disk_usage_report(raw)
    disk_meta = disk_usage_report(meta)
    db = postgres_space_report(dsn)
    growth = abnormal_growth_signals(meta)

    queue = load_entity_queue(meta_root=meta)
    targets = discoveries or []
    sla = build_sla_alerts(targets, queue) if targets else []
    qsum = queue_summary(targets, queue) if targets else {
        "eligible_count": 0,
        "overdue_count": 0,
        "lag_cleared": True,
        "sla_hours": SLA_HOURS,
    }

    alerts: list[dict[str, Any]] = []
    for label, disk in (("raw", disk_raw), ("meta", disk_meta)):
        if disk.get("severity") in ("warning", "critical"):
            alerts.append(
                {
                    "severity": disk["severity"],
                    "kind": "disk_space",
                    "target": label,
                    "message": f"Disk {label} at {disk.get('used_percent')}% used on {disk.get('path')}",
                    "next_action": "free space or expand volume before next incremental",
                }
            )
    if db.get("severity") in ("warning", "critical"):
        alerts.append(
            {
                "severity": db["severity"],
                "kind": "database_space",
                "message": f"Database volume pressure: {db.get('severity')}",
                "next_action": "vacuum/archive or expand DB volume",
                "detail": db,
            }
        )
    for g in growth:
        alerts.append(g)
    for a in sla:
        alerts.append(
            {
                "severity": a["severity"],
                "kind": "sla_lag",
                "canonical_id": a["canonical_id"],
                "message": a["message"],
                "next_action": a["next_action"],
                "lag_hours": a.get("lag_hours"),
            }
        )
    for label, info in dirs.items():
        if not info.get("ok"):
            alerts.append(
                {
                    "severity": "critical",
                    "kind": "directory_missing",
                    "target": label,
                    "message": f"Process documents {label} not ready: {info}",
                    "next_action": f"create and chown {info.get('path')} for service user",
                }
            )

    report = {
        "generated_at": _now_iso(),
        "adapter_version": ADAPTER_VERSION,
        "git_sha": _git_sha(),
        "hostname": platform.node(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME"),
        "env": {
            "PROCESS_DOCUMENTS_RAW_ROOT": str(raw),
            "PROCESS_DOCUMENTS_META_ROOT": str(meta),
            "default_raw": str(DEFAULT_RAW_ROOT),
            "default_meta": str(DEFAULT_META_ROOT),
        },
        "directories": dirs,
        "disk": {"raw": disk_raw, "meta": disk_meta},
        "database": db,
        "queue": qsum,
        "sla_alert_count": len(sla),
        "sla_alerts_sample": sla[:20],
        "alerts": alerts,
        "healthy": not any(a.get("severity") == "critical" for a in alerts),
        "warning": any(a.get("severity") == "warning" for a in alerts),
    }
    if persist:
        write_json(meta / "ops-health-latest.json", report)
        # also append ledger
        ledger = meta / "ops-health.jsonl"
        with ledger.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "generated_at": report["generated_at"],
                        "healthy": report["healthy"],
                        "alert_count": len(alerts),
                        "overdue_count": qsum.get("overdue_count"),
                        "git_sha": report.get("git_sha"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return report


def emit_alerts_to_pipeline(alerts: list[dict[str, Any]], *, dry_run: bool = True) -> list[dict[str, Any]]:
    """Optional bridge to scripts.ops.alert_pipeline (never raises)."""
    out: list[dict[str, Any]] = []
    try:
        from scripts.ops.alert_pipeline import AlertEvent, dispatch_alert
    except Exception as exc:  # noqa: BLE001
        return [{"error": f"alert_pipeline unavailable: {exc}"}]
    for a in alerts:
        ev = AlertEvent(
            title=f"[process_documents] {a.get('kind', 'alert')}",
            body=str(a.get("message") or a),
            severity=str(a.get("severity") or "warning"),
            source="process_documents.ops_health",
            entity_id=a.get("canonical_id"),
            next_action=a.get("next_action"),
            extra={k: v for k, v in a.items() if k not in {"message", "severity", "next_action"}},
        )
        try:
            out.append(dispatch_alert(ev, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001
            out.append({"error": str(exc), "alert": a})
    return out
