"""Multi-source campaign for winning-proposal and qualification documents.

Focuses residual processes missing WINNING_PROPOSAL / QUALIFICATION buckets.
Sources:
- PNCP /itens/{n}/resultados (public winner package)
- ZIP expand of proposal/qual-named archives
- Reclassification of existing titles (planilha das licitantes, etc.)

Does not shrink denominators. Residual publication blockers stay nominal.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from scripts.process_documents.adapters.pncp import PncpDocumentAdapter
from scripts.process_documents.classify_docs import classify_document_record
from scripts.process_documents.expand_zips import expand_zip_documents
from scripts.process_documents.multi_source_session import collect_pncp_session_packs
from scripts.process_documents.statuses import (
    QUALIFICATION_CATEGORIES,
    WINNING_PROPOSAL_CATEGORIES,
    DocumentRunStatus,
)
from scripts.process_documents.storage import ensure_roots, write_json

_PNCP = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")


def run_win_qual_campaign(
    *,
    max_pncp: int = 400,
    expand_zips: bool = True,
) -> dict[str, Any]:
    raw, meta = ensure_roots()
    win_cats = {c.value for c in WINNING_PROPOSAL_CATEGORIES}
    qual_cats = {c.value for c in QUALIFICATION_CATEGORIES}

    by: dict[str, dict[str, Any]] = defaultdict(lambda: {"cats": set(), "entity": None})
    for p in (meta / "runs").glob("*/result.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for doc in data.get("documents") or []:
            pid = str(doc.get("procurement_id") or "")
            if not pid:
                continue
            by[pid]["cats"].add(classify_document_record(doc))
            if doc.get("canonical_entity_id"):
                by[pid]["entity"] = doc.get("canonical_entity_id")

    targets = []
    for pid, info in by.items():
        m = _PNCP.match(pid)
        if not m:
            continue
        need_w = not (info["cats"] & win_cats)
        need_q = not (info["cats"] & qual_cats)
        if not (need_w or need_q):
            continue
        # Prefer older years (more likely finished)
        targets.append(
            {
                "process_id": pid,
                "cnpj": m.group(1),
                "ano": int(m.group(4)),
                "seq": int(m.group(3)),
                "entity": info.get("entity") or f"pncp-org:{m.group(1)}",
                "need_w": need_w,
                "need_q": need_q,
                "_prio": (0 if need_w else 1, int(m.group(4)), int(m.group(3))),
            }
        )
    targets.sort(key=lambda t: t["_prio"])
    targets = targets[:max_pncp]

    started = datetime.now(UTC)
    run_id = f"pd-win-qual-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    adapter = PncpDocumentAdapter(raw_root=raw, meta_root=meta, request_delay=0.1)
    all_docs: list[dict[str, Any]] = []
    touched = 0
    for t in targets:
        docs = collect_pncp_session_packs(
            process_id=t["process_id"],
            cnpj14=t["cnpj"],
            ano=t["ano"],
            sequencial=t["seq"],
            entity_id=t["entity"],
            raw_root=raw,
            adapter=adapter,
            run_id=run_id,
        )
        if docs:
            touched += 1
            all_docs.extend(d.to_dict() for d in docs)

    zip_stats: dict[str, Any] = {}
    if expand_zips:
        try:
            zip_stats = expand_zip_documents(max_zips=200, max_members_per_zip=80)
        except Exception as exc:  # pragma: no cover
            zip_stats = {"error": str(exc)}

    finished = datetime.now(UTC)
    result = {
        "run_id": run_id,
        "canonical_entity_id": "multi:win_qual",
        "source_id": "pncp+win_qual",
        "portal_family": "multi_source",
        "status": DocumentRunStatus.SUCCESS_NONZERO.value
        if all_docs
        else DocumentRunStatus.SUCCESS_ZERO.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "query_parameters": {"max_pncp": max_pncp, "expand_zips": expand_zips},
        "documents_discovered": len(all_docs),
        "documents_downloaded": len(all_docs),
        "processes_seen": touched,
        "documents": all_docs,
        "targets": len(targets),
        "zip_expand": zip_stats,
    }
    run_dir = meta / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "result.json", result)
    with (meta / "run-index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": result["status"],
                    "documents_downloaded": len(all_docs),
                    "processes_seen": touched,
                }
            )
            + "\n"
        )
    summary = {
        "run_id": run_id,
        "targets": len(targets),
        "touched": touched,
        "documents": len(all_docs),
        "zip_expand": zip_stats,
    }
    write_json(meta / "win-qual-campaign-summary.json", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_win_qual_campaign(max_pncp=350), indent=2))
