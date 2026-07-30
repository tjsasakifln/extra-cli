"""CIGA CKAN (dados.ciga.sc.gov.br) document adapter — public ZIPs of DOM-SC publications.

Live-capable when PNCP is unreachable. Reuses CKAN public API patterns from
``scripts.crawl.ciga_ckan_crawler`` without forking a second registry.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.models import DocumentRecord, DocumentRunResult, EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import (
    detect_mime,
    ensure_roots,
    safe_extract_zip,
    store_blob,
    write_json,
)

CKAN_API = "https://dados.ciga.sc.gov.br/api/3/action"
USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"


class CigaCkanDocumentAdapter:
    portal_family = "ciga_ckan"
    source_id = "ciga_ckan"
    # Instance-level caches to avoid re-hitting package_list/show for every entity.
    _packages_cache: list[str] | None = None
    _package_detail_cache: dict[str, dict[str, Any]] = {}
    _resource_blob_cache: dict[str, bytes] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.timeout = kwargs.get("timeout", (5.0, 60.0))
        self.raw_root, self.meta_root = ensure_roots(
            raw_root=kwargs.get("raw_root"),
            meta_root=kwargs.get("meta_root"),
        )
        self._request_delay = float(kwargs.get("request_delay", 0.05))

    def _ckan(self, action: str, params: dict[str, Any] | None = None) -> Any:
        if self._request_delay > 0:
            time.sleep(self._request_delay)
        r = self.session.get(f"{CKAN_API}/{action}", params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()
        if not payload.get("success"):
            raise RuntimeError(f"CKAN success=false for {action}")
        return payload.get("result")

    def _package_list(self) -> list[str]:
        if CigaCkanDocumentAdapter._packages_cache is None:
            result = self._ckan("package_list")
            CigaCkanDocumentAdapter._packages_cache = list(result or [])
        return CigaCkanDocumentAdapter._packages_cache

    def _package_show(self, pkg_id: str) -> dict[str, Any]:
        cache = CigaCkanDocumentAdapter._package_detail_cache
        if pkg_id not in cache:
            cache[pkg_id] = self._ckan("package_show", {"id": pkg_id}) or {}
        return cache[pkg_id]

    def collect(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: str | None = None,
        until: str | None = None,
        max_processes: int = 5,
        download: bool = True,
    ) -> DocumentRunResult:
        started = datetime.now(UTC)
        run_id = f"pd-ciga-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        errors: list[str] = []
        docs: list[DocumentRecord] = []
        pages_attempted = 0
        pages_completed = 0
        downloaded = 0
        unchanged = 0
        failed = 0
        discovered = 0

        try:
            pages_attempted += 1
            packages = self._package_list()
            pages_completed += 1
        except Exception as exc:  # noqa: BLE001
            finished = datetime.now(UTC)
            return DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity.canonical_id,
                source_id=self.source_id,
                portal_family=self.portal_family,
                capabilities_requested=["notice_documents"],
                capabilities_proven=[],
                status=DocumentRunStatus.CONNECTION_FAILED,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                errors=[str(exc)],
                blockers=["ciga_connection_failed"],
                pages_attempted=pages_attempted,
                pages_completed=pages_completed,
                latency_ms=(finished - started).total_seconds() * 1000,
            )

        # Prefer recent DOM-SC publication months
        candidates = sorted(
            [p for p in packages if str(p).startswith("domsc-publicacoes-de-")],
            reverse=True,
        )[: max(1, max_processes)]
        if not candidates:
            candidates = sorted(packages, reverse=True)[:3]

        mun_token = (entity.municipio or "").lower().replace(" ", "-")[:20]

        for pkg_id in candidates:
            pages_attempted += 1
            try:
                pkg = self._package_show(pkg_id)
                pages_completed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"package_show {pkg_id}: {exc}")
                continue
            resources = (pkg or {}).get("resources") or []
            # limit resources per package — 2 is enough for operational SUCCESS_NONZERO
            for res in resources[:2]:
                url = res.get("url")
                title = res.get("name") or res.get("description") or pkg_id
                if not url:
                    continue
                discovered += 1
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
                            document_category=classify_document_title(str(title)),
                            original_title=str(title),
                            procurement_id=f"ciga:{pkg_id}",
                            run_id=run_id,
                        )
                    )
                    continue
                try:
                    blob_cache = CigaCkanDocumentAdapter._resource_blob_cache
                    if url in blob_cache:
                        blob = blob_cache[url]
                        declared_mime = None
                    else:
                        if self._request_delay > 0:
                            time.sleep(self._request_delay)
                        resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                        if resp.status_code != 200 or not resp.content:
                            failed += 1
                            finished = datetime.now(UTC)
                            return self._result(
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
                                errors + [f"HTTP {resp.status_code}"],
                                ["download_failed"],
                                docs,
                            )
                        blob = resp.content
                        declared_mime = resp.headers.get("Content-Type")
                        # Cap memory: keep only a few blobs
                        if len(blob_cache) < 8:
                            blob_cache[url] = blob
                except requests.Timeout:
                    failed += 1
                    finished = datetime.now(UTC)
                    return self._result(
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
                        errors + [f"timeout {url}"],
                        ["timeout"],
                        docs,
                    )
                except requests.RequestException as exc:
                    failed += 1
                    finished = datetime.now(UTC)
                    return self._result(
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
                        ["connection_failed"],
                        docs,
                    )
                detected = detect_mime(blob, declared_mime if "declared_mime" in dir() else None)
                ext = "zip" if detected == "application/zip" else ("pdf" if detected == "application/pdf" else None)
                stored = store_blob(blob, raw_root=self.raw_root, extension=ext, declared_filename=str(title))
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
                        document_category=classify_document_title(str(title)),
                        original_title=str(title),
                        procurement_id=f"ciga:{pkg_id}",
                        declared_mime=declared_mime if "declared_mime" in dir() else None,
                        detected_mime=detected,
                        extension=ext,
                        run_id=run_id,
                        raw_uri=stored.raw_uri,
                        unchanged=stored.unchanged,
                    )
                )
                # Safe ZIP expand for nested PDFs (limit 3 members stored) — only first entity pays cost
                if detected == "application/zip" and downloaded + unchanged <= 3:
                    try:
                        tmp = self.meta_root / "tmp_zip" / stored.sha256
                        if not tmp.exists() or not any(tmp.iterdir()):
                            extracted = safe_extract_zip(stored.path, tmp)
                        else:
                            extracted = [p for p in tmp.rglob("*") if p.is_file()]
                        for member in extracted[:3]:
                            data = member.read_bytes() if hasattr(member, "read_bytes") else Path(member).read_bytes()
                            if not data:
                                continue
                            mname = member.name if hasattr(member, "name") else str(member)
                            if mun_token and mun_token not in mname.lower() and len(extracted) > 10:
                                continue
                            m_det = detect_mime(data)
                            m_ext = "pdf" if m_det == "application/pdf" else None
                            m_stored = store_blob(
                                data,
                                raw_root=self.raw_root,
                                extension=m_ext,
                                declared_filename=mname,
                            )
                            if m_stored.unchanged:
                                unchanged += 1
                            else:
                                downloaded += 1
                            discovered += 1
                            docs.append(
                                DocumentRecord(
                                    internal_id=m_stored.sha256[:20],
                                    sha256=m_stored.sha256,
                                    size_bytes=m_stored.size_bytes,
                                    download_url=f"{url}#{mname}",
                                    source_id=self.source_id,
                                    canonical_entity_id=entity.canonical_id,
                                    portal_family=self.portal_family,
                                    document_category=classify_document_title(mname),
                                    original_title=mname,
                                    original_filename=mname,
                                    procurement_id=f"ciga:{pkg_id}:{mname}",
                                    detected_mime=m_det,
                                    extension=m_ext,
                                    run_id=run_id,
                                    raw_uri=m_stored.raw_uri,
                                    unchanged=m_stored.unchanged,
                                )
                            )
                    except ValueError as exc:
                        errors.append(f"zip:{exc}")
                # stop early once we have enough docs
                if downloaded + unchanged >= max(1, max_processes):
                    break
            if downloaded + unchanged >= max(1, max_processes):
                break

        finished = datetime.now(UTC)
        if downloaded + unchanged > 0:
            status = DocumentRunStatus.SUCCESS_NONZERO
            justification = None
        elif pages_completed > 0 and not errors:
            status = DocumentRunStatus.SUCCESS_ZERO
            justification = "CIGA package_list/show completed; no downloadable resources in selected packages"
        else:
            status = DocumentRunStatus.PARTIAL if errors else DocumentRunStatus.UNEXPECTED_EMPTY
            justification = None
        return self._result(
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
            [],
            docs,
            justification=justification,
        )

    def _result(
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
        justification: str | None = None,
    ) -> DocumentRunResult:
        result = DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity.canonical_id,
            source_id=self.source_id,
            portal_family=self.portal_family,
            capabilities_requested=["notice_documents", "administrative_process_documents"],
            capabilities_proven=["notice_documents"] if status == DocumentRunStatus.SUCCESS_NONZERO else [],
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
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
        write_json(run_dir / "result.json", result.to_dict())
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
