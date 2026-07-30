"""Multi-source live collection for session/judgment, proposals, and qualification.

Sources (public only, fail-closed):
1. PNCP ``/atas`` — Ata de Registro de Preços / session packs when published
2. PNCP ``/itens`` — structured item outcomes (homologação, valores, situação)
3. PNCP ``/historico`` — maintenance/status log as judgment provenance
4. ``linkSistemaOrigem`` / procurement portal HTML — same-origin docs with
   session/proposal/qualification title hints
5. CIGA DOM-SC autopublicações already in CAS — reclassify acts as session docs

Does not circumvent CAPTCHA/auth. Does not shrink completeness denominators.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from scripts.process_documents.adapters.generic_html import GenericHtmlDocumentAdapter, _LinkParser
from scripts.process_documents.adapters.pncp import PNCP_API, PncpDocumentAdapter
from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.models import DocumentRecord
from scripts.process_documents.statuses import (
    QUALIFICATION_CATEGORIES,
    SESSION_JUDGMENT_CATEGORIES,
    WINNING_PROPOSAL_CATEGORIES,
    DocumentCategory,
    DocumentRunStatus,
)
from scripts.process_documents.storage import detect_mime, ensure_roots, store_blob, write_json

USER_AGENT = "extra-cli-process-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)"
_PNCP_PID = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")

SESSION_HINT = re.compile(
    r"ata|homolog|adjudic|resultado|julgamento|sess[aã]o|parecer|recurso|diligenc|decis[aã]o",
    re.I,
)
WIN_HINT = re.compile(r"proposta|planilha.*(licitante|vencedor)|comercial", re.I)
QUAL_HINT = re.compile(
    r"habilita|certid[aã]o|qualifica|atestado|cnd|fgts|cndt|balan[cç]o|cat\b|art\b|rrt\b|declara",
    re.I,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _store_json_doc(
    *,
    payload: Any,
    title: str,
    category: str,
    process_id: str,
    entity_id: str,
    source_id: str,
    portal_family: str,
    download_url: str,
    raw_root: Path,
    run_id: str,
) -> DocumentRecord:
    blob = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    stored = store_blob(blob, raw_root=raw_root, extension="json", declared_filename=title)
    return DocumentRecord(
        internal_id=stored.sha256[:20],
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        download_url=download_url,
        source_id=source_id,
        canonical_entity_id=entity_id,
        portal_family=portal_family,
        document_category=category,
        original_title=title,
        original_filename=title if title.endswith(".json") else f"{title}.json",
        procurement_id=process_id,
        declared_mime="application/json",
        detected_mime="application/json",
        extension="json",
        run_id=run_id,
        raw_uri=stored.raw_uri,
        unchanged=stored.unchanged,
        public_access_status="public",
    )


def _classify_item_outcome(item: dict[str, Any]) -> str | None:
    sit_nome = str(item.get("situacaoCompraItemNome") or "").lower()
    if "homolog" in sit_nome:
        return DocumentCategory.HOMOLOGACAO.value
    if "adjudic" in sit_nome:
        return DocumentCategory.ADJUDICACAO.value
    if any(x in sit_nome for x in ("deserto", "fracass", "anulado", "revogad", "cancelad", "encerr")):
        return DocumentCategory.RESULTADO.value
    if item.get("temResultado") is True:
        return DocumentCategory.RESULTADO.value
    blob = json.dumps(item, ensure_ascii=False).lower()
    if "homolog" in blob:
        return DocumentCategory.HOMOLOGACAO.value
    if "adjudic" in blob:
        return DocumentCategory.ADJUDICACAO.value
    if any(k in blob for k in ("desclassif", "inabilit", "julgament", "vencedor")):
        return DocumentCategory.RESULTADO.value
    return None


def collect_pncp_session_packs(
    *,
    process_id: str,
    cnpj14: str,
    ano: int,
    sequencial: int,
    entity_id: str,
    raw_root: Path,
    adapter: PncpDocumentAdapter,
    run_id: str,
) -> list[DocumentRecord]:
    """Fetch atas/itens/historico for one process and preserve as public docs."""
    docs: list[DocumentRecord] = []
    # Atas
    url_atas = f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano}/{sequencial}/atas"
    code, payload, _err = adapter._get(url_atas)
    if code == 200 and payload:
        data = payload if isinstance(payload, list) else (payload.get("data") if isinstance(payload, dict) else None)
        if data:
            docs.append(
                _store_json_doc(
                    payload=data,
                    title=f"PNCP_Atas_{cnpj14}_{ano}_{sequencial}.json",
                    category=DocumentCategory.ATA_SESSAO.value,
                    process_id=process_id,
                    entity_id=entity_id,
                    source_id="pncp+atas",
                    portal_family="pncp",
                    download_url=url_atas,
                    raw_root=raw_root,
                    run_id=run_id,
                )
            )
    # Itens → outcome signals
    url_itens = f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano}/{sequencial}/itens"
    code, payload, _err = adapter._get(url_itens)
    if code == 200 and payload:
        items = payload if isinstance(payload, list) else (payload.get("data") if isinstance(payload, dict) else [])
        if isinstance(items, list) and items:
            outcomes = []
            cats: set[str] = set()
            for it in items:
                if not isinstance(it, dict):
                    continue
                cat = _classify_item_outcome(it)
                if cat:
                    cats.add(cat)
                    outcomes.append(it)
            if outcomes:
                # Prefer strongest session category present
                category = (
                    DocumentCategory.HOMOLOGACAO.value
                    if DocumentCategory.HOMOLOGACAO.value in cats
                    else (
                        DocumentCategory.ADJUDICACAO.value
                        if DocumentCategory.ADJUDICACAO.value in cats
                        else DocumentCategory.RESULTADO.value
                    )
                )
                docs.append(
                    _store_json_doc(
                        payload={"items_with_outcome": outcomes, "categories": sorted(cats)},
                        title=f"PNCP_Itens_Resultado_{cnpj14}_{ano}_{sequencial}.json",
                        category=category,
                        process_id=process_id,
                        entity_id=entity_id,
                        source_id="pncp+itens_outcome",
                        portal_family="pncp",
                        download_url=url_itens,
                        raw_root=raw_root,
                        run_id=run_id,
                    )
                )
            # Always store raw itens as planning/session context when multi-item
            docs.append(
                _store_json_doc(
                    payload=items,
                    title=f"PNCP_Itens_{cnpj14}_{ano}_{sequencial}.json",
                    category=DocumentCategory.ANEXO.value,
                    process_id=process_id,
                    entity_id=entity_id,
                    source_id="pncp+itens",
                    portal_family="pncp",
                    download_url=url_itens,
                    raw_root=raw_root,
                    run_id=run_id,
                )
            )
    # Histórico
    url_hist = f"{PNCP_API}/orgaos/{cnpj14}/compras/{ano}/{sequencial}/historico"
    code, payload, _err = adapter._get(url_hist)
    if code == 200 and payload:
        data = payload if isinstance(payload, list) else (payload.get("data") if isinstance(payload, dict) else None)
        if data:
            blob = json.dumps(data, ensure_ascii=False).lower()
            cat = DocumentCategory.RESULTADO.value
            if "homolog" in blob:
                cat = DocumentCategory.HOMOLOGACAO.value
            elif "adjudic" in blob:
                cat = DocumentCategory.ADJUDICACAO.value
            docs.append(
                _store_json_doc(
                    payload=data,
                    title=f"PNCP_Historico_{cnpj14}_{ano}_{sequencial}.json",
                    category=cat,
                    process_id=process_id,
                    entity_id=entity_id,
                    source_id="pncp+historico",
                    portal_family="pncp",
                    download_url=url_hist,
                    raw_root=raw_root,
                    run_id=run_id,
                )
            )
    return docs


def collect_origin_html_docs(
    *,
    seed_urls: list[str],
    process_id: str,
    entity_id: str,
    raw_root: Path,
    run_id: str,
    session: requests.Session,
    max_docs: int = 12,
) -> list[DocumentRecord]:
    """Crawl same-origin links looking for session/proposal/qualification docs."""
    docs: list[DocumentRecord] = []
    seen: set[str] = set()
    for seed in seed_urls:
        if not seed or not seed.startswith("http"):
            continue
        try:
            time.sleep(0.2)
            resp = session.get(seed, timeout=(8, 35), allow_redirects=True)
        except requests.RequestException:
            continue
        if resp.status_code != 200 or not resp.text:
            continue
        parser = _LinkParser()
        try:
            parser.feed(resp.text)
        except Exception:
            continue
        origin = f"{urlparse(seed).scheme}://{urlparse(seed).netloc}"
        candidates: list[tuple[str, str, str]] = []
        for href, text in parser.links:
            url = urljoin(seed, href)
            if not url.startswith(origin):
                continue
            label = f"{text} {href}"
            cat: str | None = None
            if SESSION_HINT.search(label):
                cat = classify_document_title(label)
                if cat in {"outro", "unknown_category"}:
                    cat = DocumentCategory.ATA_SESSAO.value
            elif WIN_HINT.search(label):
                cat = DocumentCategory.PROPOSTA_COMERCIAL.value
            elif QUAL_HINT.search(label):
                cat = DocumentCategory.HABILITACAO_JURIDICA.value
            else:
                continue
            candidates.append((url, label[:180], cat))
        for url, label, cat in candidates:
            if url in seen or len(docs) >= max_docs:
                break
            seen.add(url)
            try:
                time.sleep(0.15)
                r = session.get(url, timeout=(8, 40), allow_redirects=True)
            except requests.RequestException:
                continue
            if r.status_code != 200 or not r.content or len(r.content) < 64:
                continue
            mime = detect_mime(r.content, r.headers.get("Content-Type"))
            if mime == "text/html" and not any(
                x in (label + url).lower() for x in (".pdf", "download", "arquivo", "documento")
            ):
                # skip generic nav pages
                continue
            ext = "pdf" if mime == "application/pdf" else ("zip" if mime == "application/zip" else "bin")
            try:
                stored = store_blob(
                    r.content, raw_root=raw_root, extension=ext, declared_filename=label[:80]
                )
            except ValueError:
                continue
            docs.append(
                DocumentRecord(
                    internal_id=stored.sha256[:20],
                    sha256=stored.sha256,
                    size_bytes=stored.size_bytes,
                    download_url=url,
                    source_id="origin_html+session",
                    canonical_entity_id=entity_id,
                    portal_family="multi_source_html",
                    document_category=cat,
                    original_title=label,
                    original_filename=label[:120],
                    procurement_id=process_id,
                    source_page_url=seed,
                    declared_mime=r.headers.get("Content-Type"),
                    detected_mime=mime,
                    extension=ext,
                    run_id=run_id,
                    raw_uri=stored.raw_uri,
                    unchanged=stored.unchanged,
                )
            )
    return docs


def harvest_ciga_dom_session_acts(
    *,
    raw_root: Path,
    meta_root: Path,
    max_zips: int = 8,
) -> dict[str, Any]:
    """Scan recent CIGA DOM publication ZIPs for homologation/ata acts; preserve as docs."""
    try:
        from scripts.crawl.ciga_dom_publications import (
            get_package,
            get_package_resources,
            list_domsc_months,
        )
    except Exception as exc:  # pragma: no cover - optional dependency path
        return {"status": "unavailable", "error": str(exc), "documents": 0}

    started = _now()
    run_id = f"pd-ciga-dom-session-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    docs: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        months = list_domsc_months() or []
    except Exception as exc:
        return {"status": "list_failed", "error": str(exc), "documents": 0}

    # Prefer recent months (API may return package id strings or dicts)
    months = list(reversed(list(months)))[: max_zips * 2]
    zips_done = 0
    for pkg in months:
        if zips_done >= max_zips:
            break
        if isinstance(pkg, str):
            pkg_id = pkg
        elif isinstance(pkg, dict):
            pkg_id = str(pkg.get("name") or pkg.get("id") or "")
        else:
            pkg_id = str(pkg or "")
        if not pkg_id:
            continue
        try:
            resources = []
            try:
                resources = list(get_package_resources(pkg_id) or [])
            except Exception:
                resources = []
            if not resources:
                detail = get_package(pkg_id) or {}
                if isinstance(detail, dict):
                    resources = detail.get("resources") or []
                elif isinstance(detail, list):
                    resources = detail
        except Exception as exc:
            errors.append(f"{pkg_id}: {exc}")
            continue
        for res in resources:
            if zips_done >= max_zips:
                break
            if not isinstance(res, dict):
                continue
            fmt = str(res.get("format") or "").upper()
            url = res.get("url") or ""
            if "ZIP" not in fmt and not str(url).lower().endswith(".zip"):
                continue
            try:
                time.sleep(0.3)
                r = session.get(url, timeout=(10, 90))
                if r.status_code != 200 or not r.content.startswith(b"PK"):
                    continue
                stored_zip = store_blob(
                    r.content, raw_root=raw_root, extension="zip", declared_filename=Path(url).name
                )
                zips_done += 1
                # Extract JSON members only (autopublicacoes)
                import tempfile
                import zipfile
                from scripts.process_documents.storage import safe_extract_zip

                tmp = Path(tempfile.mkdtemp(prefix="pd-dom-"))
                try:
                    members = safe_extract_zip(stored_zip.path, tmp)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                for member in members:
                    if member.suffix.lower() not in {".json", ".jsonl"}:
                        continue
                    try:
                        text = member.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    # Find session-like publication objects
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        # maybe jsonl
                        for line in text.splitlines()[:2000]:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                row = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            _maybe_add_dom_act(row, docs, raw_root, run_id, url, stored_zip.sha256)
                        continue
                    rows = data if isinstance(data, list) else data.get("data") or data.get("result") or [data]
                    if isinstance(rows, dict):
                        rows = [rows]
                    for row in rows[:5000]:
                        if isinstance(row, dict):
                            _maybe_add_dom_act(row, docs, raw_root, run_id, url, stored_zip.sha256)
                import shutil

                shutil.rmtree(tmp, ignore_errors=True)
            except Exception as exc:
                errors.append(f"{url}: {exc}")

    finished = _now()
    run_dir = meta_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "run_id": run_id,
        "canonical_entity_id": "multi:ciga_dom_session",
        "source_id": "ciga_dom+session_acts",
        "portal_family": "ciga_dom",
        "capabilities_requested": ["session_and_judgment_documents"],
        "capabilities_proven": ["session_and_judgment_documents"] if docs else [],
        "status": DocumentRunStatus.SUCCESS_NONZERO.value if docs else DocumentRunStatus.SUCCESS_ZERO.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "query_parameters": {"max_zips": max_zips, "mode": "session_act_filter"},
        "documents_discovered": len(docs),
        "documents_downloaded": len(docs),
        "errors": errors[:40],
        "documents": docs,
        "success_zero_justification": None
        if docs
        else "No homologation/ata acts found in sampled CIGA DOM ZIPs",
    }
    write_json(run_dir / "result.json", result)
    with (meta_root / "run-index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "source_id": "ciga_dom+session_acts",
                    "status": result["status"],
                    "documents_downloaded": len(docs),
                    "finished_at": finished.isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return {"run_id": run_id, "documents": len(docs), "zips": zips_done, "errors": errors[:10]}


def _maybe_add_dom_act(
    row: dict[str, Any],
    docs: list[dict[str, Any]],
    raw_root: Path,
    run_id: str,
    source_url: str,
    zip_sha: str,
) -> None:
    text = " ".join(
        str(row.get(k) or "")
        for k in (
            "titulo",
            "title",
            "ementa",
            "resumo",
            "categoria",
            "tipo",
            "assunto",
            "conteudo",
            "texto",
        )
    )
    low = text.lower()
    if not any(
        k in low
        for k in (
            "homolog",
            "adjudic",
            "ata de",
            "resultado",
            "julgamento",
            "habilita",
            "inabilit",
            "desclassif",
            "recurso",
        )
    ):
        return
    cat = classify_document_title(text)
    if cat in {"outro", "unknown_category"}:
        if "homolog" in low:
            cat = DocumentCategory.HOMOLOGACAO.value
        elif "adjudic" in low:
            cat = DocumentCategory.ADJUDICACAO.value
        elif "ata" in low:
            cat = DocumentCategory.ATA_SESSAO.value
        elif "habilit" in low:
            cat = DocumentCategory.HABILITACAO_JURIDICA.value
        else:
            cat = DocumentCategory.RESULTADO.value
    mun = str(row.get("municipio") or row.get("ente") or row.get("orgao") or "domsc")
    pid = f"ciga-dom:{mun}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
    try:
        rec = _store_json_doc(
            payload=row,
            title=f"DOM_{cat}_{pid[-12:]}.json",
            category=cat,
            process_id=pid,
            entity_id=f"ciga-dom:{mun}",
            source_id="ciga_dom+session_acts",
            portal_family="ciga_dom",
            download_url=source_url + f"#zip={zip_sha[:12]}",
            raw_root=raw_root,
            run_id=run_id,
        )
        docs.append(rec.to_dict())
    except ValueError:
        return


def run_multi_source_session_campaign(
    *,
    max_processes: int = 150,
    include_ciga_dom: bool = True,
    include_origin_html: bool = True,
) -> dict[str, Any]:
    """Live multi-source pass for processes missing session/win/qual packs."""
    raw, meta = ensure_roots()
    started = _now()
    run_id = f"pd-multi-session-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    adapter = PncpDocumentAdapter(raw_root=raw, meta_root=meta, request_delay=0.12)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    SESSION = {c.value for c in SESSION_JUDGMENT_CATEGORIES}
    WIN = {c.value for c in WINNING_PROPOSAL_CATEGORIES}
    QUAL = {c.value for c in QUALIFICATION_CATEGORIES}

    # Index current process coverage
    by: dict[str, dict[str, Any]] = {}
    from scripts.process_documents.classify_docs import classify_document_record

    for result_path in (meta / "runs").glob("*/result.json"):
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for doc in data.get("documents") or []:
            pid = str(doc.get("procurement_id") or "")
            if not pid:
                continue
            row = by.setdefault(
                pid,
                {"cats": set(), "entity": doc.get("canonical_entity_id"), "origins": set()},
            )
            row["cats"].add(classify_document_record(doc))
            if doc.get("canonical_entity_id"):
                row["entity"] = doc.get("canonical_entity_id")
            for u in (doc.get("source_page_url"), doc.get("download_url")):
                if u and "pncp.gov.br" not in str(u):
                    row["origins"].add(str(u))

    targets = []
    for pid, info in by.items():
        m = _PNCP_PID.match(pid)
        if not m:
            continue
        missing_session = not (info["cats"] & SESSION)
        missing_win = not (info["cats"] & WIN)
        missing_qual = not (info["cats"] & QUAL)
        if not (missing_session or missing_win or missing_qual):
            continue
        targets.append(
            {
                "process_id": pid,
                "cnpj": m.group(1),
                "ano": int(m.group(4)),
                "seq": int(m.group(3)),
                "entity": info.get("entity") or f"pncp-org:{m.group(1)}",
                "origins": list(info.get("origins") or [])[:3],
                "need_session": missing_session,
                "need_win": missing_win,
                "need_qual": missing_qual,
            }
        )
    # Prefer older years (more likely homologated)
    targets.sort(key=lambda t: (t["ano"], t["seq"]))
    targets = targets[:max_processes]

    all_docs: list[dict[str, Any]] = []
    stats = {
        "targets": len(targets),
        "pncp_session_docs": 0,
        "html_docs": 0,
        "processes_touched": 0,
        "errors": [],
    }
    for i, t in enumerate(targets):
        try:
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
            stats["pncp_session_docs"] += len(docs)
            if include_origin_html and t["origins"]:
                html_docs = collect_origin_html_docs(
                    seed_urls=t["origins"],
                    process_id=t["process_id"],
                    entity_id=t["entity"],
                    raw_root=raw,
                    run_id=run_id,
                    session=session,
                )
                docs.extend(html_docs)
                stats["html_docs"] += len(html_docs)
            if docs:
                stats["processes_touched"] += 1
                all_docs.extend(d.to_dict() for d in docs)
        except Exception as exc:
            stats["errors"].append(f"{t['process_id']}: {exc}")
        if i and i % 25 == 0:
            stats["progress"] = i

    ciga_stats: dict[str, Any] = {}
    if include_ciga_dom:
        try:
            ciga_stats = harvest_ciga_dom_session_acts(raw_root=raw, meta_root=meta, max_zips=6)
            stats["ciga_dom"] = ciga_stats
        except Exception as exc:
            stats["ciga_dom_error"] = str(exc)

    finished = _now()
    result = {
        "run_id": run_id,
        "canonical_entity_id": "multi:session_campaign",
        "source_id": "multi_source_session",
        "portal_family": "multi_source",
        "capabilities_requested": [
            "session_and_judgment_documents",
            "bidder_submission_documents",
        ],
        "capabilities_proven": (
            ["session_and_judgment_documents"] if stats["pncp_session_docs"] or stats["html_docs"] else []
        ),
        "status": DocumentRunStatus.SUCCESS_NONZERO.value
        if all_docs
        else DocumentRunStatus.SUCCESS_ZERO.value,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "query_parameters": {"max_processes": max_processes, "include_ciga_dom": include_ciga_dom},
        "documents_discovered": len(all_docs),
        "documents_downloaded": len(all_docs),
        "processes_seen": stats["processes_touched"],
        "errors": stats["errors"][:40],
        "documents": all_docs,
        "stats": stats,
    }
    run_dir = meta / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "result.json", result)
    with (meta / "run-index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "source_id": "multi_source_session",
                    "status": result["status"],
                    "documents_downloaded": len(all_docs),
                    "processes_seen": stats["processes_touched"],
                    "finished_at": finished.isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    write_json(meta / "multi-source-session-summary.json", {"run_id": run_id, **stats, "docs": len(all_docs)})
    return {"run_id": run_id, **stats, "documents": len(all_docs)}
