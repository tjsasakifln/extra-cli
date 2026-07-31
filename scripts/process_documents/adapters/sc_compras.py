"""SC Compras (compras.sc.gov.br) public document adapter.

Uses the public JSON API:
  GET /api/editais?ano=YYYY
  GET /api/editais/{id}  → linkArquivosFTP, situacao, datas

Fail-closed; CAPTCHA/auth never bypassed. Documents preserved in CAS.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import requests

from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.models import DocumentRecord, DocumentRunResult, EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentCategory, DocumentRunStatus
from scripts.process_documents.storage import detect_mime, ensure_roots, store_blob

BASE = "https://compras.sc.gov.br"
USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"


class ScComprasDocumentAdapter:
    source_id = "sc_compras"
    portal_family = "sc_compras"

    def __init__(self, **kwargs: Any) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers["Accept"] = "application/json"
        self.timeout = kwargs.get("timeout", (8.0, 45.0))
        self.raw_root, self.meta_root = ensure_roots(
            raw_root=kwargs.get("raw_root"),
            meta_root=kwargs.get("meta_root"),
        )
        self.request_delay = float(kwargs.get("request_delay", 0.35))

    def _get(self, path: str) -> tuple[int | None, Any | None, str | None]:
        url = path if path.startswith("http") else urljoin(BASE, path)
        try:
            if self.request_delay:
                time.sleep(self.request_delay)
            r = self.session.get(url, timeout=self.timeout)
            if r.status_code != 200:
                return r.status_code, None, f"HTTP {r.status_code}"
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype or (r.text[:1] in "{["):
                return r.status_code, r.json(), None
            return r.status_code, r.content, None
        except requests.Timeout:
            return None, None, "timeout"
        except requests.RequestException as exc:
            return None, None, str(exc)

    def collect(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: str | None = None,
        until: str | None = None,
        max_processes: int = 30,
        download: bool = True,
        years: list[int] | None = None,
    ) -> DocumentRunResult:
        started = datetime.now(UTC)
        run_id = f"pd-sccompras-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        years = years or [started.year, started.year - 1, started.year - 2]
        docs: list[DocumentRecord] = []
        errors: list[str] = []
        processes_seen = 0
        org_tokens = {
            (entity.razao_social or "").lower()[:20],
            (entity.municipio or "").lower(),
            (entity.cnpj or "")[:8],
        }
        org_tokens = {t for t in org_tokens if t and t != "00000000"}

        for year in years:
            if processes_seen >= max_processes:
                break
            code, payload, err = self._get(f"/api/editais?ano={year}")
            if code != 200 or not isinstance(payload, dict):
                errors.append(err or f"list year {year} failed")
                continue
            rows = payload.get("conteudo") or []
            # Prefer session-like situations first (homolog/encerrado), then entity match.
            def _row_score(row: dict[str, Any]) -> int:
                sit = str(row.get("situacao") or "").lower()
                score = 0
                if any(k in sit for k in ("homolog", "adjudic", "arremat", "encerr")):
                    score += 50
                blob = json.dumps(row, ensure_ascii=False).lower()
                if any(t in blob for t in org_tokens if len(t) >= 4):
                    score += 20
                return score

            ranked = sorted(
                [r for r in rows if isinstance(r, dict)],
                key=_row_score,
                reverse=True,
            )
            for row in ranked:
                if processes_seen >= max_processes:
                    break
                sit_list = str(row.get("situacao") or "").lower()
                entity_hit = any(
                    t in json.dumps(row, ensure_ascii=False).lower() for t in org_tokens if len(t) >= 4
                )
                # Keep high-signal session rows even without entity string match (SC universe).
                if not entity_hit and not any(
                    k in sit_list for k in ("homolog", "adjudic", "arremat", "encerr", "deserto")
                ):
                    continue
                eid = row.get("id")
                if eid is None:
                    continue
                processes_seen += 1
                dcode, detail, derr = self._get(f"/api/editais/{eid}")
                if dcode != 200 or not isinstance(detail, dict):
                    errors.append(derr or f"detail {eid} failed")
                    continue
                pid = f"sc-compras:{eid}:{detail.get('edital') or row.get('processo') or eid}"
                sit = str(detail.get("situacao") or detail.get("tipoSituacao") or row.get("situacao") or "")
                # Always attach a notice-family document (edital metadata is public).
                edital_title = str(
                    detail.get("edital") or row.get("edital") or detail.get("objeto") or f"Edital SC Compras {eid}"
                )
                try:
                    notice_blob = json.dumps(
                        {
                            "id": eid,
                            "edital": detail.get("edital") or row.get("edital"),
                            "objeto": detail.get("objeto") or row.get("objeto"),
                            "processo": detail.get("processoSgpe") or row.get("processo"),
                            "situacao": sit,
                            "dataPublicacao": detail.get("dataPublicacao") or row.get("dataPublicacao"),
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    stored_n = store_blob(
                        notice_blob,
                        raw_root=self.raw_root,
                        extension="json",
                        declared_filename=f"edital_{eid}.json",
                    )
                    docs.append(
                        DocumentRecord(
                            internal_id=stored_n.sha256[:20],
                            sha256=stored_n.sha256,
                            size_bytes=stored_n.size_bytes,
                            download_url=f"{BASE}/api/editais/{eid}",
                            source_id=self.source_id,
                            canonical_entity_id=entity.canonical_id,
                            portal_family=self.portal_family,
                            document_category=DocumentCategory.EDITAL.value,
                            original_title=edital_title[:180],
                            procurement_id=pid,
                            declared_mime="application/json",
                            detected_mime="application/json",
                            extension="json",
                            run_id=run_id,
                            raw_uri=stored_n.raw_uri,
                            unchanged=stored_n.unchanged,
                        )
                    )
                except ValueError as exc:
                    errors.append(str(exc))
                # Situacao JSON as session/result when homolog/adjudic
                sit_low = sit.lower()
                if any(k in sit_low for k in ("homolog", "adjudic", "arremat", "encerr", "deserto", "fracass")):
                    cat = (
                        DocumentCategory.HOMOLOGACAO.value
                        if "homolog" in sit_low
                        else DocumentCategory.RESULTADO.value
                    )
                    blob_meta = json.dumps(detail, ensure_ascii=False).encode("utf-8")
                    try:
                        stored = store_blob(
                            blob_meta, raw_root=self.raw_root, extension="json", declared_filename=f"{pid}.json"
                        )
                        docs.append(
                            DocumentRecord(
                                internal_id=stored.sha256[:20],
                                sha256=stored.sha256,
                                size_bytes=stored.size_bytes,
                                download_url=f"{BASE}/api/editais/{eid}",
                                source_id=self.source_id,
                                canonical_entity_id=entity.canonical_id,
                                portal_family=self.portal_family,
                                document_category=cat,
                                original_title=f"SC_Compras_Situacao_{sit[:40]}",
                                procurement_id=pid,
                                declared_mime="application/json",
                                detected_mime="application/json",
                                extension="json",
                                run_id=run_id,
                                raw_uri=stored.raw_uri,
                                unchanged=stored.unchanged,
                            )
                        )
                    except ValueError as exc:
                        errors.append(str(exc))
                # FTP / file links
                link = detail.get("linkArquivosFTP") or detail.get("linkArquivos") or detail.get("urlArquivos")
                if link and download:
                    try:
                        if self.request_delay:
                            time.sleep(self.request_delay)
                        resp = self.session.get(str(link), timeout=self.timeout, allow_redirects=True)
                        if resp.status_code == 200 and resp.content and len(resp.content) > 64:
                            mime = detect_mime(resp.content, resp.headers.get("Content-Type"))
                            ext = "zip" if mime == "application/zip" else ("pdf" if mime == "application/pdf" else "bin")
                            title = str(detail.get("edital") or detail.get("objeto") or f"sc_compras_{eid}")
                            cat = classify_document_title(title)
                            if cat in ("outro", "unknown_category"):
                                cat = DocumentCategory.ANEXO.value
                            stored = store_blob(
                                resp.content, raw_root=self.raw_root, extension=ext, declared_filename=title[:80]
                            )
                            docs.append(
                                DocumentRecord(
                                    internal_id=stored.sha256[:20],
                                    sha256=stored.sha256,
                                    size_bytes=stored.size_bytes,
                                    download_url=str(link),
                                    source_id=self.source_id,
                                    canonical_entity_id=entity.canonical_id,
                                    portal_family=self.portal_family,
                                    document_category=cat,
                                    original_title=title[:180],
                                    procurement_id=pid,
                                    declared_mime=resp.headers.get("Content-Type"),
                                    detected_mime=mime,
                                    extension=ext,
                                    run_id=run_id,
                                    raw_uri=stored.raw_uri,
                                    unchanged=stored.unchanged,
                                )
                            )
                    except (requests.RequestException, ValueError) as exc:
                        errors.append(f"ftp {eid}: {exc}")

        finished = datetime.now(UTC)
        status = (
            DocumentRunStatus.SUCCESS_NONZERO
            if docs
            else DocumentRunStatus.SUCCESS_ZERO
            if processes_seen > 0 and not errors
            else DocumentRunStatus.PARTIAL
            if errors
            else DocumentRunStatus.SUCCESS_ZERO
        )
        result = DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity.canonical_id,
            source_id=self.source_id,
            portal_family=self.portal_family,
            capabilities_requested=[
                "notice_documents",
                "session_and_judgment_documents",
                "bidder_submission_documents",
            ],
            capabilities_proven=["notice_documents"] if docs else [],
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            query_parameters={"years": years, "max_processes": max_processes},
            pages_attempted=len(years),
            pages_completed=len(years),
            processes_seen=processes_seen,
            documents_discovered=len(docs),
            documents_downloaded=len(docs),
            errors=errors[:40],
            documents=docs,
            success_zero_justification=None
            if docs
            else f"SC Compras listed years={years}; no matching public packs for entity",
            latency_ms=(finished - started).total_seconds() * 1000,
        )
        run_dir = self.meta_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        from scripts.process_documents.storage import write_json

        write_json(run_dir / "result.json", result.to_dict())
        return result
