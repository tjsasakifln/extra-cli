"""Document verification helpers (public PNCP / local harvest).

Document pipeline states:
  DOCUMENT_URL_LOCATED → DOCUMENT_DOWNLOADED → TEXT_EXTRACTED →
  CLAUSE_LOCATED → CLAUSE_HUMAN_CONFIRMED
  | DOCUMENT_UNAVAILABLE | DOCUMENT_PARSE_FAILED

Binary PDF located ≠ text extracted ≠ documentary gate pass.
Does not invent clauses. Absence of a document is NOT proof of non-existence.
"""

from __future__ import annotations

# Public HTTPS only; schemes restricted by caller URL builders.
# ruff: noqa: S310
import hashlib
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any  # noqa: TC003

from scripts.commercial.reajuste_14133 import (
    DOC_CLAUSE_LOCATED,
    DOC_DOWNLOADED,
    DOC_PARSE_FAILED,
    DOC_TEXT_EXTRACTED,
    DOC_UNAVAILABLE,
    DOC_URL_LOCATED,
)

INDEX_PATTERNS = (
    r"\b(INCC(?:-?DI|-?M)?)\b",
    r"\b(IPCA)\b",
    r"\b(IGP-?M)\b",
    r"\b(SINAPI)\b",
    r"\b(SICRO)\b",
    r"\b(IVAR)\b",
    r"\b(ICC)\b",
    r"\b(INPC)\b",
    r"\b(cesta\s+de\s+[ií]ndices?)\b",
)

REAJUSTE_CLAUSE = re.compile(
    r"reajust(?:e|amento)|repactua[cç]|reequil[ií]brio|atualiza[cç][aã]o\s+monet[aá]ria",
    re.I,
)
DATA_BASE_PAT = re.compile(
    r"data[- ]base|data\s+do\s+or[cç]amento\s+estimado|or[cç]amento\s+estimado|"
    r"m[eê]s\s+base\s+do\s+or[cç]amento",
    re.I,
)
APOSTILA_PAT = re.compile(r"\bapostila\b|termo\s+de\s+apostilamento", re.I)
REGIME_14133_PAT = re.compile(r"lei\s*n?[ºo°.]?\s*14[\./]?133", re.I)
REGIME_8666_PAT = re.compile(r"lei\s*n?[ºo°.]?\s*8[\./]?666", re.I)
REGIME_RDC_PAT = re.compile(r"\brdc\b|regime\s+diferenciado\s+de\s+contrata", re.I)


@dataclass
class Evidence:
    doc_type: str
    orgao_emissor: str | None
    identificador_oficial: str | None
    url_or_location: str | None
    consulted_at: str
    excerpt: str
    content_hash: str | None
    extraction_method: str
    confidence: str
    field_found: str
    page: str | None = None
    section: str | None = None
    human_confirmed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentScanResult:
    evidences: list[Evidence] = field(default_factory=list)
    index_candidates: list[str] = field(default_factory=list)
    # Indices only when semantically linked to reajuste clause window
    index_in_clause: list[str] = field(default_factory=list)
    index_outside_clause_only: list[str] = field(default_factory=list)
    regime_14133_mention: bool = False
    regime_8666_mention: bool = False
    regime_rdc_mention: bool = False
    regime_conflict: bool = False
    reajuste_clause_mention: bool = False
    data_base_mention: bool = False
    apostila_mention: bool = False
    already_adjusted_hint: bool = False
    # True only when TEXT was extracted from an official document (not binary PDF, not mere URL)
    docs_accessible: bool = False
    text_extracted: bool = False
    pdf_binary_located: bool = False
    pipeline_state: str = DOC_UNAVAILABLE
    network_error: bool = False
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidences"] = [e.as_dict() if isinstance(e, Evidence) else e for e in self.evidences]
        return d


def pncp_contract_url(contrato_id: str | None, orgao_cnpj: str | None = None) -> str | None:
    cid = (contrato_id or "").strip()
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", cid)
    if m:
        cnpj, seq, ano = m.group(1), str(int(m.group(2))), m.group(3)
        return f"https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq}"
    digits = re.sub(r"\D", "", orgao_cnpj or "")
    if len(digits) == 14:
        return f"https://pncp.gov.br/app/contratos/{digits}"
    return None


def pncp_api_contract_url(contrato_id: str | None) -> str | None:
    """Best-effort PNCP Consulta API path for structured contract metadata."""
    cid = (contrato_id or "").strip()
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", cid)
    if not m:
        return None
    cnpj, seq, ano = m.group(1), str(int(m.group(2))), m.group(3)
    return (
        f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/contratos/{ano}/{seq}"
    )


