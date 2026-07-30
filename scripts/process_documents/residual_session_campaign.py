"""Force residual session collection + bulk SC Compras homolog packs."""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.process_documents.adapters.pncp import PncpDocumentAdapter
from scripts.process_documents.classify_docs import classify_document_record
from scripts.process_documents.multi_source_session import collect_pncp_session_packs
from scripts.process_documents.statuses import SESSION_JUDGMENT_CATEGORIES, DocumentCategory, DocumentRunStatus
from scripts.process_documents.storage import ensure_roots, store_blob, write_json
from scripts.process_documents.models import DocumentRecord

_PNCP = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")


def residual_pncp_session(max_processes: int = 300) -> dict:
    raw, meta = ensure_roots()
    S = {c.value for c in SESSION_JUDGMENT_CATEGORIES}
    by: dict[str, set[str]] = defaultdict(set)
    entity_of: dict[str, str] = {}
    for p in (meta / "runs").glob("*/result.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for doc in d.get("documents") or []:
            pid = str(doc.get("procurement_id") or "")
            if not pid:
                continue
            by[pid].add(classify_document_record(doc))
            if doc.get("canonical_entity_id"):
                entity_of[pid] = str(doc["canonical_entity_id"])

    targets = []
    for pid, cats in by.items():
        if cats & S:
            continue
        m = _PNCP.match(pid)
        if not m:
            continue
        targets.append(
            {
                "process_id": pid,
                "cnpj": m.group(1),
                "ano": int(m.group(4)),
                "seq": int(m.group(3)),
                "entity": entity_of.get(pid) or f"pncp-org:{m.group(1)}",
            }
        )
    # older first
    targets.sort(key=lambda t: (t["ano"], t["seq"]))
    targets = targets[:max_processes]

    started = datetime.now(UTC)
    run_id = f"pd-residual-session-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    adapter = PncpDocumentAdapter(raw_root=raw, meta_root=meta, request_delay=0.1)
    all_docs = []
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

    finished = datetime.now(UTC)
    result = {
        "run_id": run_id,
        "canonical_entity_id": "multi:residual_session",
        "source_id": "pncp+residual_session",
        "portal_family": "pncp",
        "status": DocumentRunStatus.SUCCESS_NONZERO.value if all_docs else DocumentRunStatus.SUCCESS_ZERO.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "query_parameters": {"max_processes": max_processes, "mode": "residual_session_only"},
        "documents_discovered": len(all_docs),
        "documents_downloaded": len(all_docs),
        "processes_seen": touched,
        "documents": all_docs,
        "targets": len(targets),
    }
    run_dir = meta / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "result.json", result)
    with (meta / "run-index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": run_id, "status": result["status"], "documents_downloaded": len(all_docs), "processes_seen": touched}) + "\n")
    return {"run_id": run_id, "targets": len(targets), "touched": touched, "documents": len(all_docs)}


