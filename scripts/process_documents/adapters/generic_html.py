"""Safe generic public HTML adapter.

Does not circumvent CAPTCHA/auth. Probes institutional / transparency /
procurement URLs when present; enumerates same-origin links that look like
document downloads. Fail-closed.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from scripts.process_documents.adapters.base import classify_http_status
from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.models import DocumentRecord, DocumentRunResult, EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import detect_mime, ensure_roots, store_blob

USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"
DOC_EXT = re.compile(r"\.(pdf|zip|docx?|xlsx?|odt|ods)(?:$|\?)", re.I)
DOC_HINT = re.compile(
    r"edital|anexo|contrato|licitac|pregao|homolog|ata|planilha|projeto|"
    r"habilit|proposta|adjudic|resultado|julgamento|recurso|parecer|diligenc|"
    r"qualifica|atestado|certidao|tr\b|etp\b",
    re.I,
)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = None
        text = ""
        for k, v in attrs:
            if k.lower() == "href":
                href = v or ""
        if href:
            self.links.append((href, text))

    def handle_data(self, data: str) -> None:
        if self.links and not self.links[-1][1]:
            href, _ = self.links[-1]
            self.links[-1] = (href, data.strip())


class GenericHtmlDocumentAdapter:
    source_id = "generic_public_html"

    def __init__(self, portal_family: str = "generic_public_html", **kwargs: Any) -> None:
        self.portal_family = portal_family
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.timeout = kwargs.get("timeout", (8.0, 40.0))
        self.raw_root, self.meta_root = ensure_roots(
            raw_root=kwargs.get("raw_root"),
            meta_root=kwargs.get("meta_root"),
        )

    def collect(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: str | None = None,
        until: str | None = None,
        max_processes: int = 20,
        download: bool = True,
    ) -> DocumentRunResult:
        started = datetime.now(UTC)
        run_id = f"pd-html-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
        seeds = [
            u
            for u in (
                entity.procurement_portal,
                entity.transparency_portal,
                entity.institutional_site,
            )
            if u
        ]
        # Platform-default public portals when entity lacks a specific URL.
        plats = {p.lower() for p in (entity.platforms or [])}
        defaults = {
            "sc_compras": "https://www.compras.sc.gov.br/",
            "compras_gov": "https://www.gov.br/compras/pt-br",
            "doe_sc": "https://www.doe.sea.sc.gov.br/",
            "tce_sc": "https://www.tcesc.tc.br/",
            "pcp": "https://www.portaldecompraspublicas.com.br/",
        }
        for plat, url in defaults.items():
            if plat in plats and url not in seeds:
                seeds.append(url)
        errors: list[str] = []
        blockers: list[str] = []
        docs: list[DocumentRecord] = []
        pages_attempted = 0
        pages_completed = 0
        downloaded = 0
        unchanged = 0
        failed = 0
        discovered = 0

        if not seeds:
            finished = datetime.now(UTC)
            return DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity.canonical_id,
                source_id=self.source_id,
                portal_family=self.portal_family,
                capabilities_requested=["notice_documents"],
                capabilities_proven=[],
                status=DocumentRunStatus.SOURCE_UNAVAILABLE,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                query_parameters={"since": since, "until": until},
                blockers=["no_public_url_in_discovery"],
                latency_ms=(finished - started).total_seconds() * 1000,
            )

        candidate_urls: list[tuple[str, str]] = []
        for seed in seeds[:3]:
            pages_attempted += 1
            try:
                time.sleep(0.2)
                resp = self.session.get(seed, timeout=self.timeout, allow_redirects=True)
            except requests.Timeout:
                errors.append(f"timeout:{seed}")
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.TIMEOUT,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors,
                    blockers + ["timeout"],
                    docs,
                    since,
                    until,
                )
            except requests.RequestException as exc:
                errors.append(str(exc))
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.CONNECTION_FAILED,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors,
                    blockers + ["connection_failed"],
                    docs,
                    since,
                    until,
                )
            if resp.status_code in (401, 403):
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.AUTH_REQUIRED,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + [f"HTTP {resp.status_code}"],
                    blockers + ["auth_or_forbidden"],
                    docs,
                    since,
                    until,
                )
            if resp.status_code == 429:
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.HTTP_RATE_LIMIT,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + ["429"],
                    blockers + ["rate_limit"],
                    docs,
                    since,
                    until,
                )
            if resp.status_code >= 500:
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.HTTP_SERVER_ERROR,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + [f"HTTP {resp.status_code}"],
                    blockers + ["server_error"],
                    docs,
                    since,
                    until,
                )
            if resp.status_code != 200:
                errors.append(f"HTTP {resp.status_code} for {seed}")
                continue
            pages_completed += 1
            # CAPTCHA heuristics
            body_l = resp.text[:5000].lower()
            if "captcha" in body_l and "g-recaptcha" in body_l:
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.CAPTCHA,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + ["captcha detected"],
                    blockers + ["captcha"],
                    docs,
                    since,
                    until,
                )
            parser = _LinkParser()
            try:
                parser.feed(resp.text)
            except Exception as exc:  # noqa: BLE001 — parse errors are fail-closed
                errors.append(f"html parse: {exc}")
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.PARSE_FAILED,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors,
                    blockers + ["parse_failed"],
                    docs,
                    since,
                    until,
                )
            seed_host = urlparse(seed).netloc
            for href, text in parser.links:
                abs_url = urljoin(seed, href)
                if urlparse(abs_url).netloc and urlparse(abs_url).netloc != seed_host:
                    continue
                label = text or href
                if DOC_EXT.search(abs_url) or DOC_HINT.search(label) or DOC_HINT.search(abs_url):
                    candidate_urls.append((abs_url, label))

        # Dedup URLs
        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for u, t in candidate_urls:
            if u in seen:
                continue
            seen.add(u)
            unique.append((u, t))
        unique = unique[: max(1, min(max_processes, 30))]
        discovered = len(unique)

        if not download:
            for u, t in unique:
                docs.append(
                    DocumentRecord(
                        internal_id=hashlib.sha256(u.encode()).hexdigest()[:20],
                        sha256="",
                        size_bytes=0,
                        download_url=u,
                        source_id=self.source_id,
                        canonical_entity_id=entity.canonical_id,
                        portal_family=self.portal_family,
                        document_category=classify_document_title(t),
                        original_title=t,
                        run_id=run_id,
                    )
                )
            finished = datetime.now(UTC)
            status = (
                DocumentRunStatus.SUCCESS_NONZERO
                if unique
                else DocumentRunStatus.SUCCESS_ZERO
            )
            return self._finish(
                run_id,
                entity,
                started,
                finished,
                status,
                pages_attempted,
                pages_completed,
                discovered,
                0,
                0,
                0,
                errors,
                blockers,
                docs,
                since,
                until,
                justification=(
                    "HTML index crawl completed; no document-like links found on public pages"
                    if status == DocumentRunStatus.SUCCESS_ZERO
                    else None
                ),
            )

        for u, t in unique:
            try:
                time.sleep(0.2)
                resp = self.session.get(u, timeout=self.timeout, allow_redirects=True)
            except requests.Timeout:
                failed += 1
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + [f"timeout download {u}"],
                    blockers + ["timeout"],
                    docs,
                    since,
                    until,
                )
            except requests.RequestException as exc:
                failed += 1
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + [str(exc)],
                    blockers + ["connection_failed"],
                    docs,
                    since,
                    until,
                )
            if resp.status_code != 200:
                failed += 1
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + [f"HTTP {resp.status_code} {u}"],
                    blockers + [classify_http_status(resp.status_code).value],
                    docs,
                    since,
                    until,
                )
            blob = resp.content
            if not blob:
                failed += 1
                finished = datetime.now(UTC)
                return self._finish(
                    run_id,
                    entity,
                    started,
                    finished,
                    DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                    pages_attempted,
                    pages_completed,
                    discovered,
                    downloaded,
                    unchanged,
                    failed,
                    errors + ["empty body"],
                    blockers + ["unexpected_empty"],
                    docs,
                    since,
                    until,
                )
            detected = detect_mime(blob, resp.headers.get("Content-Type"))
            ext = "pdf" if detected == "application/pdf" else ("zip" if detected == "application/zip" else None)
            stored = store_blob(blob, raw_root=self.raw_root, extension=ext, declared_filename=t)
            if stored.unchanged:
                unchanged += 1
            else:
                downloaded += 1
            docs.append(
                DocumentRecord(
                    internal_id=stored.sha256[:20],
                    sha256=stored.sha256,
                    size_bytes=stored.size_bytes,
                    download_url=u,
                    source_id=self.source_id,
                    canonical_entity_id=entity.canonical_id,
                    portal_family=self.portal_family,
                    document_category=classify_document_title(t),
                    original_title=t,
                    declared_mime=resp.headers.get("Content-Type"),
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
        elif pages_completed > 0 and not errors:
            status = DocumentRunStatus.SUCCESS_ZERO
            justification = "Public pages fetched fully; no document-like assets downloaded"
        else:
            status = DocumentRunStatus.PARTIAL if errors else DocumentRunStatus.UNEXPECTED_EMPTY
            justification = None
        return self._finish(
            run_id,
            entity,
            started,
            finished,
            status,
            pages_attempted,
            pages_completed,
            discovered,
            downloaded,
            unchanged,
            failed,
            errors,
            blockers,
            docs,
            since,
            until,
            justification=justification,
        )

    def _finish(
        self,
        run_id: str,
        entity: EntityDocumentDiscovery,
        started: datetime,
        finished: datetime,
        status: DocumentRunStatus,
        pages_attempted: int,
        pages_completed: int,
        discovered: int,
        downloaded: int,
        unchanged: int,
        failed: int,
        errors: list[str],
        blockers: list[str],
        docs: list[DocumentRecord],
        since: str | None,
        until: str | None,
        justification: str | None = None,
    ) -> DocumentRunResult:
        result = DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity.canonical_id,
            source_id=self.source_id,
            portal_family=self.portal_family,
            capabilities_requested=["notice_documents"],
            capabilities_proven=["notice_documents"] if status == DocumentRunStatus.SUCCESS_NONZERO else [],
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            query_parameters={"since": since, "until": until, "seeds": True},
            pages_attempted=pages_attempted,
            pages_completed=pages_completed,
            records_seen=discovered,
            processes_seen=0,
            documents_discovered=discovered,
            documents_downloaded=downloaded,
            documents_unchanged=unchanged,
            documents_failed=failed,
            errors=errors,
            blockers=blockers,
            latency_ms=(finished - started).total_seconds() * 1000,
            documents=docs,
            success_zero_justification=justification,
        )
        run_dir = self.meta_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        import json

        (run_dir / "result.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result.evidence_uri = str(run_dir / "result.json")
        with (self.meta_root / "run-index.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "canonical_entity_id": entity.canonical_id,
                        "status": status.value,
                        "documents_downloaded": downloaded,
                        "documents_unchanged": unchanged,
                        "finished_at": finished.isoformat(),
                        "evidence_uri": result.evidence_uri,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return result
