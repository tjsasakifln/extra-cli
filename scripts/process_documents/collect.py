"""Orchestration: collect documents for entities (live).

Daily incremental path uses:
  1. Batch selection by staleness / never-visited (rotation), not static sort.
  2. Multi-source collection per entity (all applicable adapters), not a single preferred family.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.process_documents.adapters.base import get_adapter
from scripts.process_documents.discovery import load_discovery
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import ActivityStatus, DocumentRunStatus
from scripts.process_documents.storage import ensure_roots, write_json

# Platforms that collapse to the same adapter key (one live call per key).
_PLATFORM_TO_ADAPTER_KEY: dict[str, str] = {
    "pncp": "pncp",
    "pncp_contracts": "pncp",
    "ciga_ckan": "ciga_ckan",
    "ciga_dom": "ciga_ckan",
    "dom_sc": "ciga_ckan",
    "sc_compras": "sc_compras",
    "compras_gov": "compras_gov",
    "doe_sc": "doe_sc",
    "pcp": "pcp",
    "transparencia": "transparencia",
    "tce_sc": "tce_sc",
    "portal_institucional": "portal_institucional",
    "generic_public_html": "generic_public_html",
    "manual_only": "manual_only",
}

# Preference only orders attempts within multi-source — never excludes sources.
_SOURCE_PREFERENCE: tuple[str, ...] = (
    "ciga_ckan",
    "pncp",
    "sc_compras",
    "compras_gov",
    "pcp",
    "doe_sc",
    "transparencia",
    "tce_sc",
    "portal_institucional",
    "generic_public_html",
)

_PREF_RANK = {name: idx for idx, name in enumerate(_SOURCE_PREFERENCE)}

VISITS_CHECKPOINT_REL = Path("checkpoints") / "incremental_visits.json"

_SUCCESS_STATUSES = frozenset(
    {
        DocumentRunStatus.SUCCESS_NONZERO.value,
        DocumentRunStatus.SUCCESS_ZERO.value,
    }
)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    text = str(ts).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def select_batch_static_legacy(
    targets: Sequence[EntityDocumentDiscovery],
    *,
    limit: int | None,
) -> list[EntityDocumentDiscovery]:
    """Legacy fixed ordering: pncp first, then confidence, then canonical_id.

    Kept pure and exported so tests can prove the old prefix was sticky.
    """
    ordered = list(targets)
    ordered.sort(
        key=lambda d: (
            0 if d.portal_family == "pncp" else 1,
            -float(d.mapping_confidence or 0.0),
            d.canonical_id,
        )
    )
    if limit is not None:
        return ordered[:limit]
    return ordered


def select_batch_by_staleness(
    targets: Sequence[EntityDocumentDiscovery],
    *,
    last_visits: Mapping[str, str | None],
    limit: int | None,
    now: datetime | None = None,
) -> list[EntityDocumentDiscovery]:
    """Select up to ``limit`` entities prioritizing never-visited, then oldest visit.

    Pure function: no I/O. Tie-break by canonical_id for determinism.
    Progressive coverage: after visits are recorded, subsequent runs rotate the batch.
    """
    _ = now  # reserved for clock injection / age metrics; sort uses raw timestamps
    ordered = list(targets)

    def sort_key(d: EntityDocumentDiscovery) -> tuple[int, datetime, str]:
        visited_at = _parse_iso(last_visits.get(d.canonical_id))
        if visited_at is None:
            # Never visited → front of the queue
            return (0, datetime.min.replace(tzinfo=UTC), d.canonical_id)
        return (1, visited_at, d.canonical_id)

    ordered.sort(key=sort_key)
    if limit is not None:
        return ordered[:limit]
    return ordered


def resolve_applicable_sources(
    entity: EntityDocumentDiscovery,
    *,
    prefer_pncp: bool = True,
) -> list[str]:
    """Return ordered unique adapter keys for all platforms/families on the entity.

    Preference only reorders; it does not drop a source that has an adapter mapping.
    ``manual_only`` is omitted (no live adapter).
    """
    raw: list[str] = []
    for p in entity.platforms or []:
        key = _PLATFORM_TO_ADAPTER_KEY.get(str(p).lower())
        if key and key != "manual_only":
            raw.append(key)
    fam = (entity.portal_family or "").lower()
    if fam:
        key = _PLATFORM_TO_ADAPTER_KEY.get(fam, fam)
        if key and key != "manual_only":
            raw.append(key)
    # Dedupe preserving first-seen, then preference-sort
    seen: set[str] = set()
    unique: list[str] = []
    for k in raw:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    if not unique:
        unique = ["pncp" if prefer_pncp else (fam or "generic_public_html")]

    def rank(name: str) -> tuple[int, str]:
        # Prefer CIGA-like before PNCP when both present (reachability), else preference table
        if name in _PREF_RANK:
            return (_PREF_RANK[name], name)
        return (len(_PREF_RANK) + 1, name)

    unique.sort(key=rank)
    # prefer_pncp only tweaks order when both pncp and non-ciga exist without ciga
    if prefer_pncp and "pncp" in unique and "ciga_ckan" not in unique:
        unique = ["pncp"] + [u for u in unique if u != "pncp"]
    return unique


def preferred_single_source(
    entity: EntityDocumentDiscovery,
    *,
    prefer_pncp: bool = True,
) -> str:
    """Legacy single-family choice (for opt-out / comparison). Preference excludes others."""
    plats = {p.lower() for p in (entity.platforms or [])}
    if "ciga_ckan" in plats or "ciga_dom" in plats or "dom_sc" in plats:
        return "ciga_ckan"
    if prefer_pncp and "pncp" in plats:
        return "pncp"
    return entity.portal_family or "pncp"


def load_last_visits(meta_root: Path | None = None) -> dict[str, str]:
    """Load last-visit ISO timestamps keyed by canonical_id from meta checkpoint."""
    _, meta = ensure_roots(meta_root=meta_root)
    path = meta / VISITS_CHECKPOINT_REL
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, dict):
        return {}
    out: dict[str, str] = {}
    for cid, payload in entities.items():
        if isinstance(payload, str):
            out[str(cid)] = payload
        elif isinstance(payload, dict) and payload.get("last_visited_at"):
            out[str(cid)] = str(payload["last_visited_at"])
    return out


def record_entity_visits(
    entity_ids: Sequence[str],
    *,
    visited_at: str | None = None,
    statuses: Mapping[str, str] | None = None,
    sources_by_entity: Mapping[str, Sequence[str]] | None = None,
    meta_root: Path | None = None,
) -> Path:
    """Persist last-visit timestamps for entities that were attempted in a batch."""
    _, meta = ensure_roots(meta_root=meta_root)
    path = meta / VISITS_CHECKPOINT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {"entities": {}}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {"entities": {}}
    if not isinstance(existing.get("entities"), dict):
        existing["entities"] = {}
    stamp = visited_at or datetime.now(UTC).isoformat()
    for cid in entity_ids:
        prev = existing["entities"].get(cid) if isinstance(existing["entities"].get(cid), dict) else {}
        entry = {
            "last_visited_at": stamp,
            "last_status": (statuses or {}).get(cid) or (prev or {}).get("last_status"),
            "sources": list((sources_by_entity or {}).get(cid) or (prev or {}).get("sources") or []),
        }
        existing["entities"][cid] = entry
    existing["updated_at"] = stamp
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _status_value(run: Any) -> str | None:
    if isinstance(run, dict):
        st = run.get("status")
        return st.value if isinstance(st, DocumentRunStatus) else (str(st) if st is not None else None)
    st = getattr(run, "status", None)
    if isinstance(st, DocumentRunStatus):
        return st.value
    return str(st) if st is not None else None


def _run_to_dict(run: Any) -> dict[str, Any]:
    if isinstance(run, dict):
        return run
    if hasattr(run, "to_dict"):
        return run.to_dict()
    return {"status": _status_value(run), "raw": str(run)}


def aggregate_multi_source_result(
    canonical_entity_id: str,
    sources: Sequence[str],
    source_results: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Merge per-source run dicts into one entity-level result for the daily path."""
    statuses = [_status_value(r) for r in source_results]
    by_source: dict[str, dict[str, Any]] = {}
    documents: list[Any] = []
    errors: list[str] = []
    blockers: list[str] = []
    docs_dl = 0
    docs_unchanged = 0
    docs_failed = 0
    processes_seen = 0

    for src, result in zip(sources, source_results, strict=False):
        rd = _run_to_dict(result)
        by_source[src] = {
            "status": _status_value(rd),
            "source_id": rd.get("source_id") or src,
            "portal_family": rd.get("portal_family") or src,
            "documents_downloaded": rd.get("documents_downloaded", 0),
            "documents_unchanged": rd.get("documents_unchanged", 0),
            "documents_failed": rd.get("documents_failed", 0),
            "processes_seen": rd.get("processes_seen", 0),
            "errors": list(rd.get("errors") or []),
            "blockers": list(rd.get("blockers") or []),
            "run_id": rd.get("run_id"),
        }
        documents.extend(rd.get("documents") or [])
        errors.extend(str(e) for e in (rd.get("errors") or []))
        blockers.extend(str(b) for b in (rd.get("blockers") or []))
        docs_dl += int(rd.get("documents_downloaded") or 0)
        docs_unchanged += int(rd.get("documents_unchanged") or 0)
        docs_failed += int(rd.get("documents_failed") or 0)
        processes_seen += int(rd.get("processes_seen") or 0)

    # Aggregate status: any SUCCESS_NONZERO → NONZERO; else any SUCCESS_ZERO → ZERO;
    # else prefer partial-like failures over unknown.
    if DocumentRunStatus.SUCCESS_NONZERO.value in statuses:
        agg_status = DocumentRunStatus.SUCCESS_NONZERO.value
    elif DocumentRunStatus.SUCCESS_ZERO.value in statuses and any(
        s in _SUCCESS_STATUSES for s in statuses if s
    ):
        # At least one hard success (zero); if others failed, still partial signal
        if all(s in _SUCCESS_STATUSES for s in statuses if s):
            agg_status = DocumentRunStatus.SUCCESS_ZERO.value
        else:
            agg_status = DocumentRunStatus.PARTIAL.value
    elif any(s and s not in _SUCCESS_STATUSES for s in statuses):
        # Prefer first non-success concrete status
        agg_status = next(
            (s for s in statuses if s and s not in _SUCCESS_STATUSES),
            DocumentRunStatus.UNKNOWN.value,
        )
    else:
        agg_status = DocumentRunStatus.UNKNOWN.value

    return {
        "canonical_entity_id": canonical_entity_id,
        "portal_family": "multi_source",
        "source_id": "multi_source",
        "status": agg_status,
        "sources_attempted": list(sources),
        "sources_consulted": list(sources),
        "source_results": by_source,
        "documents": documents,
        "documents_downloaded": docs_dl,
        "documents_unchanged": docs_unchanged,
        "documents_failed": docs_failed,
        "processes_seen": processes_seen,
        "errors": errors,
        "blockers": blockers,
        "multi_source": True,
    }