def bulk_sc_compras_homolog(max_per_year: int = 200, years: list[int] | None = None) -> dict:
    """Bulk harvest SC Compras editais with homolog/encerrado situacao."""
    import requests

    raw, meta = ensure_roots()
    years = years or [2024, 2025, 2026]
    session = requests.Session()
    session.headers.update({"User-Agent": "extra-cli-process-documents/1.0", "Accept": "application/json"})
    started = datetime.now(UTC)
    run_id = f"pd-sccompras-bulk-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    docs = []
    seen_ids = set()
    errors = []
    for year in years:
        try:
            time.sleep(0.3)
            r = session.get(f"https://compras.sc.gov.br/api/editais?ano={year}", timeout=(8, 60))
            r.raise_for_status()
            rows = r.json().get("conteudo") or []
        except Exception as exc:
            errors.append(f"year {year}: {exc}")
            continue
        # prefer homolog-like
        def score(row):
            s = str(row.get("situacao") or "").lower()
            sc = 0
            if "homolog" in s:
                sc += 100
            if "adjudic" in s or "arremat" in s:
                sc += 80
            if "encerr" in s:
                sc += 40
            return sc

        ranked = sorted([x for x in rows if isinstance(x, dict)], key=score, reverse=True)
        n = 0
        for row in ranked:
            if n >= max_per_year:
                break
            if score(row) < 40:
                break
            eid = row.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            try:
                time.sleep(0.25)
                d = session.get(f"https://compras.sc.gov.br/api/editais/{eid}", timeout=(8, 40))
                if d.status_code != 200:
                    continue
                detail = d.json()
            except Exception as exc:
                errors.append(str(exc))
                continue
            n += 1
            pid = f"sc-compras:{eid}:{detail.get('edital') or row.get('processo') or eid}"
            sit = str(detail.get("situacao") or row.get("situacao") or "")
            sit_low = sit.lower()
            # notice
            notice_payload = {
                "id": eid,
                "edital": detail.get("edital") or row.get("edital"),
                "objeto": detail.get("objeto") or row.get("objeto"),
                "situacao": sit,
                "dataPublicacao": detail.get("dataPublicacao"),
            }
            for cat, title, payload in (
                (DocumentCategory.EDITAL.value, f"Edital {detail.get('edital') or eid}", notice_payload),
                (
                    DocumentCategory.HOMOLOGACAO.value
                    if "homolog" in sit_low
                    else DocumentCategory.RESULTADO.value,
                    f"SC_Compras_{sit[:40]}",
                    detail,
                ),
            ):
                try:
                    blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    stored = store_blob(blob, raw_root=raw, extension="json", declared_filename=f"{eid}_{cat}.json")
                    docs.append(
                        DocumentRecord(
                            internal_id=stored.sha256[:20],
                            sha256=stored.sha256,
                            size_bytes=stored.size_bytes,
                            download_url=f"https://compras.sc.gov.br/api/editais/{eid}",
                            source_id="sc_compras+bulk_homolog",
                            canonical_entity_id="sc-compras:bulk",
                            portal_family="sc_compras",
                            document_category=cat,
                            original_title=str(title)[:180],
                            procurement_id=pid,
                            declared_mime="application/json",
                            detected_mime="application/json",
                            extension="json",
                            run_id=run_id,
                            raw_uri=stored.raw_uri,
                            unchanged=stored.unchanged,
                        ).to_dict()
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            # FTP if any
            link = detail.get("linkArquivosFTP")
            if link:
                try:
                    time.sleep(0.2)
                    fr = session.get(str(link), timeout=(8, 45), allow_redirects=True)
                    if fr.status_code == 200 and fr.content and len(fr.content) > 64:
                        from scripts.process_documents.storage import detect_mime
                        from scripts.process_documents.classify_docs import classify_document_title

                        mime = detect_mime(fr.content, fr.headers.get("Content-Type"))
                        ext = "zip" if "zip" in mime else ("pdf" if "pdf" in mime else "bin")
                        title = str(detail.get("edital") or eid)
                        cat = classify_document_title(title)
                        if cat in ("outro", "unknown_category"):
                            cat = DocumentCategory.ANEXO.value
                        stored = store_blob(fr.content, raw_root=raw, extension=ext, declared_filename=title[:80])
                        docs.append(
                            DocumentRecord(
                                internal_id=stored.sha256[:20],
                                sha256=stored.sha256,
                                size_bytes=stored.size_bytes,
                                download_url=str(link),
                                source_id="sc_compras+bulk_homolog",
                                canonical_entity_id="sc-compras:bulk",
                                portal_family="sc_compras",
                                document_category=cat,
                                original_title=title[:180],
                                procurement_id=pid,
                                detected_mime=mime,
                                extension=ext,
                                run_id=run_id,
                                raw_uri=stored.raw_uri,
                                unchanged=stored.unchanged,
                            ).to_dict()
                        )
                except Exception as exc:
                    errors.append(f"ftp {eid}: {exc}")

    finished = datetime.now(UTC)
    result = {
        "run_id": run_id,
        "canonical_entity_id": "sc-compras:bulk",
        "source_id": "sc_compras+bulk_homolog",
        "portal_family": "sc_compras",
        "status": DocumentRunStatus.SUCCESS_NONZERO.value if docs else DocumentRunStatus.SUCCESS_ZERO.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "documents": docs,
        "documents_downloaded": len(docs),
        "processes_seen": len({d.get("procurement_id") for d in docs}),
        "errors": errors[:30],
        "query_parameters": {"years": years, "max_per_year": max_per_year},
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
                    "documents_downloaded": len(docs),
                    "processes_seen": result["processes_seen"],
                }
            )
            + "\n"
        )
    return {
        "run_id": run_id,
        "documents": len(docs),
        "processes": result["processes_seen"],
        "errors": errors[:10],
    }


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    out = {}
    if mode in ("residual", "both"):
        out["residual"] = residual_pncp_session(max_processes=int(sys.argv[2]) if len(sys.argv) > 2 else 250)
        print(json.dumps({"residual": out["residual"]}, indent=2))
    if mode in ("scbulk", "both"):
        out["scbulk"] = bulk_sc_compras_homolog(max_per_year=int(sys.argv[3]) if len(sys.argv) > 3 else 180)
        print(json.dumps({"scbulk": out["scbulk"]}, indent=2))
