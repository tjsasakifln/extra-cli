"""Orchestration: collect documents for entities (live)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.process_documents.adapters.base import get_adapter
from scripts.process_documents.discovery import load_discovery
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import ActivityStatus, DocumentRunStatus
from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots, write_json


def collect_entity(
    entity: EntityDocumentDiscovery | str,
    *,
    since: str | None = None,
    until: str | None = None,
    max_processes: int = 10,
    download: bool = True,
    prefer_pncp: bool = True,
) -> Any:
    if isinstance(entity, str):
        entities = {d.canonical_id: d for d in load_discovery()}
        if entity not in entities:
            raise KeyError(f"unknown entity: {entity}")
        entity = entities[entity]
    plats = {p.lower() for p in entity.platforms}
    # Prefer CIGA when present (often reachable when PNCP is degraded); else PNCP.
    if "ciga_ckan" in plats or "ciga_dom" in plats or "dom_sc" in plats:
        family = "ciga_ckan"
    elif prefer_pncp and "pncp" in plats:
        family = "pncp"
    else:
        family = entity.portal_family
    adapter = get_adapter(family)
    return adapter.collect(
        entity,
        since=since,
        until=until,
        max_processes=max_processes,
        download=download,
    )


def collect_many(
    *,
    only_active: bool = True,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    max_processes: int = 8,
    download: bool = True,
    canonical_ids: list[str] | None = None,
) -> dict[str, Any]:
    discoveries = load_discovery()
    if canonical_ids:
        want = set(canonical_ids)
        targets = [d for d in discoveries if d.canonical_id in want]
    elif only_active:
        targets = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
        # If activity not classified yet, fall back to collected/verified/operational
        if not targets:
            targets = [
                d
                for d in discoveries
                if d.access_status in ("collected", "verified", "operational")
            ]
    else:
        targets = list(discoveries)
    # Priority: pncp family first, higher mapping confidence
    targets.sort(key=lambda d: (0 if d.portal_family == "pncp" else 1, -d.mapping_confidence, d.canonical_id))
    if limit is not None:
        targets = targets[:limit]

    results = []
    for d in targets:
        try:
            run = collect_entity(d, since=since, until=until, max_processes=max_processes, download=download)
            results.append(run.to_dict() if hasattr(run, "to_dict") else run)
        except Exception as exc:  # noqa: BLE001 — per-entity isolation
            results.append(
                {
                    "canonical_entity_id": d.canonical_id,
                    "status": DocumentRunStatus.UNKNOWN.value,
                    "errors": [str(exc)],
                }
            )
    summary = {
        "count": len(results),
        "by_status": {},
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
    }
    for r in results:
        st = r.get("status") if isinstance(r, dict) else None
        if st:
            summary["by_status"][st] = summary["by_status"].get(st, 0) + 1
    _, meta = ensure_roots()
    write_json(meta / "collect-batch-latest.json", summary)
    return summary


def backfill(
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    download: bool = True,
) -> dict[str, Any]:
    until = until or datetime.now(UTC).date().isoformat()
    if not since:
        since = (datetime.now(UTC).date() - timedelta(days=365 * 3)).isoformat()
    # Checkpoint file
    _, meta = ensure_roots()
    ck_path = meta / "checkpoints" / "backfill.json"
    ck_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {"completed_entities": [], "since": since, "until": until}
    if ck_path.is_file():
        checkpoint = json.loads(ck_path.read_text(encoding="utf-8"))
    done = set(checkpoint.get("completed_entities") or [])
    discoveries = load_discovery()
    targets = [
        d
        for d in discoveries
        if d.activity_status == ActivityStatus.ACTIVE.value and d.canonical_id not in done
    ]
    if not targets:
        targets = [d for d in discoveries if d.canonical_id not in done][: (limit or 50)]
    if limit:
        targets = targets[:limit]
    summary = collect_many(
        only_active=False,
        limit=None,
        since=since,
        until=until,
        download=download,
        canonical_ids=[d.canonical_id for d in targets],
    )
    for r in summary.get("results") or []:
        cid = r.get("canonical_entity_id")
        st = r.get("status")
        if cid and st in (
            DocumentRunStatus.SUCCESS_NONZERO.value,
            DocumentRunStatus.SUCCESS_ZERO.value,
        ):
            done.add(cid)
    checkpoint["completed_entities"] = sorted(done)
    checkpoint["updated_at"] = datetime.now(UTC).isoformat()
    ck_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["checkpoint_uri"] = str(ck_path)
    write_json(meta / "document-backfill-manifest.json", summary)
    return summary


def incremental(*, download: bool = True, limit: int | None = 50) -> dict[str, Any]:
    since = (datetime.now(UTC).date() - timedelta(days=14)).isoformat()
    until = datetime.now(UTC).date().isoformat()
    summary = collect_many(only_active=True, limit=limit, since=since, until=until, download=download)
    _, meta = ensure_roots()
    write_json(meta / "document-incremental-manifest.json", summary)
    return summary