def _indices_in_window(text: str, start: int, end: int) -> list[str]:
    window = text[max(0, start) : min(len(text), end)]
    found: list[str] = []
    for pat in INDEX_PATTERNS:
        for m in re.finditer(pat, window, re.I):
            idx = m.group(1).upper().replace(" ", "_")
            if idx not in found:
                found.append(idx)
    return found


def extract_from_text(
    text: str,
    *,
    doc_type: str,
    url: str | None,
    orgao: str | None = None,
    official_id: str | None = None,
    method: str = "regex_text",
    is_binary_placeholder: bool = False,
) -> DocumentScanResult:
    """Extract reajuste-related signals from a text blob.

    Binary PDF placeholders must set ``is_binary_placeholder=True`` so
    ``docs_accessible`` stays False.
    """
    res = DocumentScanResult()
    if not text or not text.strip():
        res.limitations.append("empty_text")
        res.pipeline_state = DOC_UNAVAILABLE
        return res

    if is_binary_placeholder or text.startswith("[PDF_BINARY"):
        res.pdf_binary_located = True
        res.docs_accessible = False
        res.text_extracted = False
        res.pipeline_state = DOC_DOWNLOADED
        res.limitations.append(
            "PDF binário localizado sem extração de texto — não satisfaz gate documental."
        )
        h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                excerpt=text[:200],
                content_hash=h,
                extraction_method=method,
                confidence="low",
                field_found="pdf_binary_only",
            )
        )
        return res

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    res.docs_accessible = True
    res.text_extracted = True
    res.pipeline_state = DOC_TEXT_EXTRACTED

    m_reg = REGIME_14133_PAT.search(text)
    if m_reg:
        res.regime_14133_mention = True
        start = max(0, m_reg.start() - 60)
        end = min(len(text), m_reg.end() + 60)
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=now,
                excerpt=text[start:end].strip(),
                content_hash=h,
                extraction_method=method,
                confidence="medium",
                field_found="regime_legal_14133",
            )
        )
    if REGIME_8666_PAT.search(text):
        res.regime_8666_mention = True
    if REGIME_RDC_PAT.search(text):
        res.regime_rdc_mention = True
    if res.regime_14133_mention and (res.regime_8666_mention or res.regime_rdc_mention):
        res.regime_conflict = True

    m_rej = REAJUSTE_CLAUSE.search(text)
    clause_windows: list[tuple[int, int]] = []
    if m_rej:
        res.reajuste_clause_mention = True
        res.pipeline_state = DOC_CLAUSE_LOCATED
        w0, w1 = max(0, m_rej.start() - 200), min(len(text), m_rej.end() + 400)
        clause_windows.append((w0, w1))
        window = text[w0:w1]
        if re.search(r"j[aá]\s+reajust|reajuste\s+concedido|apostilado\s+o\s+reajuste", window, re.I):
            res.already_adjusted_hint = True
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=now,
                excerpt=window.strip()[:800],
                content_hash=h,
                extraction_method=method,
                confidence="medium",
                field_found="clausula_reajuste",
                section="clausula_reajuste",
            )
        )
        # Indices only count when inside reajuste clause window
        for idx in _indices_in_window(text, w0, w1):
            if idx not in res.index_in_clause:
                res.index_in_clause.append(idx)
                res.evidences.append(
                    Evidence(
                        doc_type=doc_type,
                        orgao_emissor=orgao,
                        identificador_oficial=official_id,
                        url_or_location=url,
                        consulted_at=now,
                        excerpt=text[max(0, w0) : min(len(text), w1)][:200],
                        content_hash=h,
                        extraction_method=method,
                        confidence="high",
                        field_found="indice_na_clausula_reajuste",
                        section="clausula_reajuste",
                    )
                )

    m_db = DATA_BASE_PAT.search(text)
    if m_db:
        res.data_base_mention = True
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=now,
                excerpt=text[max(0, m_db.start() - 40) : min(len(text), m_db.end() + 80)].strip(),
                content_hash=h,
                extraction_method=method,
                confidence="medium",
                field_found="data_base",
            )
        )

    if APOSTILA_PAT.search(text):
        res.apostila_mention = True

    # Collect all index mentions; split in-clause vs outside-only
    all_idx: list[str] = []
    for pat in INDEX_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            idx = m.group(1).upper().replace(" ", "_")
            if idx not in all_idx:
                all_idx.append(idx)
            in_clause = any(w0 <= m.start() <= w1 for w0, w1 in clause_windows)
            if not in_clause and idx not in res.index_in_clause:
                if idx not in res.index_outside_clause_only:
                    res.index_outside_clause_only.append(idx)
                    res.evidences.append(
                        Evidence(
                            doc_type=doc_type,
                            orgao_emissor=orgao,
                            identificador_oficial=official_id,
                            url_or_location=url,
                            consulted_at=now,
                            excerpt=text[max(0, m.start() - 30) : min(len(text), m.end() + 30)].strip(),
                            content_hash=h,
                            extraction_method=method,
                            confidence="low",
                            field_found="indice_fora_da_clausula",
                        )
                    )
    res.index_candidates = list(res.index_in_clause)  # only clause-linked for assignment
    # Keep outside list separate — do not promote to index_candidates

    return res


