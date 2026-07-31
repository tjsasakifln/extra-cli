"""PNCP document adapter — live fetch of compra arquivos (public API).

Reuses endpoint patterns from ``scripts.crawl.pncp_crawler_adapter`` without
forking a second crawl framework. Fail-closed: never maps errors to SUCCESS_ZERO.
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
from scripts.process_documents.models import DocumentRecord, DocumentRunResult, EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import (
    detect_mime,
    ensure_roots,
    store_blob,
    write_json,
)

PNCP_CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP_API = "https://pncp.gov.br/api/pncp/v1"
USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"
# Pregão eletrônico first (highest volume); keep list short for fail-closed latency.
DEFAULT_MODALIDADES = (6, 8, 4)


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def expand_cnpj14(cnpj: str) -> list[str]:
    """Return candidate CNPJ forms for PNCP org queries."""
    d = digits_only(cnpj)
    out: list[str] = []
    if len(d) == 14:
        out.append(d)
    if len(d) >= 8:
        root = d[:8]
        # Common public-body check digits patterns unknown — try root-padded
        # and rely on consulta filters by cnpj when available
        out.append(root)
    return list(dict.fromkeys(out))


class PncpDocumentAdapter:
    portal_family = "pncp"
    source_id = "pncp"

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 45.0),
        max_retries: int = 3,
        request_delay: float = 0.25,
        raw_root: Path | None = None,
        meta_root: Path | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.raw_root, self.meta_root = ensure_roots(raw_root=raw_root, meta_root=meta_root)

    def _sleep(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> tuple[int | None, Any | None, str | None]:
        last_err: str | None = None
        for attempt in range(self.max_retries):
            try:
                self._sleep()
                resp = self.session.get(url, params=params, timeout=self.timeout)
                code = resp.status_code
                if code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt) * 2
                    time.sleep(min(wait, 60))
                    last_err = f"429 rate limit attempt={attempt}"
                    continue
                if code >= 500:
                    time.sleep(min((2 ** attempt) * 1.5, 30))
                    last_err = f"HTTP {code}"
                    continue
                if code == 204:
                    return code, [], None
                if code != 200:
                    return code, None, f"HTTP {code}: {resp.text[:200]}"
                ctype = resp.headers.get("Content-Type", "")
                if "json" in ctype or resp.text[:1] in ("{", "["):
                    try:
                        return code, resp.json(), None
                    except json.JSONDecodeError as exc:
                        return code, None, f"JSON parse error: {exc}"
                return code, resp.content, None
            except requests.Timeout as exc:
                last_err = f"timeout: {exc}"
                time.sleep(min((2 ** attempt), 20))
            except requests.RequestException as exc:
                last_err = f"connection: {exc}"
                time.sleep(min((2 ** attempt), 20))
        return None, None, last_err or "request failed"

    def _download_bytes(self, url: str) -> tuple[DocumentRunStatus | None, bytes | None, str | None, str | None]:
        """Return (error_status|None, bytes, mime, error_message)."""
        for attempt in range(self.max_retries):
            try:
                self._sleep()
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if resp.status_code == 429:
                    time.sleep(min((2 ** attempt) * 2, 60))
                    continue
                if resp.status_code in (401, 403):
                    return DocumentRunStatus.AUTH_REQUIRED, None, None, f"HTTP {resp.status_code}"
                if resp.status_code == 404:
                    return DocumentRunStatus.HTTP_CLIENT_ERROR, None, None, "HTTP 404"
                if resp.status_code >= 500:
                    time.sleep(min((2 ** attempt) * 1.5, 30))
                    continue
                if resp.status_code != 200:
                    return DocumentRunStatus.HTTP_CLIENT_ERROR, None, None, f"HTTP {resp.status_code}"
                data = resp.content
                if not data:
                    return DocumentRunStatus.UNEXPECTED_EMPTY, None, None, "empty body"
                mime = resp.headers.get("Content-Type")
                return None, data, mime, None
            except requests.Timeout:
                if attempt + 1 >= self.max_retries:
                    return DocumentRunStatus.TIMEOUT, None, None, "timeout"
            except requests.RequestException as exc:
                if attempt + 1 >= self.max_retries:
                    return DocumentRunStatus.CONNECTION_FAILED, None, None, str(exc)
        return DocumentRunStatus.CONNECTION_FAILED, None, None, "download failed"

    def search_processes(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: date,
        until: date,
        max_processes: int = 20,
    ) -> tuple[DocumentRunStatus | None, list[dict[str, Any]], int, int, list[str]]:
        """Search PNCP publicações for entity CNPJ. Returns status_err, processes, pages_att, pages_ok, errors."""
        processes: list[dict[str, Any]] = []
        pages_attempted = 0
        pages_completed = 0
        errors: list[str] = []
        cnpj_digits = digits_only(entity.cnpj)
        if len(cnpj_digits) < 8:
            return DocumentRunStatus.SCHEMA_FAILED, [], 0, 0, ["cnpj too short for PNCP"]

        # Prefer cnpj filter when API accepts; also filter client-side by orgao CNPJ root
        root = cnpj_digits[:8]
        for modalidade in DEFAULT_MODALIDADES:
            page = 1
            while len(processes) < max_processes:
                pages_attempted += 1
                params = {
                    "dataInicial": since.strftime("%Y%m%d"),
                    "dataFinal": until.strftime("%Y%m%d"),
                    "codigoModalidadeContratacao": str(modalidade),
                    "uf": entity.uf or "SC",
                    "pagina": str(page),
                    "tamanhoPagina": "50",
                }
                # Try org cnpj when 14 digits available
                if len(cnpj_digits) == 14:
                    params["cnpj"] = cnpj_digits
                code, payload, err = self._get(f"{PNCP_CONSULTA}/contratacoes/publicacao", params=params)
                if code is None:
                    errors.append(err or "connection failed")
                    return DocumentRunStatus.CONNECTION_FAILED, processes, pages_attempted, pages_completed, errors
                if code == 429:
                    return DocumentRunStatus.HTTP_RATE_LIMIT, processes, pages_attempted, pages_completed, errors + [err or "429"]
                if code in (401, 403):
                    return DocumentRunStatus.AUTH_REQUIRED, processes, pages_attempted, pages_completed, errors + [f"HTTP {code}"]
                if code >= 500:
                    return DocumentRunStatus.HTTP_SERVER_ERROR, processes, pages_attempted, pages_completed, errors + [f"HTTP {code}"]
                if code not in (200, 204):
                    # Some modalidade/window combos return 400 — skip modality, not fatal alone
                    errors.append(f"modalidade={modalidade} page={page} HTTP {code}: {err}")
                    break
                pages_completed += 1
                rows = []
                if isinstance(payload, dict):
                    rows = payload.get("data") or []
                    total_pages = int(payload.get("totalPaginas") or 1)
                elif isinstance(payload, list):
                    rows = payload
                    total_pages = 1
                else:
                    rows = []
                    total_pages = 1
                matched = 0
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    oe = row.get("orgaoEntidade") or {}
                    org_cnpj = digits_only(oe.get("cnpj") if isinstance(oe, dict) else None)
                    # When API didn't filter by cnpj, keep only matching root
                    if org_cnpj and not org_cnpj.startswith(root) and len(cnpj_digits) != 14:
                        continue
                    if len(cnpj_digits) == 14 and org_cnpj and org_cnpj != cnpj_digits:
                        # still accept root match for filial quirks
                        if not org_cnpj.startswith(root):
                            continue
                    processes.append(row)
                    matched += 1
                    if len(processes) >= max_processes:
                        break
                if page >= total_pages or not rows:
                    break
                page += 1
            if len(processes) >= max_processes:
                break
        return None, processes[:max_processes], pages_attempted, pages_completed, errors

    def list_arquivos(self, cnpj14: str, ano: int, sequencial: int) -> tuple[DocumentRunStatus | None, list[dict[str, Any]], str | None]:
        url = f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano}/{sequencial}/arquivos"
        code, payload, err = self._get(url)
        if code is None:
            return DocumentRunStatus.CONNECTION_FAILED, [], err
        if code == 429:
            return DocumentRunStatus.HTTP_RATE_LIMIT, [], err
        if code in (401, 403):
            return DocumentRunStatus.AUTH_REQUIRED, [], f"HTTP {code}"
        if code == 404:
            return None, [], None  # process exists but no arquivos endpoint — empty list OK
        if code == 204:
            return None, [], None
        if code is not None and code >= 500:
            return DocumentRunStatus.HTTP_SERVER_ERROR, [], f"HTTP {code}"
        if code != 200:
            return DocumentRunStatus.HTTP_CLIENT_ERROR, [], f"HTTP {code}: {err}"
        if isinstance(payload, list):
            return None, [p for p in payload if isinstance(p, dict)], None
        if isinstance(payload, dict) and "data" in payload:
            data = payload.get("data") or []
            return None, [p for p in data if isinstance(p, dict)], None
        return DocumentRunStatus.PARSE_FAILED, [], "unexpected arquivos payload"

    def collect_process_key(
        self,
        *,
        cnpj14: str,
        ano: int,
        sequencial: int,
        canonical_entity_id: str,
        process_id: str | None = None,
        download: bool = True,
    ) -> DocumentRunResult:
        """Targeted live collect of all public arquivos for one PNCP process key."""
        started = datetime.now(UTC)
        run_id = f"pd-pncp-key-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        pid = process_id or f"{cnpj14}-1-{int(sequencial):06d}/{ano}"
        query = {
            "cnpj14": cnpj14,
            "ano": ano,
            "sequencial": sequencial,
            "process_id": pid,
            "download": download,
        }
        docs: list[DocumentRecord] = []
        errors: list[str] = []
        blockers: list[str] = []
        discovered = downloaded = unchanged = failed = 0
        a_err, arquivos, a_msg = self.list_arquivos(cnpj14, ano, sequencial)
        if a_err is not None:
            finished = datetime.now(UTC)
            result = DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=canonical_entity_id,
                source_id=self.source_id,
                portal_family=self.portal_family,
                capabilities_requested=[
                    "notice_documents",
                    "planning_documents",
                    "session_and_judgment_documents",
                    "bidder_submission_documents",
                ],
                capabilities_proven=[],
                status=a_err,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                query_parameters=query,
                pages_attempted=1,
                pages_completed=0,
                errors=errors + ([a_msg] if a_msg else []),
                blockers=blockers + [a_err.value],
                latency_ms=(finished - started).total_seconds() * 1000,
            )
            self._persist_run(result)
            return result

        for arq in arquivos:
            discovered += 1
            title = arq.get("titulo") or arq.get("uri") or arq.get("url") or "documento"
            url = arq.get("url") or arq.get("uri") or arq.get("link")
            if isinstance(url, str) and url.startswith("/"):
                url = urljoin("https://pncp.gov.br", url)
            if not url:
                seq_doc = arq.get("sequencialDocumento") or arq.get("sequencial")
                if seq_doc is not None:
                    url = f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano}/{sequencial}/arquivos/{seq_doc}"
                else:
                    failed += 1
                    continue
            category = classify_document_title(str(title))
            if not download:
                docs.append(
                    DocumentRecord(
                        internal_id=hashlib.sha256(str(url).encode()).hexdigest()[:20],
                        sha256="",
                        size_bytes=0,
                        download_url=str(url),
                        source_id=self.source_id,
                        canonical_entity_id=canonical_entity_id,
                        portal_family=self.portal_family,
                        document_category=category,
                        original_title=str(title),
                        procurement_id=pid,
                        notice_id=str(sequencial),
                        run_id=run_id,
                    )
                )
                continue
            d_err, blob, declared_mime, d_msg = self._download_bytes(str(url))
            if d_err is not None or blob is None:
                failed += 1
                errors.append(d_msg or (d_err.value if d_err else "download failed"))
                continue
            detected = detect_mime(blob, declared_mime)
            ext = "pdf" if detected == "application/pdf" else ("zip" if detected == "application/zip" else None)
            try:
                stored = store_blob(blob, raw_root=self.raw_root, extension=ext, declared_filename=str(title))
            except ValueError as exc:
                failed += 1
                errors.append(str(exc))
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
                    source_id=self.source_id,
                    canonical_entity_id=canonical_entity_id,
                    portal_family=self.portal_family,
                    document_category=category,
                    original_title=str(title),
                    original_filename=str(title),
                    procurement_id=pid,
                    notice_id=str(sequencial),
                    declared_mime=declared_mime,
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
            just = None
        elif not arquivos and not errors:
            status = DocumentRunStatus.SUCCESS_ZERO
            just = f"PNCP arquivos empty for {cnpj14}/{ano}/{sequencial}"
        elif errors and not docs:
            status = DocumentRunStatus.DOWNLOAD_INCOMPLETE
            just = None
        else:
            status = DocumentRunStatus.SUCCESS_ZERO
            just = f"no downloadable arquivos for {cnpj14}/{ano}/{sequencial}"
        result = DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=canonical_entity_id,
            source_id=self.source_id,
            portal_family=self.portal_family,
            capabilities_requested=[
                "notice_documents",
                "planning_documents",
                "session_and_judgment_documents",
                "bidder_submission_documents",
            ],
            capabilities_proven=["notice_documents"] if status == DocumentRunStatus.SUCCESS_NONZERO else [],
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            query_parameters=query,
            pages_attempted=1,
            pages_completed=1,
            records_seen=len(arquivos),
            processes_seen=1,
            documents_discovered=discovered,
            documents_downloaded=downloaded,
            documents_unchanged=unchanged,
            documents_failed=failed,
            errors=errors,
            blockers=blockers,
            latency_ms=(finished - started).total_seconds() * 1000,
            documents=docs,
            success_zero_justification=just,
        )
        self._persist_run(result)
        return result

    def collect(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: str | None = None,
        until: str | None = None,
        max_processes: int = 15,
        download: bool = True,
    ) -> DocumentRunResult:
        started = datetime.now(UTC)
        run_id = f"pd-pncp-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
        until_d = date.fromisoformat(until) if until else date.today()
        since_d = date.fromisoformat(since) if since else (until_d - timedelta(days=365))
        query = {
            "since": since_d.isoformat(),
            "until": until_d.isoformat(),
            "max_processes": max_processes,
            "download": download,
            "cnpj": entity.cnpj,
        }
        docs: list[DocumentRecord] = []
        errors: list[str] = []
        blockers: list[str] = []
        retry_count = 0
        downloaded = 0
        unchanged = 0
        failed = 0
        discovered = 0

        err_status, processes, pages_att, pages_ok, search_errors = self.search_processes(
            entity, since=since_d, until=until_d, max_processes=max_processes
        )
        errors.extend(search_errors)
        if err_status is not None:
            finished = datetime.now(UTC)
            result = DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity.canonical_id,
                source_id=self.source_id,
                portal_family=self.portal_family,
                capabilities_requested=["notice_documents", "planning_documents"],
                capabilities_proven=[],
                status=err_status,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                query_parameters=query,
                pages_attempted=pages_att,
                pages_completed=pages_ok,
                records_seen=len(processes),
                processes_seen=len(processes),
                documents_discovered=0,
                documents_downloaded=0,
                documents_unchanged=0,
                documents_failed=0,
                errors=errors,
                blockers=blockers + [err_status.value],
                retry_count=retry_count,
                latency_ms=(finished - started).total_seconds() * 1000,
            )
            self._persist_run(result)
            return result

        for proc in processes:
            oe = proc.get("orgaoEntidade") or {}
            cnpj14 = digits_only(oe.get("cnpj") if isinstance(oe, dict) else None)
            ano = proc.get("anoCompra")
            seq = proc.get("sequencialCompra")
            if not cnpj14 or not ano or not seq:
                errors.append("process missing cnpj/ano/sequencial")
                continue
            try:
                ano_i = int(ano)
                seq_i = int(seq)
            except (TypeError, ValueError):
                errors.append(f"invalid ano/seq {ano}/{seq}")
                continue
            a_err, arquivos, a_msg = self.list_arquivos(cnpj14, ano_i, seq_i)
            if a_err is not None:
                # Partial listing failure → fail closed for this run if we cannot
                # complete enumeration for a discovered process.
                errors.append(a_msg or a_err.value)
                failed += 1
                finished = datetime.now(UTC)
                result = DocumentRunResult(
                    run_id=run_id,
                    canonical_entity_id=entity.canonical_id,
                    source_id=self.source_id,
                    portal_family=self.portal_family,
                    capabilities_requested=["notice_documents", "planning_documents"],
                    capabilities_proven=[],
                    status=DocumentRunStatus.PARTIAL
                    if docs
                    else a_err,
                    started_at=started.isoformat(),
                    finished_at=finished.isoformat(),
                    query_parameters=query,
                    pages_attempted=pages_att,
                    pages_completed=pages_ok,
                    records_seen=len(processes),
                    processes_seen=len(processes),
                    documents_discovered=discovered,
                    documents_downloaded=downloaded,
                    documents_unchanged=unchanged,
                    documents_failed=failed,
                    errors=errors,
                    blockers=blockers + [a_err.value],
                    retry_count=retry_count,
                    latency_ms=(finished - started).total_seconds() * 1000,
                    documents=docs,
                )
                self._persist_run(result)
                return result
            for arq in arquivos:
                discovered += 1
                title = arq.get("titulo") or arq.get("uri") or arq.get("url") or "documento"
                url = arq.get("url") or arq.get("uri") or arq.get("link")
                if isinstance(url, str) and url.startswith("/"):
                    url = urljoin("https://pncp.gov.br", url)
                if not url:
                    # Construct default download path when sequence present
                    seq_doc = arq.get("sequencialDocumento") or arq.get("sequencial")
                    if seq_doc is not None:
                        url = (
                            f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano_i}/{seq_i}/arquivos/{seq_doc}"
                        )
                    else:
                        failed += 1
                        errors.append(f"arquivo without url: {title}")
                        continue
                category = classify_document_title(str(title))
                if not download:
                    docs.append(
                        DocumentRecord(
                            internal_id=hashlib.sha256(url.encode()).hexdigest()[:20],
                            sha256="",
                            size_bytes=0,
                            download_url=url,
                            source_id=self.source_id,
                            canonical_entity_id=entity.canonical_id,
                            portal_family=self.portal_family,
                            document_category=category,
                            original_title=str(title),
                            procurement_id=str(proc.get("numeroControlePNCP") or f"{cnpj14}-{ano_i}-{seq_i}"),
                            notice_id=str(proc.get("numeroCompra") or seq_i),
                            source_page_url=str(proc.get("linkSistemaOrigem") or ""),
                            published_at=str(proc.get("dataPublicacaoPncp") or ""),
                            run_id=run_id,
                            public_access_status="public",
                        )
                    )
                    continue
                d_err, blob, declared_mime, d_msg = self._download_bytes(url)
                if d_err is not None or blob is None:
                    failed += 1
                    errors.append(d_msg or (d_err.value if d_err else "download failed"))
                    # Fail closed: incomplete required download aborts SUCCESS
                    finished = datetime.now(UTC)
                    result = DocumentRunResult(
                        run_id=run_id,
                        canonical_entity_id=entity.canonical_id,
                        source_id=self.source_id,
                        portal_family=self.portal_family,
                        capabilities_requested=["notice_documents", "planning_documents"],
                        capabilities_proven=["notice_documents"] if docs else [],
                        status=DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                        started_at=started.isoformat(),
                        finished_at=finished.isoformat(),
                        query_parameters=query,
                        pages_attempted=pages_att,
                        pages_completed=pages_ok,
                        records_seen=len(processes),
                        processes_seen=len(processes),
                        documents_discovered=discovered,
                        documents_downloaded=downloaded,
                        documents_unchanged=unchanged,
                        documents_failed=failed,
                        errors=errors,
                        blockers=blockers + [d_err.value if d_err else "download_failed"],
                        retry_count=retry_count,
                        latency_ms=(finished - started).total_seconds() * 1000,
                        documents=docs,
                    )
                    self._persist_run(result)
                    return result
                detected = detect_mime(blob, declared_mime)
                # HTML disguised as PDF is still stored but classified
                ext = None
                if detected == "application/pdf":
                    ext = "pdf"
                elif detected == "application/zip":
                    ext = "zip"
                elif detected == "text/html":
                    ext = "html"
                try:
                    stored = store_blob(blob, raw_root=self.raw_root, extension=ext, declared_filename=str(title))
                except ValueError as exc:
                    failed += 1
                    errors.append(str(exc))
                    finished = datetime.now(UTC)
                    result = DocumentRunResult(
                        run_id=run_id,
                        canonical_entity_id=entity.canonical_id,
                        source_id=self.source_id,
                        portal_family=self.portal_family,
                        capabilities_requested=["notice_documents", "planning_documents"],
                        capabilities_proven=[],
                        status=DocumentRunStatus.PERSISTENCE_FAILED,
                        started_at=started.isoformat(),
                        finished_at=finished.isoformat(),
                        query_parameters=query,
                        pages_attempted=pages_att,
                        pages_completed=pages_ok,
                        records_seen=len(processes),
                        processes_seen=len(processes),
                        documents_discovered=discovered,
                        documents_downloaded=downloaded,
                        documents_unchanged=unchanged,
                        documents_failed=failed,
                        errors=errors,
                        blockers=blockers + ["persistence_failed"],
                        retry_count=retry_count,
                        latency_ms=(finished - started).total_seconds() * 1000,
                        documents=docs,
                    )
                    self._persist_run(result)
                    return result
                if stored.unchanged:
                    unchanged += 1
                else:
                    downloaded += 1
                docs.append(
                    DocumentRecord(
                        internal_id=stored.sha256[:20],
                        sha256=stored.sha256,
                        size_bytes=stored.size_bytes,
                        download_url=url,
                        source_id=self.source_id,
                        canonical_entity_id=entity.canonical_id,
                        portal_family=self.portal_family,
                        document_category=category,
                        original_title=str(title),
                        original_filename=str(title),
                        procurement_id=str(proc.get("numeroControlePNCP") or f"{cnpj14}-{ano_i}-{seq_i}"),
                        notice_id=str(proc.get("numeroCompra") or seq_i),
                        source_page_url=str(proc.get("linkSistemaOrigem") or ""),
                        published_at=str(proc.get("dataPublicacaoPncp") or ""),
                        declared_mime=declared_mime,
                        detected_mime=detected,
                        extension=ext,
                        run_id=run_id,
                        raw_uri=stored.raw_uri,
                        unchanged=stored.unchanged,
                    )
                )

        finished = datetime.now(UTC)
        if pages_att > 0 and pages_ok < pages_att and not processes and errors:
            status = DocumentRunStatus.PAGINATION_INCOMPLETE
            justification = None
        elif downloaded + unchanged > 0:
            status = DocumentRunStatus.SUCCESS_NONZERO
            justification = None
        elif not processes:
            # Full search completed with zero matching processes in window
            if pages_att > 0 and pages_ok == pages_att and not errors:
                status = DocumentRunStatus.SUCCESS_ZERO
                justification = (
                    f"PNCP consulta completed for window {since_d}..{until_d}; "
                    f"modalidades={list(DEFAULT_MODALIDADES)}; zero matching processes for CNPJ root"
                )
            elif errors:
                status = DocumentRunStatus.PARTIAL
                justification = None
            else:
                status = DocumentRunStatus.UNEXPECTED_EMPTY
                justification = None
        else:
            # processes seen but zero arquivos
            if pages_ok >= pages_att and not errors:
                status = DocumentRunStatus.SUCCESS_ZERO
                justification = (
                    f"PNCP processos={len(processes)} enumerated; arquivos endpoints returned empty for all"
                )
            else:
                status = DocumentRunStatus.PARTIAL
                justification = None

        result = DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity.canonical_id,
            source_id=self.source_id,
            portal_family=self.portal_family,
            capabilities_requested=["notice_documents", "planning_documents"],
            capabilities_proven=["notice_documents"] if status == DocumentRunStatus.SUCCESS_NONZERO else [],
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            query_parameters=query,
            pages_attempted=pages_att,
            pages_completed=pages_ok,
            records_seen=len(processes),
            processes_seen=len(processes),
            documents_discovered=discovered,
            documents_downloaded=downloaded,
            documents_unchanged=unchanged,
            documents_failed=failed,
            errors=errors,
            blockers=blockers,
            retry_count=retry_count,
            latency_ms=(finished - started).total_seconds() * 1000,
            documents=docs,
            success_zero_justification=justification,
        )
        try:
            result.validate_fail_closed()
        except ValueError as exc:
            result.status = DocumentRunStatus.SCHEMA_FAILED
            result.errors.append(str(exc))
        self._persist_run(result)
        return result

    def _persist_run(self, result: DocumentRunResult) -> None:
        run_dir = self.meta_root / "runs" / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "result.json"
        write_json(path, result.to_dict())
        result.evidence_uri = str(path)
        result.raw_manifest_uri = str(run_dir / "documents.jsonl")
        with (run_dir / "documents.jsonl").open("w", encoding="utf-8") as fh:
            for doc in result.documents:
                fh.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
        # index append
        index = self.meta_root / "run-index.jsonl"
        with index.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "run_id": result.run_id,
                        "canonical_entity_id": result.canonical_entity_id,
                        "status": result.status.value,
                        "documents_downloaded": result.documents_downloaded,
                        "documents_unchanged": result.documents_unchanged,
                        "finished_at": result.finished_at,
                        "evidence_uri": result.evidence_uri,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