def collect_entity(
    entity: EntityDocumentDiscovery | str,
    *,
    since: str | None = None,
    until: str | None = None,
    max_processes: int = 10,
    download: bool = True,
    prefer_pncp: bool = True,
    multi_source: bool = True,
) -> Any:
    """Collect documents for one entity.

    Default ``multi_source=True`` consults every applicable adapter family.
    Set ``multi_source=False`` to restore legacy single preferred source.
    """
    if isinstance(entity, str):
        entities = {d.canonical_id: d for d in load_discovery()}
        if entity not in entities:
            raise KeyError(f"unknown entity: {entity}")
        entity = entities[entity]

    if not multi_source:
        family = preferred_single_source(entity, prefer_pncp=prefer_pncp)
        adapter = get_adapter(family)
        return adapter.collect(
            entity,
            since=since,
            until=until,
            max_processes=max_processes,
            download=download,
        )

    sources = resolve_applicable_sources(entity, prefer_pncp=prefer_pncp)
    # Conservative per-source process budget when multiple sources share the entity budget.
    per_source = max(1, int(max_processes)) if len(sources) <= 1 else max(1, int(max_processes))
    source_results: list[dict[str, Any]] = []
    for family in sources:
        try:
            adapter = get_adapter(family)
            run = adapter.collect(
                entity,
                since=since,
                until=until,
                max_processes=per_source,
                download=download,
            )
            source_results.append(_run_to_dict(run))
        except Exception as exc:  # noqa: BLE001 — isolate per source
            source_results.append(
                {
                    "canonical_entity_id": entity.canonical_id,
                    "source_id": family,
                    "portal_family": family,
                    "status": DocumentRunStatus.UNKNOWN.value,
                    "errors": [str(exc)],
                    "documents": [],
                    "documents_downloaded": 0,
                    "documents_unchanged": 0,
                    "documents_failed": 0,
                    "processes_seen": 0,
                }
            )
    return aggregate_multi_source_result(entity.canonical_id, sources, source_results)


