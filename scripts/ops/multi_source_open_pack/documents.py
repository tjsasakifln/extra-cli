"""Inventário e validação de documentos oficiais para shortlist."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from scripts.ops.multi_source_open_pack.models import CanonicalProcess, ProcessDocument
from scripts.ops.multi_source_open_pack.pdf_parse import (
    extract_pdf_text,
    is_edital_like_title,
    is_pdf_bytes,
)
from scripts.ops.multi_source_open_pack.textutil import iso_z

USER_AGENT = "extra-cli-ms-open-pack/2.0 (+public official docs only)"


@dataclass
class FetchResult:
    ok: bool
    url_original: str
    url_final: str = ""
    http_status: int | None = None
    content_type: str = ""
    sha256: str = ""
    size: int = 0
    error: str = ""
    body: bytes = b""
    fetched_at: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_url(
    url: str,
    *,
    timeout: float = 25.0,
    max_bytes: int = 8_000_000,
    session: Any | None = None,
) -> FetchResult:
    """HTTP GET with redirect follow; returns original + final URL and hash."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return FetchResult(ok=False, url_original=url or "", error="url_invalida")
    low = url.lower()
    # SSRF denylist includes all-interfaces bind addresses by design.
    for bad in ("localhost", "127.0.0.1", "0.0.0.0", "ec-prod", "/opt/extra"):  # noqa: S104
        if bad in low:
            return FetchResult(ok=False, url_original=url, error=f"url_proibida:{bad}")

    try:
        import requests
    except ImportError:
        # fallback urllib
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        try:
            req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")  # noqa: S310
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    data = data[:max_bytes]
                final = resp.geturl() or url
                status = getattr(resp, "status", None) or resp.getcode()
                ctype = resp.headers.get("Content-Type", "")
                return FetchResult(
                    ok=200 <= int(status or 0) < 400,
                    url_original=url,
                    url_final=final,
                    http_status=int(status or 0),
                    content_type=ctype,
                    sha256=_sha256(data),
                    size=len(data),
                    body=data,
                    fetched_at=iso_z(),
                )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return FetchResult(ok=False, url_original=url, error=str(exc)[:300], fetched_at=iso_z())

    sess = session
    own = False
    if sess is None:
        sess = requests.Session()
        own = True
    try:
        resp = sess.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            allow_redirects=True,
            stream=True,
        )
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
        data = b"".join(chunks)[:max_bytes]
        final = str(resp.url or url)
        ok = 200 <= resp.status_code < 400 and len(data) > 0
        return FetchResult(
            ok=ok,
            url_original=url,
            url_final=final,
            http_status=resp.status_code,
            content_type=resp.headers.get("Content-Type", ""),
            sha256=_sha256(data) if data else "",
            size=len(data),
            body=data,
            error="" if ok else f"HTTP {resp.status_code} or empty body",
            fetched_at=iso_z(),
        )
    except Exception as exc:  # noqa: BLE001 — surface as inventory failure
        return FetchResult(ok=False, url_original=url, error=str(exc)[:300], fetched_at=iso_z())
    finally:
        if own:
            sess.close()


def is_specific_official_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    ul = url.lower().split("?", 1)[0].rstrip("/")
    if any(x in ul for x in ("google.com", "/pesquisa", "search?q=")):
        return False
    # PNCP listing / home — not process-specific
    if ul.endswith(
        (
            "pncp.gov.br",
            "pncp.gov.br/app",
            "pncp.gov.br/app/editais",
            "www.pncp.gov.br",
            "www.pncp.gov.br/app",
            "www.pncp.gov.br/app/editais",
        )
    ):
        return False
    if re.search(r"pncp\.gov\.br/app/editais/\d{14}/\d{4}/\d+", ul):
        return True
    path = urlparse(ul).path or ""
    # require deep path (process page), not mere /app/editais
    return path.count("/") >= 3 and len(path) > 12


