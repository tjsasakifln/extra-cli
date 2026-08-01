"""Orchestration: collect documents for entities (live).

Daily incremental path uses:
  1. Entity queue by **last valid success lag** (rotation), not sticky top-N.
  2. Multi-source collection per entity (all applicable adapters), not a single preferred family.
  3. Drain until lag cleared or capacity insufficient; SLA alerts for >24h without success.
  4. Process cards merging multi-source documents with version/change detection.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.process_documents.adapters.base import get_adapter
from scripts.process_documents.discovery import load_discovery
from scripts.process_documents.entity_queue import (
    SLA_HOURS,
    apply_attempt_result,
    apply_multi_source_attempt,
    build_sla_alerts,
    drain_decision,
    ensure_entries,
    load_entity_queue,
    overdue_entities,
    queue_summary,
    save_entity_queue,
    select_batch_by_source_lag,
    select_batch_by_success_lag,
)
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.process_card import build_cards_from_collect_summary
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
    """Legacy-compatible wrapper: treat last_visits as last_success timestamps.

    Prefer ``select_batch_by_success_lag`` with a full entity queue for production.
    """
    from scripts.process_documents.entity_queue import EntityQueueEntry

    queue = {
        cid: EntityQueueEntry(canonical_id=cid, last_success_at=ts, last_attempt_at=ts)
        for cid, ts in last_visits.items()
        if ts
    }
    return select_batch_by_success_lag(targets, queue, limit=limit, now=now)


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
    """Backward-compatible view: last_attempt (or last_success) timestamps from queue."""
    queue = load_entity_queue(meta_root=meta_root)
    out: dict[str, str] = {}
    for cid, entry in queue.items():
        ts = entry.last_success_at or entry.last_attempt_at
        if ts:
            out[cid] = ts
    # Also surface legacy file if queue empty
    if out:
        return out
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
    results_by_entity: Mapping[str, Mapping[str, Any]] | None = None,
    meta_root: Path | None = None,
) -> Path:
    """Persist full queue state (attempt/success/failures) for attempted entities."""
    queue = load_entity_queue(meta_root=meta_root)
    ensure_entries(queue, entity_ids)
    stamp = _parse_iso(visited_at) or datetime.now(UTC)
    for cid in entity_ids:
        entry = queue[cid]
        st = (statuses or {}).get(cid)
        srcs = (sources_by_entity or {}).get(cid)
        result = (results_by_entity or {}).get(cid)
        err = None
        if result and isinstance(result, dict):
            errs = result.get("errors") or []
            if errs:
                err = str(errs[0])
            src_results = result.get("source_results")
            if isinstance(src_results, dict) and src_results:
                # Per source_id state — success of one source never clears another
                apply_multi_source_attempt(
                    entry,
                    source_results=src_results,
                    attempted_at=stamp,
                    aggregate_status=st,
                )
            else:
                apply_attempt_result(
                    entry,
                    status=st,
                    sources=srcs,
                    error=err,
                    attempted_at=stamp,
                    result=result,
                )
        else:
            apply_attempt_result(
                entry,
                status=st,
                sources=srcs,
                error=err,
                attempted_at=stamp,
                result=result,
            )
        queue[cid] = entry
    path = save_entity_queue(queue, meta_root=meta_root, updated_at=stamp.isoformat())
    # Keep legacy visits file in sync for older readers
    _, meta = ensure_roots(meta_root=meta_root)
    legacy = {
        "updated_at": stamp.isoformat(),
        "entities": {
            cid: {
                "last_visited_at": queue[cid].last_attempt_at,
                "last_status": queue[cid].last_status,
                "sources": queue[cid].sources,
                "last_success_at": queue[cid].last_success_at,
                "next_run_at": queue[cid].next_run_at,
                "attempt_count": queue[cid].attempt_count,
                "consecutive_failures": queue[cid].consecutive_failures,
            }
            for cid in entity_ids
            if cid in queue
        },
    }
    # merge with previous legacy entities
    leg_path = meta / VISITS_CHECKPOINT_REL
    if leg_path.is_file():
        try:
            prev = json.loads(leg_path.read_text(encoding="utf-8"))
            if isinstance(prev.get("entities"), dict):
                merged = dict(prev["entities"])
                merged.update(legacy["entities"])
                legacy["entities"] = merged
        except (OSError, json.JSONDecodeError):
            pass
    write_json(leg_path, legacy)
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
            "max_processes_budget": rd.get("max_processes_budget"),
            "scope_complete": rd.get("scope_complete"),
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

    # Aggregate status (fail-closed, multi-source honest):
    # - SUCCESS_NONZERO only if ALL consulted sources are SUCCESS_NONZERO
    # - SUCCESS_ZERO only if ALL consulted are success and every SUCCESS_ZERO has
    #   scope_complete is not False
    # - mixed success+failure → PARTIAL (never mask failed source)
    # - NOT_QUERIED_BUDGET is not a consulted success
    skip = {
        DocumentRunStatus.NOT_QUERIED_BUDGET.value,
        DocumentRunStatus.NOT_QUERIED.value,
        "NOT_QUERIED_BUDGET",
        "NOT_QUERIED",
    }
    consulted = [s for s in statuses if s and s not in skip]
    not_queried = [s for s in statuses if s in skip]
    if not consulted and not_queried:
        agg_status = DocumentRunStatus.NOT_QUERIED_BUDGET.value
    elif consulted and all(s == DocumentRunStatus.SUCCESS_NONZERO.value for s in consulted):
        agg_status = DocumentRunStatus.SUCCESS_NONZERO.value
    elif consulted and all(s in _SUCCESS_STATUSES for s in consulted):
        # All success-class; check SUCCESS_ZERO scope completeness
        zero_incomplete = False
        for src, result in zip(sources, source_results, strict=False):
            rd = _run_to_dict(result)
            st = _status_value(rd)
            if st == DocumentRunStatus.SUCCESS_ZERO.value and rd.get("scope_complete") is False:
                zero_incomplete = True
        if zero_incomplete:
            agg_status = DocumentRunStatus.PARTIAL.value
        elif all(s == DocumentRunStatus.SUCCESS_ZERO.value for s in consulted):
            agg_status = DocumentRunStatus.SUCCESS_ZERO.value
        else:
            # mix of NONZERO and ZERO among all-success
            agg_status = DocumentRunStatus.SUCCESS_NONZERO.value
    elif consulted and any(s in _SUCCESS_STATUSES for s in consulted) and any(
        s not in _SUCCESS_STATUSES for s in consulted
    ):
        agg_status = DocumentRunStatus.PARTIAL.value
    elif any(s and s not in _SUCCESS_STATUSES and s not in skip for s in statuses):
        agg_status = next(
            (s for s in statuses if s and s not in _SUCCESS_STATUSES and s not in skip),
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
        "sources_consulted": [s for s, st in zip(sources, statuses, strict=False) if st not in skip],
        "sources_not_queried_budget": [
            s for s, st in zip(sources, statuses, strict=False) if st in skip
        ],
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
    from scripts.process_documents.source_budget import allocate_source_budgets

    allocation = allocate_source_budgets(sources, max_processes=max_processes)
    budgets = allocation["budgets"]
    source_results: list[dict[str, Any]] = []
    for family in sources:
        budget = int(budgets.get(family, 0))
        if budget <= 0:
            source_results.append(
                {
                    "canonical_entity_id": entity.canonical_id,
                    "source_id": family,
                    "portal_family": family,
                    "status": DocumentRunStatus.NOT_QUERIED_BUDGET.value,
                    "errors": [],
                    "documents": [],
                    "documents_downloaded": 0,
                    "documents_unchanged": 0,
                    "documents_failed": 0,
                    "processes_seen": 0,
                    "max_processes_budget": 0,
                    "not_queried_reason": "entity_max_processes_exhausted",
                }
            )
            continue
        try:
            adapter = get_adapter(family)
            run = adapter.collect(
                entity,
                since=since,
                until=until,
                max_processes=budget,
                download=download,
            )
            rd = _run_to_dict(run)
            rd.setdefault("source_id", family)
            rd.setdefault("portal_family", family)
            rd["max_processes_budget"] = budget
            source_results.append(rd)
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
                    "max_processes_budget": budget,
                }
            )
    merged = aggregate_multi_source_result(entity.canonical_id, sources, source_results)
    merged["budget_allocation"] = allocation
    # Fail-closed invariant
    if int(allocation["sum_budgets"]) > int(allocation["max_processes"]):
        raise RuntimeError(
            f"budget overflow: sum={allocation['sum_budgets']} > max={allocation['max_processes']}"
        )
    return merged


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
    overdue_only: bool = False,
    build_process_cards: bool = True,
) -> dict[str, Any]:
    """Collect for a batch of entities.

    Defaults match the daily path: multi-source + success-lag queue rotation.
    ``rotation=False`` restores legacy static sort (pncp/confidence/id).
    """
    discoveries = load_discovery()
    targets = _eligible_targets(discoveries, only_active=only_active, canonical_ids=canonical_ids)

    queue = load_entity_queue(meta_root=meta_root)
    ensure_entries(queue, [d.canonical_id for d in targets])

    # Optional override from last_visits map (tests)
    if last_visits is not None:
        from scripts.process_documents.entity_queue import EntityQueueEntry

        for cid, ts in last_visits.items():
            if cid not in queue:
                queue[cid] = EntityQueueEntry(canonical_id=cid)
            if ts:
                queue[cid].last_success_at = ts
                queue[cid].last_attempt_at = ts

    pool = targets
    if overdue_only:
        pool = overdue_entities(targets, queue)
    if rotation:
        # Prefer entity×source lag when source state exists; else entity success lag
        if any((queue.get(d.canonical_id) and queue[d.canonical_id].sources_state) for d in pool):
            selected = select_batch_by_source_lag(pool, queue, limit=limit)
            selection_policy = "entity_source_lag_rotation"
        else:
            selected = select_batch_by_success_lag(pool, queue, limit=limit)
            selection_policy = "success_lag_rotation"
    else:
        selected = select_batch_static_legacy(pool, limit=limit)
        selection_policy = "static_legacy"

    results: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    statuses: dict[str, str] = {}
    sources_by_entity: dict[str, list[str]] = {}
    results_by_entity: dict[str, dict[str, Any]] = {}

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
            results_by_entity[d.canonical_id] = rd
            st = _status_value(rd)
            if st:
                statuses[d.canonical_id] = st
            sources_by_entity[d.canonical_id] = list(
                rd.get("sources_attempted") or rd.get("sources_consulted") or [rd.get("portal_family") or ""]
            )
        except Exception as exc:  # noqa: BLE001 — per-entity isolation
            rd = {
                "canonical_entity_id": d.canonical_id,
                "status": DocumentRunStatus.UNKNOWN.value,
                "errors": [str(exc)],
                "sources_attempted": [],
            }
            results.append(rd)
            results_by_entity[d.canonical_id] = rd
            statuses[d.canonical_id] = DocumentRunStatus.UNKNOWN.value

    if persist_visits and selected_ids and rotation:
        record_entity_visits(
            selected_ids,
            statuses=statuses,
            sources_by_entity=sources_by_entity,
            results_by_entity=results_by_entity,
            meta_root=meta_root,
        )

    # Refresh queue after persist for accurate lag metrics
    queue = load_entity_queue(meta_root=meta_root)
    qsum = queue_summary(targets, queue)
    sla_alerts = build_sla_alerts(targets, queue)

    summary: dict[str, Any] = {
        "count": len(results),
        "by_status": {},
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
        "selection_policy": selection_policy,
        "multi_source": multi_source,
        "selected_canonical_ids": selected_ids,
        "eligible_count": len(targets),
        "overdue_count": qsum.get("overdue_count"),
        "lag_cleared": qsum.get("lag_cleared"),
        "sla_hours": SLA_HOURS,
        "sla_alerts": sla_alerts[:50],
        "sla_alert_count": len(sla_alerts),
        "limit": limit,
        "queue_summary": qsum,
    }
    for r in results:
        st = r.get("status") if isinstance(r, dict) else None
        if st:
            summary["by_status"][st] = summary["by_status"].get(st, 0) + 1

    if build_process_cards and results:
        try:
            summary["process_cards"] = build_cards_from_collect_summary(
                summary, meta_root=meta_root, persist=True
            )
        except Exception as exc:  # noqa: BLE001 — cards must not fail collect
            summary["process_cards_error"] = str(exc)

    _, meta = ensure_roots(meta_root=meta_root)
    # rotate previous batch for growth signals
    latest = meta / "collect-batch-latest.json"
    if latest.is_file():
        try:
            write_json(meta / "collect-batch-previous.json", json.loads(latest.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    write_json(latest, summary)
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
    drain: bool = True,
    max_batches: int | None = None,
    max_entities: int | None = None,
    max_wall_seconds: float | None = None,
    meta_root: Path | None = None,
    build_daily_report: bool = True,
) -> dict[str, Any]:
    """Daily incremental refresh: success-lag queue + multi-source.

    When ``drain=True`` (default), continues selecting overdue entities in batches
    until lag is cleared **or** capacity is insufficient (batches/entities/wall).
    """
    since = (datetime.now(UTC).date() - timedelta(days=14)).isoformat()
    until = datetime.now(UTC).date().isoformat()
    batch_limit = limit if limit is not None else 50

    if not drain:
        summary = collect_many(
            only_active=True,
            limit=batch_limit,
            since=since,
            until=until,
            download=download,
            multi_source=multi_source,
            rotation=rotation,
            persist_visits=True,
            meta_root=meta_root,
            overdue_only=False,
        )
        summary["drain_stop_reason"] = "drain_disabled"
        summary["batches"] = 1
        _, meta = ensure_roots(meta_root=meta_root)
        write_json(meta / "document-incremental-manifest.json", summary)
        if build_daily_report:
            _attach_daily_report(summary, meta_root=meta_root)
        return summary

    # Drain loop
    t0 = time.monotonic()
    batches = 0
    entities_done = 0
    all_results: list[dict[str, Any]] = []
    all_ids: list[str] = []
    by_status: dict[str, int] = {}
    stop_reason = "continue"
    last_summary: dict[str, Any] = {}

    # Default capacity: allow enough batches to cover universe at batch_limit,
    # but cap wall time conservatively for oneshot services (5.5h < 6h Timeout).
    if max_batches is None:
        max_batches = 50
    if max_wall_seconds is None:
        max_wall_seconds = 5.5 * 3600

    while True:
        last_summary = collect_many(
            only_active=True,
            limit=batch_limit,
            since=since,
            until=until,
            download=download,
            multi_source=multi_source,
            rotation=rotation,
            persist_visits=True,
            meta_root=meta_root,
            overdue_only=True,
        )
        batches += 1
        batch_ids = list(last_summary.get("selected_canonical_ids") or [])
        entities_done += len(batch_ids)
        all_ids.extend(batch_ids)
        for r in last_summary.get("results") or []:
            if isinstance(r, dict):
                all_results.append(r)
                st = r.get("status")
                if st:
                    by_status[st] = by_status.get(st, 0) + 1

        overdue_remaining = int(last_summary.get("overdue_count") or 0)
        # If a batch returned empty while overdue remain, stop (stuck)
        if not batch_ids and overdue_remaining > 0:
            stop_reason = "capacity_insufficient_empty_batch"
            break
        if not batch_ids and overdue_remaining == 0:
            stop_reason = "lag_cleared"
            break

        wall = time.monotonic() - t0
        stop, reason = drain_decision(
            overdue_remaining=overdue_remaining,
            batches_done=batches,
            entities_done=entities_done,
            max_batches=max_batches,
            max_entities=max_entities,
            wall_seconds=wall,
            max_wall_seconds=max_wall_seconds,
        )
        stop_reason = reason
        if stop:
            break

    process_cards: dict[str, Any] | None = None
    try:
        process_cards = build_cards_from_collect_summary(
            {"results": all_results},
            meta_root=meta_root,
            persist=True,
        )
    except Exception as exc:  # noqa: BLE001
        process_cards = {"error": str(exc)}

    summary: dict[str, Any] = {
        "count": len(all_results),
        "by_status": by_status,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": all_results,
        "selection_policy": last_summary.get("selection_policy") or "success_lag_rotation",
        "multi_source": multi_source,
        "selected_canonical_ids": all_ids,
        "eligible_count": last_summary.get("eligible_count"),
        "overdue_count": last_summary.get("overdue_count"),
        "lag_cleared": bool(last_summary.get("lag_cleared")),
        "sla_hours": SLA_HOURS,
        "sla_alerts": last_summary.get("sla_alerts") or [],
        "sla_alert_count": last_summary.get("sla_alert_count") or 0,
        "limit": batch_limit,
        "batches": batches,
        "drain": True,
        "drain_stop_reason": stop_reason,
        "capacity_insufficient": (
            stop_reason.startswith("capacity_insufficient")
            or stop_reason == "PARTIAL_CAPACITY_EXHAUSTED"
            or "CAPACITY_EXHAUSTED" in stop_reason
        ),
        "operational_status": (
            "PARTIAL_CAPACITY_EXHAUSTED"
            if (
                stop_reason.startswith("capacity_insufficient")
                or stop_reason == "PARTIAL_CAPACITY_EXHAUSTED"
            )
            else stop_reason
        ),
        "queue_summary": last_summary.get("queue_summary"),
        "process_cards": process_cards,
        "wall_seconds": round(time.monotonic() - t0, 3),
    }
    _, meta = ensure_roots(meta_root=meta_root)
    write_json(meta / "document-incremental-manifest.json", summary)
    if build_daily_report:
        _attach_daily_report(summary, meta_root=meta_root)
    return summary


def _attach_daily_report(summary: dict[str, Any], *, meta_root: Path | None = None) -> None:
    try:
        from scripts.process_documents.daily_ops_report import build_daily_ops_report
        from scripts.process_documents.discovery import load_discovery as _ld

        discoveries = _ld()
        only_active = [
            d
            for d in discoveries
            if d.activity_status == ActivityStatus.ACTIVE.value
        ]
        if not only_active:
            only_active = list(discoveries)
        report = build_daily_ops_report(
            discoveries=only_active,
            collect_summary=summary,
            meta_root=meta_root,
            persist=True,
        )
        summary["daily_ops_report_day"] = report.get("day")
    except Exception as exc:  # noqa: BLE001
        summary["daily_ops_report_error"] = str(exc)