def fetch_url_text(url: str, *, timeout: float = 12.0, max_bytes: int = 500_000) -> tuple[str | None, str | None, str]:
    """Fetch public URL body.

    Returns (text_or_placeholder, error, kind) where kind is
    ``html`` | ``pdf_binary`` | ``json`` | ``error`` | ``empty``.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "extra-cli-reajuste-14133/2.0 (+research; read-only)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(max_bytes)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype or raw[:4] == b"%PDF":
                placeholder = (
                    f"[PDF_BINARY bytes={len(raw)} "
                    f"sha256={hashlib.sha256(raw).hexdigest()[:16]}]"
                )
                return placeholder, None, "pdf_binary"
            if "json" in ctype:
                return raw.decode("utf-8", errors="replace"), None, "json"
            return raw.decode("utf-8", errors="replace"), None, "html"
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}", "error"


def try_extract_pdf_via_process_documents(pdf_bytes: bytes) -> str | None:
    """Reuse existing deep document pipeline when available; never invent text."""
    try:
        # Prefer pypdf if present (project dependency for process_documents)
        from io import BytesIO

        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(BytesIO(pdf_bytes))
        parts: list[str] = []
        for i, page in enumerate(reader.pages[:40]):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                parts.append(f"[page={i + 1}]\n{t}")
        text = "\n".join(parts).strip()
        return text or None
    except Exception:
        return None


def verify_contract_documents(
    *,
    contrato_id: str,
    orgao_cnpj: str | None,
    orgao_nome: str | None,
    objeto: str | None,
    fetch_remote: bool = False,
    max_fetches: int = 1,
) -> DocumentScanResult:
    """Scan available public signals for a contract.

    Always scans the object text (low confidence). Optionally fetches PNCP
    portal / API. PDF binary never sets docs_accessible=True unless text extracted.
    """
    merged = DocumentScanResult()
    obj_scan = extract_from_text(
        objeto or "",
        doc_type="objeto_contrato_pncp",
        url=None,
        orgao=orgao_nome,
        official_id=contrato_id,
        method="object_field_scan",
    )
    # Object mentions don't set docs_accessible for HOT
    merged.index_outside_clause_only = list(obj_scan.index_outside_clause_only)
    # Do not promote object-only indices to clause-linked
    merged.regime_14133_mention = obj_scan.regime_14133_mention
    merged.regime_8666_mention = obj_scan.regime_8666_mention
    merged.regime_rdc_mention = obj_scan.regime_rdc_mention
    merged.regime_conflict = obj_scan.regime_conflict
    merged.reajuste_clause_mention = obj_scan.reajuste_clause_mention
    merged.data_base_mention = obj_scan.data_base_mention
    merged.apostila_mention = obj_scan.apostila_mention
    merged.already_adjusted_hint = obj_scan.already_adjusted_hint
    for e in obj_scan.evidences:
        e.confidence = "low"
        e.doc_type = "objeto_contrato_pncp_field"
        merged.evidences.append(e)
    merged.limitations.append(
        "Varredura do campo objeto_contrato não substitui edital/contrato/apostila."
    )
    merged.docs_accessible = False
    merged.text_extracted = False
    merged.pipeline_state = DOC_UNAVAILABLE

    url = pncp_contract_url(contrato_id, orgao_cnpj)
    if url:
        merged.pipeline_state = DOC_URL_LOCATED
        merged.evidences.append(
            Evidence(
                doc_type="pncp_portal_url",
                orgao_emissor=orgao_nome,
                identificador_oficial=contrato_id,
                url_or_location=url,
                consulted_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                excerpt="URL canônica do portal PNCP (não é prova documental por si só).",
                content_hash=None,
                extraction_method="url_builder",
                confidence="high",
                field_found="portal_url",
            )
        )
        merged.limitations.append(
            "URL do portal localizada ≠ documento acessível / texto extraído."
        )

    fetches_left = max_fetches if fetch_remote else 0
    api_url = pncp_api_contract_url(contrato_id)
    def _unpack_fetch(result: Any) -> tuple[str | None, str | None, str]:
        """Support (text, err) legacy and (text, err, kind) triples."""
        if not isinstance(result, tuple):
            return None, "bad_fetch_return", "error"
        if len(result) == 2:
            text, err = result
            kind = "error" if err else "html"
            return text, err, kind
        if len(result) >= 3:
            return result[0], result[1], result[2]
        return None, "bad_fetch_return", "error"

    if fetches_left > 0 and api_url:
        text, err, kind = _unpack_fetch(fetch_url_text(api_url))
        fetches_left -= 1
        if err:
            merged.limitations.append(f"api_fetch_error:{err}")
            if "network" in (err or "").lower() or "URLError" in (err or ""):
                merged.network_error = True
        elif text and kind in {"json", "html"}:
            page = extract_from_text(
                text,
                doc_type="pncp_api_contract",
                url=api_url,
                orgao=orgao_nome,
                official_id=contrato_id,
                method="http_get_api",
            )
            _merge_page(merged, page)

    if fetches_left > 0 and url:
        text, err, kind = _unpack_fetch(fetch_url_text(url))
        if err:
            merged.network_error = True
            merged.limitations.append(f"fetch_error:{err}")
            if merged.pipeline_state == DOC_URL_LOCATED:
                # URL known but body failed
                pass
        elif text:
            if kind == "pdf_binary":
                merged.pdf_binary_located = True
                merged.pipeline_state = DOC_DOWNLOADED
                merged.docs_accessible = False
                merged.text_extracted = False
                merged.limitations.append(
                    "Documento PDF detectado sem extração de texto — cláusula não confirmada."
                )
                # Attempt deep extract if we re-fetch raw (placeholder only here)
                page = extract_from_text(
                    text,
                    doc_type="pncp_portal_pdf",
                    url=url,
                    orgao=orgao_nome,
                    official_id=contrato_id,
                    method="http_get_pdf_binary",
                    is_binary_placeholder=True,
                )
                merged.evidences.extend(page.evidences)
            else:
                page = extract_from_text(
                    text,
                    doc_type="pncp_portal_html",
                    url=url,
                    orgao=orgao_nome,
                    official_id=contrato_id,
                    method="http_get_html",
                )
                _merge_page(merged, page)
        else:
            merged.limitations.append("fetch_empty_body")
            if not merged.evidences:
                merged.pipeline_state = DOC_PARSE_FAILED

    merged.limitations.append(
        "Ausência de apostila no PNCP não prova, isoladamente, que o reajuste não foi concedido."
    )
    return merged


def _merge_page(merged: DocumentScanResult, page: DocumentScanResult) -> None:
    """Merge a page/API scan into the aggregate result (respect binary rules)."""
    if page.pdf_binary_located and not page.text_extracted:
        merged.pdf_binary_located = True
        # Do NOT set docs_accessible
        if merged.pipeline_state in {DOC_UNAVAILABLE, DOC_URL_LOCATED}:
            merged.pipeline_state = DOC_DOWNLOADED
        merged.limitations.extend(page.limitations)
        merged.evidences.extend(page.evidences)
        return

    if page.text_extracted:
        merged.docs_accessible = True
        merged.text_extracted = True
        if page.pipeline_state == DOC_CLAUSE_LOCATED or page.reajuste_clause_mention:
            merged.pipeline_state = DOC_CLAUSE_LOCATED
        elif merged.pipeline_state not in {DOC_CLAUSE_LOCATED}:
            merged.pipeline_state = DOC_TEXT_EXTRACTED

    merged.regime_14133_mention = merged.regime_14133_mention or page.regime_14133_mention
    merged.regime_8666_mention = merged.regime_8666_mention or page.regime_8666_mention
    merged.regime_rdc_mention = merged.regime_rdc_mention or page.regime_rdc_mention
    merged.regime_conflict = merged.regime_conflict or page.regime_conflict
    merged.reajuste_clause_mention = merged.reajuste_clause_mention or page.reajuste_clause_mention
    merged.data_base_mention = merged.data_base_mention or page.data_base_mention
    merged.apostila_mention = merged.apostila_mention or page.apostila_mention
    merged.already_adjusted_hint = merged.already_adjusted_hint or page.already_adjusted_hint
    for idx in page.index_in_clause:
        if idx not in merged.index_in_clause:
            merged.index_in_clause.append(idx)
    for idx in page.index_outside_clause_only:
        if idx not in merged.index_outside_clause_only and idx not in merged.index_in_clause:
            merged.index_outside_clause_only.append(idx)
    merged.index_candidates = list(merged.index_in_clause)
    merged.evidences.extend(page.evidences)
    merged.limitations.extend(page.limitations)
