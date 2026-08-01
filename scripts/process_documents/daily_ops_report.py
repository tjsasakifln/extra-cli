"""Daily coverage / update report for continuous operation proof (7-day campaign).

Does not claim VPS_OPERATIONAL. Produces a dated JSON+MD snapshot under meta/daily_reports/
that can be accumulated for a seven-day continuous evidence pack.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.entity_queue import (
    SLA_HOURS,
    build_sla_alerts,
    load_entity_queue,
    queue_summary,
)
from scripts.process_documents.ops_health import collect_ops_health
from scripts.process_documents.storage import ensure_roots, write_json


def build_daily_ops_report(
    *,
    discoveries: list[Any] | None = None,
    collect_summary: dict[str, Any] | None = None,
    meta_root: Path | None = None,
    raw_root: Path | None = None,
    day: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    day = day or datetime.now(UTC).date().isoformat()
    raw, meta = ensure_roots(raw_root=raw_root, meta_root=meta_root)
    targets = discoveries or []
    queue = load_entity_queue(meta_root=meta)
    qsum = queue_summary(targets, queue) if targets else {
        "eligible_count": 0,
        "overdue_count": 0,
        "never_succeeded_count": 0,
        "within_sla_count": 0,
        "lag_cleared": True,
        "sla_hours": SLA_HOURS,
    }
    sla = build_sla_alerts(targets, queue) if targets else []
    health = collect_ops_health(
        discoveries=targets,
        meta_root=meta,
        raw_root=raw,
        persist=False,
    )
    coll = collect_summary or {}
    report = {
        "day": day,
        "generated_at": datetime.now(UTC).isoformat(),
        "coverage": {
            "eligible_entities": qsum.get("eligible_count"),
            "within_sla": qsum.get("within_sla_count"),
            "overdue": qsum.get("overdue_count"),
            "never_succeeded": qsum.get("never_succeeded_count"),
            "lag_cleared": qsum.get("lag_cleared"),
            "sla_hours": SLA_HOURS,
        },
        "collect": {
            "selection_policy": coll.get("selection_policy"),
            "multi_source": coll.get("multi_source"),
            "count": coll.get("count"),
            "by_status": coll.get("by_status"),
            "selected_canonical_ids": coll.get("selected_canonical_ids"),
            "drain_stop_reason": coll.get("drain_stop_reason"),
            "batches": coll.get("batches"),
            "process_cards": coll.get("process_cards"),
        },
        "sla_alerts": {
            "count": len(sla),
            "sample": sla[:15],
        },
        "health": {
            "healthy": health.get("healthy"),
            "warning": health.get("warning"),
            "alert_count": len(health.get("alerts") or []),
            "disk": health.get("disk"),
            "directories": health.get("directories"),
            "git_sha": health.get("git_sha"),
            "adapter_version": health.get("adapter_version"),
        },
    }
    if persist:
        out_dir = meta / "daily_reports"
        write_json(out_dir / f"{day}.json", report)
        md = _render_md(report)
        (out_dir / f"{day}.md").write_text(md, encoding="utf-8")
        write_json(meta / "daily-ops-report-latest.json", report)
    return report


def _render_md(report: dict[str, Any]) -> str:
    cov = report.get("coverage") or {}
    coll = report.get("collect") or {}
    health = report.get("health") or {}
    lines = [
        f"# Process documents daily report — {report.get('day')}",
        "",
        f"Generated: `{report.get('generated_at')}`",
        "",
        "## Coverage / lag",
        f"- Eligible: **{cov.get('eligible_entities')}**",
        f"- Within SLA: **{cov.get('within_sla')}**",
        f"- Overdue (>{cov.get('sla_hours')}h): **{cov.get('overdue')}**",
        f"- Never succeeded: **{cov.get('never_succeeded')}**",
        f"- Lag cleared: **{cov.get('lag_cleared')}**",
        "",
        "## Collect",
        f"- Policy: `{coll.get('selection_policy')}` multi_source=`{coll.get('multi_source')}`",
        f"- Entities in run: **{coll.get('count')}**",
        f"- By status: `{coll.get('by_status')}`",
        f"- Drain stop: `{coll.get('drain_stop_reason')}`",
        "",
        "## Health",
        f"- Healthy: **{health.get('healthy')}** (warnings={health.get('warning')})",
        f"- Alerts: **{health.get('alert_count')}**",
        f"- Deploy: `{health.get('git_sha')}` / `{health.get('adapter_version')}`",
        "",
        "## SLA sample",
    ]
    for a in (report.get("sla_alerts") or {}).get("sample") or []:
        lines.append(f"- `{a.get('canonical_id')}`: {a.get('message')}")
    if not (report.get("sla_alerts") or {}).get("sample"):
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines) + "\n"


def list_daily_report_streak(meta_root: Path | None = None) -> dict[str, Any]:
    """Count consecutive daily report files (for 7-day continuous proof tracking)."""
    _, meta = ensure_roots(meta_root=meta_root)
    out_dir = meta / "daily_reports"
    if not out_dir.is_dir():
        return {"days_present": 0, "days": [], "seven_day_ready": False}
    days = sorted(p.stem for p in out_dir.glob("????-??-??.json"))
    return {
        "days_present": len(days),
        "days": days,
        "seven_day_ready": len(days) >= 7,
        "path": str(out_dir),
    }