def _eligible_targets(
    discoveries: Sequence[EntityDocumentDiscovery],
    *,
    only_active: bool,
    canonical_ids: list[str] | None,
) -> list[EntityDocumentDiscovery]:
    if canonical_ids:
        want = set(canonical_ids)
        return [d for d in discoveries if d.canonical_id in want]
    if only_active:
        targets = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
        if not targets:
            targets = [
                d
                for d in discoveries
                if d.access_status in ("collected", "verified", "operational")
            ]
        return targets
    return list(discoveries)


def collect_many(
    *,
    only_active: bool = True,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    max_processes: int = 8,
    download: bool = True,
    canonical_ids: list[str] | None = None,
    multi_source: bool = True,
    rotation: bool = True,
    last_visits: Mapping[str, str | None] | None = None,
    persist_visits: bool = True,
    meta_root: Path | None = None,
) -> dict[str, Any]:
    """Collect for a batch of entities.

    Defaults match the daily path: multi-source + staleness rotation.
    ``rotation=False`` restores legacy static sort (pncp/confidence/id).
    """
    discoveries = load_discovery()
    targets = _eligible_targets(discoveries, only_active=only_active, canonical_ids=canonical_ids)

    visits: Mapping[str, str | None]
    if last_visits is not None:
        visits = last_visits
    elif rotation:
        visits = load_last_visits(meta_root=meta_root)
    else:
        visits = {}

    if rotation:
        selected = select_batch_by_staleness(targets, last_visits=visits, limit=limit)
        selection_policy = "staleness_rotation"
    else:
        selected = select_batch_static_legacy(targets, limit=limit)
        selection_policy = "static_legacy"

    results: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    statuses: dict[str, str] = {}
    sources_by_entity: dict[str, list[str]] = {}

    for d in selected:
        selected_ids.append(d.canonical_id)
        try:
            run = collect_entity(
                d,
                since=since,
                until=until,
                max_processes=max_processes,
                download=download,
                multi_source=multi_source,
            )
            rd = _run_to_dict(run)
            results.append(rd)
            st = _status_value(rd)
            if st:
                statuses[d.canonical_id] = st
            sources_by_entity[d.canonical_id] = list(
                rd.get("sources_attempted") or rd.get("sources_consulted") or [rd.get("portal_family") or ""]
            )
        except Exception as exc:  # noqa: BLE001 — per-entity isolation
            results.append(
                {
                    "canonical_entity_id": d.canonical_id,
                    "status": DocumentRunStatus.UNKNOWN.value,
                    "errors": [str(exc)],
                    "sources_attempted": [],
                }
            )
            statuses[d.canonical_id] = DocumentRunStatus.UNKNOWN.value

    if persist_visits and selected_ids and rotation:
        record_entity_visits(
            selected_ids,
            statuses=statuses,
            sources_by_entity=sources_by_entity,
            meta_root=meta_root,
        )

    summary: dict[str, Any] = {
        "count": len(results),
        "by_status": {},
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
        "selection_policy": selection_policy,
        "multi_source": multi_source,
        "selected_canonical_ids": selected_ids,
        "eligible_count": len(targets),
        "limit": limit,
    }
    for r in results:
        st = r.get("status") if isinstance(r, dict) else None
        if st:
            summary["by_status"][st] = summary["by_status"].get(st, 0) + 1
    _, meta = ensure_roots(meta_root=meta_root)
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
    checkpoint: dict[str, Any] = {"completed_entities": [], "since": since, "until": until}
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
        # Backfill already tracks completed_entities; keep multi-source default.
        rotation=False,
        persist_visits=False,
    )
    for r in summary.get("results") or []:
        cid = r.get("canonical_entity_id")
        st = r.get("status")
        if cid and st in (
            DocumentRunStatus.SUCCESS_NONZERO.value,
            DocumentRunStatus.SUCCESS_ZERO.value,
            DocumentRunStatus.PARTIAL.value,
        ):
            # multi-source partial still advances backfill so we do not stall forever
            if st in (
                DocumentRunStatus.SUCCESS_NONZERO.value,
                DocumentRunStatus.SUCCESS_ZERO.value,
            ):
                done.add(cid)
            elif st == DocumentRunStatus.PARTIAL.value and any(
                (r.get("source_results") or {}).get(s, {}).get("status") in _SUCCESS_STATUSES
                for s in (r.get("sources_attempted") or [])
            ):
                done.add(cid)
    checkpoint["completed_entities"] = sorted(done)
    checkpoint["updated_at"] = datetime.now(UTC).isoformat()
    ck_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["checkpoint_uri"] = str(ck_path)
    write_json(meta / "document-backfill-manifest.json", summary)
    return summary


def incremental(
    *,
    download: bool = True,
    limit: int | None = 50,
    multi_source: bool = True,
    rotation: bool = True,
) -> dict[str, Any]:
    """Daily incremental refresh: staleness rotation + multi-source by default."""
    since = (datetime.now(UTC).date() - timedelta(days=14)).isoformat()
    until = datetime.now(UTC).date().isoformat()
    summary = collect_many(
        only_active=True,
        limit=limit,
        since=since,
        until=until,
        download=download,
        multi_source=multi_source,
        rotation=rotation,
        persist_visits=True,
    )
    _, meta = ensure_roots()
    write_json(meta / "document-incremental-manifest.json", summary)
    return summary
