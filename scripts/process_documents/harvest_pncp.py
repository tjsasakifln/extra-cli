"""Bulk PNCP harvest for live proof and corpus (public API).

Searches SC publications by modality/window, downloads arquivos, maps to
registry entities by CNPJ root when possible. Fail-closed per process.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.discovery import load_discovery
from scripts.process_documents.models import DocumentRecord, DocumentRunResult
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import detect_mime, ensure_roots, store_blob, write_json

PNCP_CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP_API = "https://pncp.gov.br/api/pncp/v1"
USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"


def digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def harvest_sc_window(
    *,
    since: str | None = None,
    until: str | None = None,
    modalidades: tuple[int, ...] = (6, 8),
    max_processes: int = 40,
    max_pages_per_modalidade: int = 3,
    download: bool = True,
    uf: str = "SC",
) -> dict[str, Any]:
    until_d = date.fromisoformat(until) if until else date.today()
    since_d = date.fromisoformat(since) if since else (until_d - timedelta(days=180))
    raw_root, meta_root = ensure_roots()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    discoveries = load_discovery()
    by_root: dict[str, str] = {}
    for d in discoveries:
        root = digits(d.cnpj)[:8]
        if len(root) == 8 and root != "00000000":
            by_root.setdefault(root, d.canonical_id)

    started = datetime.now(UTC)
    run_id = f"pd-pncp-harvest-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    processes: list[dict[str, Any]] = []
    errors: list[str] = []
    pages_attempted = 0
    pages_completed = 0

    for mod in modalidades:
        for page in range(1, max_pages_per_modalidade + 1):
            if len(processes) >= max_processes:
                break
            pages_attempted += 1
            params = {
                "dataInicial": since_d.strftime("%Y%m%d"),
                "dataFinal": until_d.strftime("%Y%m%d"),
                "codigoModalidadeContratacao": str(mod),
                "uf": uf,
                "pagina": str(page),
                "tamanhoPagina": "50",
            }
            try:
                time.sleep(0.3)
                resp = session.get(
                    f"{PNCP_CONSULTA}/contratacoes/publicacao",
                    params=params,
                    timeout=(5, 50),
                )
            except requests.Timeout:
                errors.append(f"timeout modalidade={mod} page={page}")
                continue
            except requests.RequestException as exc:
                errors.append(f"connection modalidade={mod} page={page}: {exc}")
                continue
            if resp.status_code == 429:
                errors.append("429 rate limit")
                time.sleep(10)
                continue
            if resp.status_code != 200:
                errors.append(f"HTTP {resp.status_code} modalidade={mod} page={page}")
                continue
            pages_completed += 1
            try:
                payload = resp.json()
            except json.JSONDecodeError as exc:
                errors.append(f"json: {exc}")
                continue
            rows = payload.get("data") or []
            if not rows:
                break
            for row in rows:
                if len(processes) >= max_processes:
                    break
                processes.append(row)
            total_pages = int(payload.get("totalPaginas") or 1)
            if page >= total_pages:
                break

    docs: list[DocumentRecord] = []
    downloaded = 0
    unchanged = 0
    failed = 0
    discovered = 0
    entity_hits: dict[str, int] = {}

    for proc in processes:
        oe = proc.get("orgaoEntidade") or {}
        cnpj14 = digits(oe.get("cnpj") if isinstance(oe, dict) else None)
        ano = proc.get("anoCompra")
        seq = proc.get("sequencialCompra")
        if not cnpj14 or not ano or not seq:
            continue
        root = cnpj14[:8]
        entity_id = by_root.get(root) or f"pncp-org:{cnpj14}"
        entity_hits[entity_id] = entity_hits.get(entity_id, 0) + 1
        try:
            time.sleep(0.25)
            arq_resp = session.get(
                f"{PNCP_API}/orgaos/{cnpj14}/compras/{int(ano)}/{int(seq)}/arquivos",
                timeout=(5, 40),
            )
        except requests.RequestException as exc:
            errors.append(str(exc))
            failed += 1
            continue
        if arq_resp.status_code == 204:
            continue
        if arq_resp.status_code != 200:
            errors.append(f"arquivos HTTP {arq_resp.status_code} {cnpj14}/{ano}/{seq}")
            failed += 1
            continue
        try:
            arquivos = arq_resp.json()
        except json.JSONDecodeError:
            errors.append("arquivos parse failed")
            failed += 1
            continue
        if not isinstance(arquivos, list):
            arquivos = arquivos.get("data") if isinstance(arquivos, dict) else []
        for arq in arquivos or []:
            if not isinstance(arq, dict):
                continue
            discovered += 1
            title = str(arq.get("titulo") or "documento")
            url = arq.get("url") or arq.get("uri")
            if isinstance(url, str) and url.startswith("/"):
                url = urljoin("https://pncp.gov.br", url)
            if not url:
                seq_doc = arq.get("sequencialDocumento") or arq.get("sequencial")
                if seq_doc is not None:
                    url = f"{PNCP_API}/orgaos/{cnpj14}/compras/{int(ano)}/{int(seq)}/arquivos/{seq_doc}"
                else:
                    failed += 1
                    continue
            if not download:
                docs.append(
                    DocumentRecord(
                        internal_id=hashlib.sha256(str(url).encode()).hexdigest()[:20],
                        sha256="",
                        size_bytes=0,
                        download_url=str(url),
                        source_id="pncp",
                        canonical_entity_id=entity_id,
                        portal_family="pncp",
                        document_category=classify_document_title(title),
                        original_title=title,
                        procurement_id=str(proc.get("numeroControlePNCP") or f"{cnpj14}-{ano}-{seq}"),
                        run_id=run_id,
                    )
                )
                continue
            try:
                time.sleep(0.2)
                dresp = session.get(str(url), timeout=(5, 60), allow_redirects=True)
            except requests.RequestException as exc:
                errors.append(f"download {url}: {exc}")
                failed += 1
                continue
            if dresp.status_code != 200 or not dresp.content:
                errors.append(f"download HTTP {dresp.status_code} {url}")
                failed += 1
                continue
            blob = dresp.content
            detected = detect_mime(blob, dresp.headers.get("Content-Type"))
            ext = "pdf" if detected == "application/pdf" else ("zip" if detected == "application/zip" else None)
            try:
                stored = store_blob(blob, raw_root=raw_root, extension=ext, declared_filename=title)
            except ValueError as exc:
                errors.append(str(exc))
                failed += 1
                continue
            if stored.unchanged:
                unchanged += 1
            else:
                downloaded += 1
            docs.append(
                DocumentRecord(
                    internal_id=stored.sha256[:20],
                    sha256=stored.sha256,
                    size_bytes=stored.size_bytes,
                    download_url=str(url),
                    source_id="pncp",
                    canonical_entity_id=entity_id,
                    portal_family="pncp",
                    document_category=classify_document_title(title),
                    original_title=title,
                    procurement_id=str(proc.get("numeroControlePNCP") or f"{cnpj14}-{ano}-{seq}"),
                    notice_id=str(proc.get("numeroCompra") or seq),
                    published_at=str(proc.get("dataPublicacaoPncp") or ""),
                    declared_mime=dresp.headers.get("Content-Type"),
                    detected_mime=detected,
                    extension=ext,
                    run_id=run_id,
                    raw_uri=stored.raw_uri,
                    unchanged=stored.unchanged,
                )
            )

    finished = datetime.now(UTC)
    if downloaded + unchanged > 0:
        status = DocumentRunStatus.SUCCESS_NONZERO
        justification = None
    elif pages_completed > 0 and not processes and not errors:
        status = DocumentRunStatus.SUCCESS_ZERO
        justification = f"PNCP harvest window {since_d}..{until_d} empty for SC modalidades={list(modalidades)}"
    elif processes and discovered == 0 and not errors:
        status = DocumentRunStatus.SUCCESS_ZERO
        justification = f"processes={len(processes)} but zero arquivos listed"
    elif errors and not docs:
        status = DocumentRunStatus.CONNECTION_FAILED if any("timeout" in e or "connection" in e for e in errors) else DocumentRunStatus.PARTIAL
        justification = None
    else:
        status = DocumentRunStatus.PARTIAL
        justification = None

    # Emit synthetic per-entity SUCCESS markers for mapped entities that had downloads
    entity_runs = []
    by_entity_docs: dict[str, list[DocumentRecord]] = {}
    for doc in docs:
        by_entity_docs.setdefault(doc.canonical_entity_id, []).append(doc)

    for entity_id, edocs in by_entity_docs.items():
        erun_id = f"{run_id}-{hashlib.sha256(entity_id.encode()).hexdigest()[:8]}"
        er = DocumentRunResult(
            run_id=erun_id,
            canonical_entity_id=entity_id,
            source_id="pncp",
            portal_family="pncp",
            capabilities_requested=["notice_documents"],
            capabilities_proven=["notice_documents"],
            status=DocumentRunStatus.SUCCESS_NONZERO,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            query_parameters={
                "harvest_run_id": run_id,
                "since": since_d.isoformat(),
                "until": until_d.isoformat(),
                "uf": uf,
            },
            pages_attempted=pages_attempted,
            pages_completed=pages_completed,
            records_seen=len(processes),
            processes_seen=entity_hits.get(entity_id, 0),
            documents_discovered=len(edocs),
            documents_downloaded=sum(1 for d in edocs if not d.unchanged and d.sha256),
            documents_unchanged=sum(1 for d in edocs if d.unchanged),
            documents_failed=0,
            documents=edocs,
            latency_ms=(finished - started).total_seconds() * 1000,
        )
        run_dir = meta_root / "runs" / erun_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "result.json", er.to_dict())
        with (meta_root / "run-index.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "run_id": erun_id,
                        "canonical_entity_id": entity_id,
                        "status": er.status.value,
                        "documents_downloaded": er.documents_downloaded,
                        "documents_unchanged": er.documents_unchanged,
                        "finished_at": er.finished_at,
                        "evidence_uri": str(run_dir / "result.json"),
                        "harvest_run_id": run_id,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        entity_runs.append(er.to_dict())

    summary = {
        "run_id": run_id,
        "status": status.value,
        "success_zero_justification": justification,
        "since": since_d.isoformat(),
        "until": until_d.isoformat(),
        "pages_attempted": pages_attempted,
        "pages_completed": pages_completed,
        "processes_seen": len(processes),
        "documents_discovered": discovered,
        "documents_downloaded": downloaded,
        "documents_unchanged": unchanged,
        "documents_failed": failed,
        "errors": errors[:50],
        "entity_hits": len(entity_hits),
        "entity_runs": len(entity_runs),
        "latency_ms": (finished - started).total_seconds() * 1000,
        "documents": [d.to_dict() for d in docs],
    }
    write_json(meta_root / "runs" / run_id / "harvest.json", summary)
    write_json(meta_root / "live-harvest-latest.json", {k: v for k, v in summary.items() if k != "documents"})
    return summary