def parse_pncp_ids_from_url(url: str) -> tuple[str, str, str] | None:
    m = re.search(r"pncp\.gov\.br/app/editais/(\d{14})/(\d{4})/(\d+)", url or "", re.I)
    if not m:
        return None
    return m.group(1), m.group(2), str(int(m.group(3)))


def list_pcp_documentos(process_url: str, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    """List documents from Portal de Compras Públicas process API."""
    m = re.search(r"portaldecompraspublicas\.com\.br/processos/.+-(\d+)(?:\?|$)", process_url or "", re.I)
    if not m:
        m = re.search(r"/(\d{5,})(?:\?|$)", process_url or "")
    if not m:
        return []
    codigo = m.group(1)
    api = f"https://compras.api.portaldecompraspublicas.com.br/v2/licitacao/{codigo}/documentos/processo"
    try:
        import requests

        r = requests.get(
            api,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            title = str(it.get("nome") or it.get("tituloDocumento") or "documento")
            uri = str(it.get("url") or "")
            tipo = str(it.get("tipo") or "anexo")
            if uri:
                out.append({"title": title, "url": uri, "tipo": tipo, "raw": it})
        return out
    except Exception:
        return []


def list_pncp_arquivos(
    cnpj: str,
    ano: str,
    sequencial: str,
    *,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """List official PNCP arquivos for a compra (public API)."""
    try:
        import requests
    except ImportError:
        return []
    # consulta v1 pattern used in repo
    urls = [
        f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos",
        f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos",
    ]
    out: list[dict[str, Any]] = []
    for api in urls:
        try:
            r = requests.get(
                api,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("data") or data.get("items") or []
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                title = str(it.get("titulo") or it.get("nome") or it.get("title") or "arquivo")
                uri = (
                    it.get("url")
                    or it.get("uri")
                    or it.get("link")
                    or it.get("urlArquivo")
                    or ""
                )
                if uri and not str(uri).startswith("http"):
                    uri = urljoin("https://pncp.gov.br/", str(uri))
                out.append(
                    {
                        "title": title,
                        "url": str(uri),
                        "tipo": str(it.get("tipoDocumentoNome") or it.get("type") or "anexo"),
                        "raw": it,
                    }
                )
            if out:
                return out
        except Exception:  # noqa: BLE001, S112
            # Try next PNCP endpoint variant; failures are non-fatal per-candidate.
            continue
    return out


def inventariar_processo(
    proc: CanonicalProcess,
    *,
    cache_dir: Path | None = None,
    download_arquivos: bool = True,
    max_arquivos: int = 8,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Validate official page + optional PNCP file list; hash versioned inventory."""
    docs: list[ProcessDocument] = []
    evidence: dict[str, Any] = {
        "process_id": proc.process_id,
        "attempts": [],
        "docs_complete": False,
        "page_validated": False,
        "blocked_reason": "",
    }

    candidates: list[str] = []
    for u in [proc.url_oficial, *proc.urls_all]:
        if u and is_specific_official_url(u) and u not in candidates:
            candidates.append(u)
    # Prefer PNCP process URLs first (API arquivos + more stable for inventory)
    candidates.sort(key=lambda u: (0 if "pncp.gov.br/app/editais/" in u.lower() else 1, u))

    url = candidates[0] if candidates else (proc.url_oficial or "")
    if not url or not is_specific_official_url(url):
        evidence["blocked_reason"] = "sem_pagina_oficial_especifica"
        proc.official_page_validated = False
        proc.docs_inventory_status = "blocked_missing_official_page"
        proc.documents = [
            ProcessDocument(
                doc_type="pagina_oficial",
                title="ausente/genérica",
                url=url or "",
                fonte=proc.fontes[0] if proc.fontes else "",
                download_status="not_attempted",
                parse_status="blocked",
            )
        ]
        return evidence

    page = fetch_url(url, timeout=timeout)
    # Retry alternate candidates if primary fails
    if not page.ok and len(candidates) > 1:
        for alt in candidates[1:]:
            alt_page = fetch_url(alt, timeout=timeout)
            evidence["attempts"].append(
                {
                    "kind": "pagina_oficial_retry",
                    "url_original": alt_page.url_original,
                    "url_final": alt_page.url_final,
                    "http_status": alt_page.http_status,
                    "ok": alt_page.ok,
                    "sha256": alt_page.sha256,
                    "size": alt_page.size,
                    "error": alt_page.error,
                    "fetched_at": alt_page.fetched_at,
                }
            )
            if alt_page.ok:
                page = alt_page
                url = alt
                proc.url_oficial = alt
                break
    evidence["attempts"].append(
        {
            "kind": "pagina_oficial",
            "url_original": page.url_original,
            "url_final": page.url_final,
            "http_status": page.http_status,
            "ok": page.ok,
            "sha256": page.sha256,
            "size": page.size,
            "error": page.error,
            "fetched_at": page.fetched_at,
        }
    )
    # Always recompute validation from live fetch (do not keep pre-inventory True)
    proc.official_page_validated = bool(page.ok)
    evidence["page_validated"] = bool(page.ok)
    if page.ok:
        # store cache optional
        if cache_dir is not None and page.body:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{proc.process_id}_page.bin").write_bytes(page.body)
            (cache_dir / f"{proc.process_id}_page.meta.json").write_text(
                json.dumps(evidence["attempts"][-1], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        docs.append(
            ProcessDocument(
                doc_type="pagina_oficial",
                title="Página oficial do processo",
                url=page.url_final or page.url_original,
                fonte=proc.fontes[0] if proc.fontes else "oficial",
                published_at=page.fetched_at,
                content_hash=page.sha256,
                download_status="downloaded",
                parse_status="bytes_hashed",
                version=1,
            )
        )
        # keep text snippet for analysis
        evidence["page_text_sample"] = _html_to_text(page.body)[:8000]
        evidence["url_final"] = page.url_final
    else:
        evidence["blocked_reason"] = f"falha_fetch_pagina:{page.error or page.http_status}"
        docs.append(
            ProcessDocument(
                doc_type="pagina_oficial",
                title="Página oficial (fetch falhou)",
                url=url,
                fonte=proc.fontes[0] if proc.fontes else "oficial",
                download_status="failed",
                parse_status="error",
            )
        )

    extracted_texts: list[str] = []
    if evidence.get("page_text_sample"):
        extracted_texts.append(str(evidence["page_text_sample"]))

    def _ingest_file(
        *,
        title: str,
        fr: FetchResult,
        fonte: str,
        doc_type: str,
        kind: str,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "title": title,
            "ok": fr.ok,
            "sha256": fr.sha256,
            "size": fr.size,
            "parsed": False,
            "edital_like": is_edital_like_title(title) or is_pdf_bytes(fr.body),
        }
        evidence["attempts"].append(
            {
                "kind": kind,
                "title": title,
                "url_original": fr.url_original,
                "url_final": fr.url_final,
                "http_status": fr.http_status,
                "ok": fr.ok,
                "sha256": fr.sha256,
                "size": fr.size,
                "error": fr.error,
                "fetched_at": fr.fetched_at,
            }
        )
        parse_status = "error"
        if fr.ok and fr.body:
            if is_pdf_bytes(fr.body) or "pdf" in (fr.content_type or "").lower():
                parsed = extract_pdf_text(fr.body)
                meta["parse"] = parsed.to_dict()
                if parsed.ok and parsed.text.strip():
                    parse_status = "text_extracted"
                    meta["parsed"] = True
                    extracted_texts.append(parsed.text)
                    if cache_dir is not None:
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", title)[:80]
                        (cache_dir / f"{proc.process_id}_{safe}.pdf").write_bytes(fr.body[:4_000_000])
                else:
                    parse_status = "bytes_hashed_unreadable" if fr.sha256 else "error"
                    meta["parsed"] = False
            else:
                # HTML/other attachment
                txt = _html_to_text(fr.body)
                if len(txt) > 200:
                    parse_status = "text_extracted"
                    meta["parsed"] = True
                    extracted_texts.append(txt[:40_000])
                else:
                    parse_status = "bytes_hashed"
        docs.append(
            ProcessDocument(
                doc_type=doc_type,
                title=title,
                url=fr.url_final or fr.url_original,
                fonte=fonte,
                published_at=fr.fetched_at,
                content_hash=fr.sha256,
                download_status="downloaded" if fr.ok else "failed",
                parse_status=parse_status,
                version=1,
            )
        )
        return meta

    # PNCP arquivos
    pncp_ids = parse_pncp_ids_from_url(page.url_final if page.ok else url)
    if not pncp_ids:
        pncp_ids = parse_pncp_ids_from_url(url)
        for c in candidates:
            pncp_ids = pncp_ids or parse_pncp_ids_from_url(c)
    arquivos_meta: list[dict[str, Any]] = []
    if pncp_ids and download_arquivos:
        cnpj, ano, seq = pncp_ids
        listed = list_pncp_arquivos(cnpj, ano, seq, timeout=timeout)
        # prioritize edital-like titles
        listed_sorted = sorted(
            listed,
            key=lambda it: (0 if is_edital_like_title(str(it.get("title") or "")) else 1),
        )
        for i, item in enumerate(listed_sorted[:max_arquivos]):
            aurl = item.get("url") or ""
            title = str(item.get("title") or f"arquivo_{i}")
            if not aurl:
                docs.append(
                    ProcessDocument(
                        doc_type=str(item.get("tipo") or "anexo"),
                        title=title,
                        url="",
                        fonte="pncp_api",
                        download_status="listed_no_url",
                        parse_status="not_parsed",
                    )
                )
                continue
            fr = fetch_url(aurl, timeout=timeout, max_bytes=6_000_000)
            arquivos_meta.append(
                _ingest_file(
                    title=title,
                    fr=fr,
                    fonte="pncp_api",
                    doc_type=str(item.get("tipo") or "anexo"),
                    kind="arquivo_pncp",
                )
            )
        evidence["pncp_arquivos_listed"] = len(listed)
        evidence["pncp_arquivos_downloaded"] = sum(1 for a in arquivos_meta if a.get("ok"))
        evidence["pncp_arquivos_parsed"] = sum(1 for a in arquivos_meta if a.get("parsed"))

    # Portal de Compras Públicas document API (JSON list of EDITAL.pdf etc.)
    if download_arquivos and "portaldecompraspublicas.com.br" in (url or "").lower():
        pcp_docs = list_pcp_documentos(page.url_final or url, timeout=timeout)
        evidence["pcp_docs_listed"] = len(pcp_docs)
        for i, item in enumerate(
            sorted(pcp_docs, key=lambda it: (0 if is_edital_like_title(str(it.get("title") or "")) else 1))[
                :max_arquivos
            ]
        ):
            aurl = item.get("url") or ""
            if not aurl or any(d.url == aurl for d in docs):
                continue
            fr = fetch_url(aurl, timeout=timeout, max_bytes=6_000_000)
            arquivos_meta.append(
                _ingest_file(
                    title=str(item.get("title") or f"pcp_{i}"),
                    fr=fr,
                    fonte="pcp_api",
                    doc_type=str(item.get("tipo") or "anexo"),
                    kind="arquivo_pcp",
                )
            )
        evidence["pcp_docs_downloaded"] = sum(
            1 for a in evidence["attempts"] if a.get("kind") == "arquivo_pcp" and a.get("ok")
        )

    # HTML-discovered PDF/doc links (portais não-PNCP ou complementares)
    if page.ok and page.body and download_arquivos:
        for i, link in enumerate(_discover_doc_links(page.body, page.url_final or url)[:6]):
            if any(d.url == link["url"] for d in docs):
                continue
            fr = fetch_url(link["url"], timeout=timeout, max_bytes=6_000_000)
            arquivos_meta.append(
                _ingest_file(
                    title=link.get("title") or f"anexo_html_{i}",
                    fr=fr,
                    fonte="html_discovery",
                    doc_type=link.get("tipo") or "anexo",
                    kind="arquivo_html",
                )
            )
        evidence["html_docs_discovered"] = sum(
            1 for a in evidence["attempts"] if a.get("kind") == "arquivo_html"
        )

    # secondary observation URLs (not counted as complete alone)
    for u in proc.urls_all:
        if u and u != url and is_specific_official_url(u):
            if any(d.url == u for d in docs):
                continue
            docs.append(
                ProcessDocument(
                    doc_type="observacao_fonte",
                    title="URL de fonte consolidada",
                    url=u,
                    fonte="multi",
                    download_status="linked_not_downloaded",
                    parse_status="not_parsed",
                )
            )

    proc.documents = docs
    downloaded = [d for d in docs if d.download_status == "downloaded" and d.content_hash]
    parsed_docs = [d for d in docs if d.parse_status == "text_extracted"]
    edital_docs = [
        d
        for d in docs
        if d.download_status == "downloaded"
        and (
            is_edital_like_title(d.title)
            or d.doc_type.lower() in {"edital", "anexo", "pdf"}
            or d.parse_status == "text_extracted"
        )
        and d.doc_type != "pagina_oficial"
    ]
    arquivos_ok = int(evidence.get("pncp_arquivos_downloaded") or 0) + int(
        evidence.get("pcp_docs_downloaded") or 0
    ) + sum(
        1
        for a in evidence["attempts"]
        if a.get("kind") == "arquivo_html" and a.get("ok")
    )
    evidence["edital_docs_downloaded"] = len(edital_docs)
    evidence["parsed_docs"] = len(parsed_docs)
    evidence["extracted_text_chars"] = sum(len(t) for t in extracted_texts)

    # Shortlist-complete requires official evidence + at least one non-HTML-only
    # process document (edital/TR/anexo) downloaded and preferably parsed.
    has_official_evidence = evidence["page_validated"] or arquivos_ok > 0
    has_process_document = len(edital_docs) > 0
    has_parse = len(parsed_docs) > 0 or any(
        len(t) > 400 for t in extracted_texts
    )

    if has_official_evidence and has_process_document and has_parse:
        if arquivos_ok > 0 and evidence.get("pncp_arquivos_parsed", 0) > 0:
            proc.docs_inventory_status = "complete"
        elif arquivos_ok > 0:
            proc.docs_inventory_status = "complete_pncp_arquivos"
        else:
            proc.docs_inventory_status = "complete_with_attachments"
        if not evidence["page_validated"] and arquivos_ok > 0:
            proc.official_page_validated = True
            evidence["page_validated"] = True
            evidence["note"] = (
                "HTML da página PNCP indisponível; documentos oficiais via API/anexos"
            )
        evidence["docs_complete"] = True
        evidence["blocked_reason"] = ""
    elif has_official_evidence and has_process_document:
        # downloaded but unreadable (scanned) — still stronger than page-only
        proc.docs_inventory_status = "partial_docs_unparsed"
        evidence["docs_complete"] = False
        evidence["blocked_reason"] = "documentos_baixados_sem_texto_extraivel"
    elif evidence["page_validated"]:
        proc.docs_inventory_status = "partial_page_only"
        evidence["docs_complete"] = False
        evidence["blocked_reason"] = "apenas_html_sem_edital_anexo"
    else:
        proc.docs_inventory_status = "blocked_fetch_failed"
        evidence["docs_complete"] = False
        if not evidence.get("blocked_reason"):
            evidence["blocked_reason"] = "blocked_fetch_failed"

    # Stash combined text for edital analysis
    evidence["combined_text"] = "\n\n".join(extracted_texts)[:100_000]
    evidence["page_text_sample"] = evidence.get("combined_text", "")[:12_000]
    proc._page_text_sample = evidence["page_text_sample"]  # type: ignore[attr-defined]
    proc._combined_doc_text = evidence.get("combined_text", "")  # type: ignore[attr-defined]

    evidence["document_count"] = len(docs)
    evidence["hashed_count"] = len(downloaded)
    return evidence


def _discover_doc_links(html: bytes, base_url: str) -> list[dict[str, str]]:
    """Find PDF/doc links in HTML for attachment download."""
    try:
        text = html.decode("utf-8", errors="replace")
    except Exception:
        text = html.decode("latin-1", errors="replace")
    hrefs = re.findall(
        r'href=["\']([^"\']+\.(?:pdf|docx?|xlsx?|zip))(?:\?[^"\']*)?["\']',
        text,
        flags=re.I,
    )
    hrefs += re.findall(
        r'href=["\']([^"\']*(?:arquivo|download|anexo|edital)[^"\']*)["\']',
        text,
        flags=re.I,
    )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for h in hrefs:
        full = urljoin(base_url, h)
        if not full.startswith("http") or full in seen:
            continue
        if any(x in full.lower() for x in ("javascript:", "mailto:", "#")):
            continue
        seen.add(full)
        title = full.rsplit("/", 1)[-1][:120]
        tipo = "pdf" if full.lower().endswith(".pdf") else "anexo"
        out.append({"url": full, "title": title, "tipo": tipo})
    return out


def _html_to_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = data.decode("latin-1", errors="replace")
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def inventariar_shortlist(
    processes: list[CanonicalProcess],
    *,
    cache_dir: Path | None = None,
    enabled: bool = True,
    max_processes: int = 25,
) -> dict[str, Any]:
    """Run inventory on shortlist processes (mutates in place)."""
    summary: dict[str, Any] = {
        "enabled": enabled,
        "attempted": 0,
        "page_validated": 0,
        "complete": 0,
        "blocked": 0,
        "by_process": {},
    }
    if not enabled:
        for p in processes:
            if p.docs_inventory_status in {"pending", "urls_linked_only"}:
                p.docs_inventory_status = "review_bloqueado_inventario_desligado"
                if p.decision:
                    p.decision.inclusion_reason = "review_bloqueado_sem_inventario_documental"
                    p.decision.pending = sorted(
                        set(p.decision.pending + ["inventario_documental_obrigatorio"])
                    )
        return summary

    for p in processes[:max_processes]:
        summary["attempted"] += 1
        ev = inventariar_processo(p, cache_dir=cache_dir)
        summary["by_process"][p.process_id] = {
            k: v for k, v in ev.items() if k != "page_text_sample"
        }
        # stash text for analysis on process object via attributes bag
        p._page_text_sample = ev.get("page_text_sample", "")  # type: ignore[attr-defined]
        p._combined_doc_text = ev.get("combined_text", "")  # type: ignore[attr-defined]
        if ev.get("page_validated"):
            summary["page_validated"] += 1
        if ev.get("docs_complete"):
            summary["complete"] += 1
        else:
            summary["blocked"] += 1
            if p.decision:
                p.decision.inclusion_reason = (
                    f"review_bloqueado:{ev.get('blocked_reason') or p.docs_inventory_status}"
                )
                p.decision.pending = sorted(
                    set(
                        p.decision.pending
                        + ["completar_inventario_documental", "analise_edital_profunda"]
                    )
                )
                p.decision.next_action = (
                    f"Inventário documental: {p.docs_inventory_status}. "
                    f"{p.decision.next_action}"
                )
    return summary
