"""Entity activity classification using sources independent of the document crawler.

An entity is ACTIVE when there is evidence of at least one relevant tender,
contracting or contract in the last 36 months from:
  - entity source registry evidence / platforms
  - optional DB tables (opportunities, contracts) when DSN available
  - optional PNCP presence signals already stored in registry evidences

Does not use the document crawler under evaluation as sole evidence.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.process_documents.discovery import load_discovery
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import ActivityStatus
from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots, write_json

ACTIVITY_LOOKBACK_MONTHS = 36
ACTIVITY_CRITERIA_VERSION = "activity_v1_independent_36m"


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (TypeError, ValueError):
        return None


def _within_lookback(ts: datetime | None, *, months: int = ACTIVITY_LOOKBACK_MONTHS) -> bool:
    if ts is None:
        return False
    return ts >= _now() - timedelta(days=int(months * 30.44))


def classify_activity_for_entity(
    discovery: EntityDocumentDiscovery,
    *,
    db_signals: dict[str, list[str]] | None = None,
) -> EntityDocumentDiscovery:
    """Mutate/return discovery with activity_status and evidence list."""
    evidence: list[str] = []
    db_signals = db_signals or {}

    # Registry operational timestamps (independent of document crawler runs)
    for ev in discovery.evidences or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") in (
            "pipeline_evidence",
            "pncp_probe",
            "ciga_municipio_expand",
            "contract_presence",
            "opportunity_presence",
        ):
            evidence.append(f"registry_evidence:{ev.get('type')}")
        checked = _parse_ts(ev.get("checked_at") or ev.get("at") or ev.get("timestamp"))
        if _within_lookback(checked):
            evidence.append(f"registry_evidence_fresh:{ev.get('type')}")

    # Platform membership as weak historical signal only when status advanced
    cnpj_digits = "".join(ch for ch in (discovery.cnpj or "") if ch.isdigit())
    invalid_cnpj = len(cnpj_digits) < 8 or set(cnpj_digits) == {"0"}
    if discovery.access_status in ("collected", "verified", "operational") and not invalid_cnpj:
        evidence.append(f"registry_access_status:{discovery.access_status}")
    if "pncp" in {p.lower() for p in discovery.platforms}:
        evidence.append("platform:pncp")
    if "pncp_contracts" in {p.lower() for p in discovery.platforms}:
        evidence.append("platform:pncp_contracts")

    # DB independent signals
    for sig in db_signals.get(discovery.canonical_id, []):
        evidence.append(sig)

    # Decision rules (fail-closed toward inactive only with explicit absence)
    if invalid_cnpj:
        status = ActivityStatus.INACTIVE.value
        evidence.append("invalid_or_placeholder_cnpj")
    else:
        strong = [
            e
            for e in evidence
            if e.startswith(("db:", "registry_evidence_fresh:", "registry_access_status:"))
        ]
        if strong:
            status = ActivityStatus.ACTIVE.value
        elif any(e.startswith("platform:pncp") for e in evidence) and discovery.access_status not in (
            "source_not_identified",
            "blocked",
        ):
            # PNCP mapped with prior collection pipeline signal elsewhere
            if discovery.access_status in ("mapped", "accessible", "collected", "verified", "operational"):
                # Conservative: mapped+pncp alone is not enough for ACTIVE without
                # time-bounded evidence — mark pending unless collected+
                if discovery.access_status in ("collected", "verified", "operational"):
                    status = ActivityStatus.ACTIVE.value
                else:
                    status = ActivityStatus.UNKNOWN_PENDING_EVIDENCE.value
            else:
                status = ActivityStatus.UNKNOWN_PENDING_EVIDENCE.value
        else:
            status = ActivityStatus.INACTIVE.value
            evidence.append("no_independent_activity_signal_in_lookback")

    discovery.activity_status = status
    discovery.activity_evidence = sorted(set(evidence))
    return discovery


def load_db_activity_signals(dsn: str | None = None) -> dict[str, list[str]]:
    """Optional independent signals from local/remote Postgres."""
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        return {}
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return {}

    signals: dict[str, list[str]] = {}
    cutoff = (_now() - timedelta(days=int(ACTIVITY_LOOKBACK_MONTHS * 30.44))).date().isoformat()
    try:
        conn = psycopg2.connect(dsn)
    except Exception:
        return {}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Opportunities / open tenders if table exists
            for sql, label in (
                (
                    """
                    SELECT DISTINCT canonical_entity_id AS cid
                    FROM coverage_evidence
                    WHERE capability IN ('open_tenders','historical_contracts')
                      AND state IN ('success_with_data','success_zero')
                      AND checked_at >= %s
                      AND canonical_entity_id IS NOT NULL
                    """,
                    "db:coverage_evidence",
                ),
                (
                    """
                    SELECT DISTINCT entity_id AS cid
                    FROM entity_coverage
                    WHERE last_seen_at >= %s AND entity_id IS NOT NULL
                    """,
                    "db:entity_coverage",
                ),
            ):
                try:
                    cur.execute(sql, (cutoff,))
                    for row in cur.fetchall() or []:
                        cid = row.get("cid")
                        if cid:
                            signals.setdefault(str(cid), []).append(label)
                except Exception:
                    conn.rollback()
                    continue
    finally:
        conn.close()
    return signals


def classify_all_activity(
    discoveries: list[EntityDocumentDiscovery] | None = None,
    *,
    dsn: str | None = None,
    persist: bool = True,
    output_dir: Path | str | None = None,
) -> tuple[list[EntityDocumentDiscovery], dict[str, Any]]:
    discoveries = list(discoveries or load_discovery())
    db_signals = load_db_activity_signals(dsn)
    # Map db keys that may be cnpj-based — also index by cnpj root
    by_cnpj: dict[str, list[str]] = {}
    for cid, sigs in db_signals.items():
        root = cid.split(":")[0] if ":" in cid else cid
        by_cnpj.setdefault(root, []).extend(sigs)

    for d in discoveries:
        merged = dict(db_signals)
        root = (d.cnpj or "")[:8]
        extra = by_cnpj.get(root, [])
        if extra:
            merged[d.canonical_id] = list(merged.get(d.canonical_id, [])) + extra
        classify_activity_for_entity(d, db_signals=merged)

    report = build_activity_report(discoveries)
    if persist:
        _, meta = ensure_roots()
        out = Path(output_dir or meta)
        write_json(out / "entity-activity-classification.json", report)
        (out / "entity-activity-classification.md").write_text(
            render_activity_markdown(report), encoding="utf-8"
        )
        # refresh discovery jsonl with activity
        with (out / "entity-document-discovery.jsonl").open("w", encoding="utf-8") as fh:
            for d in sorted(discoveries, key=lambda x: x.canonical_id):
                fh.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
        report["artifacts"] = {
            "json": str(out / "entity-activity-classification.json"),
            "md": str(out / "entity-activity-classification.md"),
        }
    return discoveries, report


def build_activity_report(discoveries: list[EntityDocumentDiscovery]) -> dict[str, Any]:
    counts = {s.value: 0 for s in ActivityStatus}
    active_ids: list[str] = []
    inactive_ids: list[str] = []
    pending_ids: list[str] = []
    for d in discoveries:
        st = d.activity_status
        counts[st] = counts.get(st, 0) + 1
        if st == ActivityStatus.ACTIVE.value:
            active_ids.append(d.canonical_id)
        elif st == ActivityStatus.INACTIVE.value:
            inactive_ids.append(d.canonical_id)
        else:
            pending_ids.append(d.canonical_id)
    return {
        "criteria_version": ACTIVITY_CRITERIA_VERSION,
        "lookback_months": ACTIVITY_LOOKBACK_MONTHS,
        "generated_at": _now().isoformat(),
        "total_entities": len(discoveries),
        "counts": counts,
        "active_count": len(active_ids),
        "inactive_count": len(inactive_ids),
        "pending_count": len(pending_ids),
        "active_ids": sorted(active_ids),
        "inactive_ids": sorted(inactive_ids)[:100],
        "pending_ids": sorted(pending_ids)[:100],
        "note": (
            "Active denominator for operational document coverage uses active_ids only. "
            "Inactive entities leave the operational denominator after audited classification. "
            "Pending entities remain documented and do not inflate operational coverage."
        ),
        "entities": [
            {
                "canonical_id": d.canonical_id,
                "activity_status": d.activity_status,
                "activity_evidence": d.activity_evidence,
                "portal_family": d.portal_family,
            }
            for d in sorted(discoveries, key=lambda x: x.canonical_id)
        ],
    }


def render_activity_markdown(report: dict[str, Any]) -> str:
    return (
        "# Entity activity classification\n\n"
        f"- Criteria: `{report['criteria_version']}`\n"
        f"- Lookback: {report['lookback_months']} months\n"
        f"- Total: {report['total_entities']}\n"
        f"- Active: **{report['active_count']}**\n"
        f"- Inactive: **{report['inactive_count']}**\n"
        f"- Pending evidence: **{report['pending_count']}**\n"
        f"- Generated: {report['generated_at']}\n\n"
        f"{report['note']}\n"
    )


def active_entity_ids(discoveries: list[EntityDocumentDiscovery] | None = None) -> list[str]:
    discoveries = discoveries or load_discovery()
    return sorted(d.canonical_id for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value)
