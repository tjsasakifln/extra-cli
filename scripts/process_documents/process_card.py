"""Unified process card across multi-source document runs.

One certame may scatter edital, annexes, corrections and session results across
PNCP, origin portal, CIGA, SC Compras and official acts. This module merges
per-source document inventories into a single process-level card and detects:

- new / changed / removed documents (by stable key + sha256)
- cited-but-missing titles (referenced without a stored blob)
- version history entries for each document key
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.storage import ensure_roots, write_json

PROCESS_CARDS_REL = Path("process_cards")
HISTORY_REL = Path("document_versions")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def document_stable_key(doc: Mapping[str, Any]) -> str:
    """Stable key for a document across sources (not content hash)."""
    parts = [
        str(doc.get("official_id") or ""),
        str(doc.get("original_filename") or doc.get("original_title") or ""),
        str(doc.get("document_category") or ""),
        str(doc.get("source_id") or doc.get("portal_family") or ""),
        str(doc.get("download_url") or doc.get("source_page_url") or ""),
    ]
    raw = "|".join(p.strip().lower() for p in parts if p.strip())
    if not raw:
        raw = str(doc.get("sha256") or doc.get("internal_id") or json.dumps(doc, sort_keys=True)[:200])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def process_id_from_doc(doc: Mapping[str, Any], fallback_entity: str | None = None) -> str:
    for key in (
        "procurement_id",
        "administrative_process_id",
        "notice_id",
        "contract_id",
        "official_id",
    ):
        val = doc.get(key)
        if val:
            return str(val)
    # last resort: entity + title hash
    title = str(doc.get("original_title") or doc.get("original_filename") or "unknown")
    ent = str(doc.get("canonical_entity_id") or fallback_entity or "unknown")
    return f"{ent}:{hashlib.sha256(title.encode()).hexdigest()[:12]}"


@dataclass
class DocVersion:
    sha256: str | None
    source_id: str | None
    portal_family: str | None
    recorded_at: str
    change: str  # new | changed | unchanged | removed | cited_missing
    size_bytes: int | None = None
    title: str | None = None
    download_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessCard:
    process_id: str
    canonical_entity_id: str | None
    sources_seen: list[str] = field(default_factory=list)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    changes: list[dict[str, Any]] = field(default_factory=list)
    cited_missing: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _index_previous(card: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not card:
        return {}
    docs = card.get("documents") or {}
    return {str(k): v for k, v in docs.items()} if isinstance(docs, dict) else {}


def merge_documents_into_card(
    process_id: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    previous: Mapping[str, Any] | None = None,
    canonical_entity_id: str | None = None,
    now: str | None = None,
) -> ProcessCard:
    """Build/update a process card from multi-source document rows (pure)."""
    stamp = now or _now_iso()
    prev_docs = _index_previous(previous)
    prev_versions = dict((previous or {}).get("versions") or {}) if previous else {}

    current: dict[str, dict[str, Any]] = {}
    sources: set[str] = set((previous or {}).get("sources_seen") or []) if previous else set()
    changes: list[dict[str, Any]] = []
    versions: dict[str, list[dict[str, Any]]] = {
        str(k): list(v) for k, v in prev_versions.items() if isinstance(v, list)
    }
    cited_missing: list[dict[str, Any]] = []

    entity = canonical_entity_id or (previous or {}).get("canonical_entity_id")

    for doc in documents:
        key = document_stable_key(doc)
        src = str(doc.get("source_id") or doc.get("portal_family") or "unknown")
        sources.add(src)
        sha = doc.get("sha256")
        title = doc.get("original_title") or doc.get("original_filename")
        # Cited but missing: no sha / no raw_uri / error marker
        missing = bool(doc.get("cited_missing")) or (
            not sha and not doc.get("raw_uri") and (doc.get("error") or doc.get("blocker"))
        )
        if missing or (not sha and doc.get("download_url") is None and not doc.get("raw_uri")):
            if not sha and (doc.get("original_title") or doc.get("download_url")):
                cited_missing.append(
                    {
                        "key": key,
                        "title": title,
                        "source_id": src,
                        "reason": doc.get("error") or doc.get("blocker") or "no_blob",
                        "recorded_at": stamp,
                    }
                )
                ver = DocVersion(
                    sha256=None,
                    source_id=src,
                    portal_family=doc.get("portal_family"),
                    recorded_at=stamp,
                    change="cited_missing",
                    title=str(title) if title else None,
                    download_url=doc.get("download_url"),
                )
                versions.setdefault(key, []).append(ver.to_dict())
                continue

        row = {
            "key": key,
            "sha256": sha,
            "source_id": src,
            "portal_family": doc.get("portal_family"),
            "document_category": doc.get("document_category"),
            "title": title,
            "original_filename": doc.get("original_filename"),
            "download_url": doc.get("download_url"),
            "raw_uri": doc.get("raw_uri"),
            "size_bytes": doc.get("size_bytes"),
            "version": doc.get("version"),
            "fetched_at": doc.get("fetched_at") or stamp,
            "canonical_entity_id": doc.get("canonical_entity_id") or entity,
        }
        current[key] = row
        old = prev_docs.get(key)
        if old is None:
            change = "new"
        elif old.get("sha256") and sha and old.get("sha256") != sha:
            change = "changed"
        else:
            change = "unchanged"
        if change != "unchanged":
            changes.append(
                {
                    "key": key,
                    "change": change,
                    "old_sha256": (old or {}).get("sha256"),
                    "new_sha256": sha,
                    "source_id": src,
                    "title": title,
                    "recorded_at": stamp,
                }
            )
            ver = DocVersion(
                sha256=str(sha) if sha else None,
                source_id=src,
                portal_family=doc.get("portal_family"),
                recorded_at=stamp,
                change=change,
                size_bytes=int(doc["size_bytes"]) if doc.get("size_bytes") is not None else None,
                title=str(title) if title else None,
                download_url=doc.get("download_url"),
            )
            versions.setdefault(key, []).append(ver.to_dict())

    # Removals: previously present keys absent now
    for key, old in prev_docs.items():
        if key not in current:
            changes.append(
                {
                    "key": key,
                    "change": "removed",
                    "old_sha256": old.get("sha256"),
                    "new_sha256": None,
                    "source_id": old.get("source_id"),
                    "title": old.get("title"),
                    "recorded_at": stamp,
                }
            )
            versions.setdefault(key, []).append(
                DocVersion(
                    sha256=old.get("sha256"),
                    source_id=old.get("source_id"),
                    portal_family=old.get("portal_family"),
                    recorded_at=stamp,
                    change="removed",
                    title=old.get("title"),
                ).to_dict()
            )

    # Prefer entity from docs
    if not entity:
        for d in current.values():
            if d.get("canonical_entity_id"):
                entity = d["canonical_entity_id"]
                break

    return ProcessCard(
        process_id=process_id,
        canonical_entity_id=str(entity) if entity else None,
        sources_seen=sorted(sources),
        documents=current,
        versions=versions,
        changes=changes,
        cited_missing=cited_missing,
        updated_at=stamp,
    )


def group_run_documents_by_process(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Extract documents from collect_many/entity results grouped by process_id."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for run in results:
        entity = run.get("canonical_entity_id")
        docs = list(run.get("documents") or [])
        # Multi-source: also flatten nested source_results documents
        for src_run in (run.get("source_results") or {}).values():
            if isinstance(src_run, dict):
                docs.extend(src_run.get("documents") or [])
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            pid = process_id_from_doc(doc, fallback_entity=str(entity) if entity else None)
            groups.setdefault(pid, []).append(doc)
    return groups


def load_process_card(process_id: str, *, meta_root: Path | None = None) -> dict[str, Any] | None:
    _, meta = ensure_roots(meta_root=meta_root)
    path = meta / PROCESS_CARDS_REL / f"{_safe_name(process_id)}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_process_card(card: ProcessCard | Mapping[str, Any], *, meta_root: Path | None = None) -> Path:
    _, meta = ensure_roots(meta_root=meta_root)
    data = card.to_dict() if isinstance(card, ProcessCard) else dict(card)
    pid = str(data.get("process_id") or "unknown")
    path = meta / PROCESS_CARDS_REL / f"{_safe_name(pid)}.json"
    write_json(path, data)
    # Append change history ledger
    hist = meta / HISTORY_REL / f"{_safe_name(pid)}.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    for ch in data.get("changes") or []:
        with hist.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ch, ensure_ascii=False) + "\n")
    return path


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:180]


def source_consultation_report(
    *,
    applicable_sources: Sequence[str],
    source_results: Mapping[str, Mapping[str, Any]] | None = None,
    documents: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Distinguish not-consulted / query-failed / unpublished / located / unreadable.

    Pure report for multi-source process reconstruction evidence.
    """
    results = source_results or {}
    docs = list(documents or [])
    rows: list[dict[str, Any]] = []
    for src in applicable_sources:
        rd = results.get(src)
        if rd is None:
            rows.append(
                {
                    "source_id": src,
                    "state": "not_consulted",
                    "documents_located": 0,
                    "documents_unreadable": 0,
                    "documents_unpublished": 0,
                }
            )
            continue
        st = str(rd.get("status") or "").lower()
        src_docs = [d for d in docs if str(d.get("source_id") or d.get("portal_family") or "") == src]
        if not src_docs and isinstance(rd.get("documents"), list):
            src_docs = list(rd.get("documents") or [])
        unreadable = [
            d
            for d in src_docs
            if d.get("quarantined")
            or d.get("unreadable")
            or (d.get("extraction_quality") in {"none", "low"} and d.get("ocr_failed"))
        ]
        unpublished = [
            d for d in src_docs if d.get("cited_missing") or str(d.get("public_access_status") or "") == "not_published"
        ]
        located = [d for d in src_docs if d.get("sha256") or d.get("raw_uri")]
        if st in {"not_queried", "not_queried_budget"}:
            state = "not_consulted"
        elif st in {"connection_failed", "timeout", "error", "failed"} or rd.get("error"):
            state = "query_failed"
        elif unpublished and not located:
            state = "document_not_published"
        elif unreadable and located:
            state = "located_but_unreadable"
        elif located:
            state = "document_located"
        elif st in {"success_zero", "success", "success_nonzero"} and not located:
            state = "document_not_published"
        else:
            state = "query_failed" if rd.get("errors") else "not_consulted"
        rows.append(
            {
                "source_id": src,
                "state": state,
                "status": rd.get("status"),
                "error": rd.get("error") or ((rd.get("errors") or [None])[0]),
                "documents_located": len(located),
                "documents_unreadable": len(unreadable),
                "documents_unpublished": len(unpublished),
            }
        )
    return {
        "generated_at": _now_iso(),
        "sources": rows,
        "summary": {
            "not_consulted": sum(1 for r in rows if r["state"] == "not_consulted"),
            "query_failed": sum(1 for r in rows if r["state"] == "query_failed"),
            "document_not_published": sum(1 for r in rows if r["state"] == "document_not_published"),
            "document_located": sum(1 for r in rows if r["state"] == "document_located"),
            "located_but_unreadable": sum(1 for r in rows if r["state"] == "located_but_unreadable"),
        },
    }


def build_cards_from_collect_summary(
    summary: Mapping[str, Any],
    *,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Create/update process cards for all documents in a collect summary."""
    groups = group_run_documents_by_process(summary.get("results") or [])
    cards: list[dict[str, Any]] = []
    change_counts = {"new": 0, "changed": 0, "removed": 0, "cited_missing": 0}
    for pid, docs in groups.items():
        prev = load_process_card(pid, meta_root=meta_root) if persist else None
        entity = None
        for d in docs:
            if d.get("canonical_entity_id"):
                entity = d["canonical_entity_id"]
                break
        card = merge_documents_into_card(pid, docs, previous=prev, canonical_entity_id=entity)
        for ch in card.changes:
            c = ch.get("change")
            if c in change_counts:
                change_counts[c] += 1
        change_counts["cited_missing"] += len(card.cited_missing)
        if persist:
            save_process_card(card, meta_root=meta_root)
        cards.append(card.to_dict())
    report = {
        "process_count": len(cards),
        "change_counts": change_counts,
        "generated_at": _now_iso(),
        "cards_sample": cards[:5],
    }
    if persist:
        _, meta = ensure_roots(meta_root=meta_root)
        write_json(meta / "process-cards-latest.json", report)
    return report
