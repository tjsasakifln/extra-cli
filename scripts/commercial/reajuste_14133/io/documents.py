"""Document verification for reajuste 14.133 — real PNCP arquivos + PDF extract.

Honest pipeline states:
  DOCUMENT_URL_LOCATED → DOCUMENT_DOWNLOADED → TEXT_EXTRACTED → CLAUSE_LOCATED
  | DOCUMENT_UNAVAILABLE | DOCUMENT_PARSE_FAILED

Rules (fail-closed):
  - Portal HTML / API JSON alone NEVER set docs_accessible=True for documentary gates.
  - Object field scan is low-confidence signal only.
  - PDF binary without text extract ≠ documentary proof.
  - Official proof requires TEXT_EXTRACTED from compra/contrato arquivos (edital, TR, contrato PDF).
"""

from __future__ import annotations

# ruff: noqa: S310
import hashlib
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urljoin

from scripts.commercial.reajuste_14133 import (
    DOC_CLAUSE_LOCATED,
    DOC_DOWNLOADED,
    DOC_PARSE_FAILED,
    DOC_TEXT_EXTRACTED,
    DOC_UNAVAILABLE,
    DOC_URL_LOCATED,
)

PNCP_API = "https://pncp.gov.br/api/pncp/v1"
PNCP_API_ALT = "https://pncp.gov.br/pncp-api/v1"
USER_AGENT = "extra-cli-reajuste-14133/2.1 (+research; read-only)"

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

# Reajuste em sentido estrito only — NEVER "atualização monetária" (late-payment IPCA)
REAJUSTE_CLAUSE = re.compile(
    r"reajust(?:e|amento)|repactua[cç]|reequil[ií]brio",
    re.I,
)
# Late-payment / billing updates — must not bind indices for reajuste score
ATUALIZACAO_MONETARIA = re.compile(
    r"atualiza[cç][aã]o\s+monet[aá]ria|atualiza[cç][aã]o\s+por\s+atraso",
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

# Prefer these document titles when choosing which PDF to extract first
_PRIORITY_TITLE = re.compile(
    r"edital|contrato|termo\s+de\s+refer[eê]ncia|projeto\s+b[aá]sico|"
    r"minuta|instrumento|apostila|planilha",
    re.I,
)

# Methods that count as official document text for documentary gates
OFFICIAL_EXTRACT_METHODS = frozenset(
    {
        "pncp_pdf_pypdf2",
        "pncp_pdf_pypdf",
        "process_documents_pdf",
        "http_get_pdf_text",
    }
)
# Methods that are signal-only (never documentary proof alone)
SIGNAL_ONLY_METHODS = frozenset(
    {
        "object_field_scan",
        "url_builder",
        "http_get_html",
        "http_get_api",
        "http_get_pdf_binary",
    }
)


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


# Documentary types sought during deep recovery (priority queue)
DOC_TYPES_SOUGHT = (
    "edital",
    "contrato_ou_minuta",
    "orcamento_estimado",
    "planilha_orcamentaria",
    "termo_referencia_ou_projeto_basico",
    "cronograma",
    "apostilas",
    "termos_aditivos",
    "publicacoes_reajuste",
    "medicoes_ou_pagamentos",
)


@dataclass
class DocumentScanResult:
    evidences: list[Evidence] = field(default_factory=list)
    index_candidates: list[str] = field(default_factory=list)
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
    # True ONLY when official document text was extracted (PDF/edital/contrato)
    docs_accessible: bool = False
    text_extracted: bool = False
    official_text_extracted: bool = False
    pdf_binary_located: bool = False
    pdf_text_pages: int = 0
    pipeline_state: str = DOC_UNAVAILABLE
    network_error: bool = False
    limitations: list[str] = field(default_factory=list)
    # Honest effort counters for campaign metrics
    arquivos_listed: int = 0
    pdfs_downloaded: int = 0
    pdfs_text_extracted: int = 0
    deep_document_work: bool = (
        False  # True only if PDF download+extract attempted with success or hard fail after download
    )
    # Priority-queue deep recovery fields
    document_link_status: str | None = None
    document_link: dict[str, Any] | None = None
    signals_usable: bool = True
    exact_data_base: dict[str, Any] | None = None
    data_base_exata_localizada: bool = False
    index_formula: dict[str, Any] | None = None
    doc_type_inventory: dict[str, Any] = field(default_factory=dict)
    formats_processed: list[str] = field(default_factory=list)
    files_processed: int = 0
    early_stop_disabled: bool = False

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


def parse_pncp_contrato_id(contrato_id: str | None) -> tuple[str, int, int] | None:
    """Return (cnpj14, ano, sequencial) from PNCP contract control number."""
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", (contrato_id or "").strip())
    if not m:
        return None
    # groups: 1=cnpj, 2=sequencial, 3=ano
    return m.group(1), int(m.group(3)), int(m.group(2))


def parse_pncp_compra_id(compra_id: str | None) -> tuple[str, int, int] | None:
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", (compra_id or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(3)), int(m.group(2))


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    is_official_document: bool = False,
    page_hint: str | None = None,
) -> DocumentScanResult:
    """Extract reajuste-related signals from a text blob.

    ``is_official_document=True`` only for edital/contrato/TR PDF text — enables
    docs_accessible. Portal HTML / object field must pass False.
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
        res.limitations.append("PDF binário localizado sem extração de texto — não satisfaz gate documental.")
        h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=_now(),
                excerpt=text[:200],
                content_hash=h,
                extraction_method=method,
                confidence="low",
                field_found="pdf_binary_only",
            )
        )
        return res

    h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    # Signal extraction always possible; documentary accessibility is separate
    res.text_extracted = bool(is_official_document)
    res.official_text_extracted = bool(is_official_document)
    res.docs_accessible = bool(is_official_document)
    res.pipeline_state = DOC_TEXT_EXTRACTED if is_official_document else DOC_URL_LOCATED

    m_reg = REGIME_14133_PAT.search(text)
    if m_reg:
        res.regime_14133_mention = True
        start = max(0, m_reg.start() - 60)
        end = min(len(text), m_reg.end() + 60)
        conf = "high" if is_official_document else "low"
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=_now(),
                excerpt=text[start:end].strip(),
                content_hash=h,
                extraction_method=method,
                confidence=conf,
                field_found="regime_legal_14133",
                page=page_hint,
            )
        )
    if REGIME_8666_PAT.search(text):
        res.regime_8666_mention = True
    if REGIME_RDC_PAT.search(text):
        res.regime_rdc_mention = True
    if res.regime_14133_mention and (res.regime_8666_mention or res.regime_rdc_mention):
        res.regime_conflict = True

    clause_windows: list[tuple[int, int]] = []
    # Collect reajuste/repactuação/reequilíbrio windows.
    # Index binding uses FORWARD window from keyword only so preceding
    # "atualização monetária" blocks cannot bind IPCA into reajuste.
    for m_rej in REAJUSTE_CLAUSE.finditer(text):
        res.reajuste_clause_mention = True
        if is_official_document:
            res.pipeline_state = DOC_CLAUSE_LOCATED
        # Context for excerpt may look back; indices only look forward from keyword
        w0_ctx = max(0, m_rej.start() - 80)
        w0_idx = m_rej.start()
        w1 = min(len(text), m_rej.end() + 400)
        clause_windows.append((w0_idx, w1))
        excerpt_window = text[w0_ctx:w1]
        index_window_text = text[w0_idx:w1]
        if re.search(
            r"j[aá]\s+reajust|reajuste\s+concedido|apostilado\s+o\s+reajuste",
            excerpt_window,
            re.I,
        ):
            res.already_adjusted_hint = True
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=_now(),
                excerpt=excerpt_window.strip()[:800],
                content_hash=h,
                extraction_method=method,
                confidence="high" if is_official_document else "low",
                field_found="clausula_reajuste",
                section="clausula_reajuste",
                page=page_hint,
            )
        )
        for idx in _indices_in_window(text, w0_idx, w1):
            if idx in res.index_in_clause:
                continue
            # Double-check: index position must not be inside atualização monetária span
            # that is not itself a reajuste sentence.
            ok = True
            for pat in (
                r"\bINCC(?:-?DI|-?M)?\b",
                r"\bIPCA\b",
                r"\bIGP-?M\b",
                r"\bSINAPI\b",
                r"\bSICRO\b",
                r"\bIVAR\b",
                r"\bICC\b",
                r"\bINPC\b",
            ):
                for im in re.finditer(pat, index_window_text, re.I):
                    token = im.group(0).upper().replace(" ", "_")
                    if idx.split("_")[0] not in token and token.split("-")[0] not in idx:
                        continue
                    abs_pos = w0_idx + im.start()
                    around = text[max(0, abs_pos - 100) : min(len(text), abs_pos + 40)]
                    if ATUALIZACAO_MONETARIA.search(around) and not re.search(r"reajust(?:e|amento)", around, re.I):
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                if idx not in res.index_outside_clause_only:
                    res.index_outside_clause_only.append(idx)
                continue
            res.index_in_clause.append(idx)
            res.evidences.append(
                Evidence(
                    doc_type=doc_type,
                    orgao_emissor=orgao,
                    identificador_oficial=official_id,
                    url_or_location=url,
                    consulted_at=_now(),
                    excerpt=index_window_text[:200],
                    content_hash=h,
                    extraction_method=method,
                    confidence="high" if is_official_document else "low",
                    field_found="indice_na_clausula_reajuste",
                    section="clausula_reajuste",
                    page=page_hint,
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
                consulted_at=_now(),
                excerpt=text[max(0, m_db.start() - 40) : min(len(text), m_db.end() + 80)].strip(),
                content_hash=h,
                extraction_method=method,
                confidence="high" if is_official_document else "low",
                field_found="data_base",
                page=page_hint,
            )
        )

    if APOSTILA_PAT.search(text):
        res.apostila_mention = True

    for pat in INDEX_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            idx = m.group(1).upper().replace(" ", "_")
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
                            consulted_at=_now(),
                            excerpt=text[max(0, m.start() - 30) : min(len(text), m.end() + 30)].strip(),
                            content_hash=h,
                            extraction_method=method,
                            confidence="low",
                            field_found="indice_fora_da_clausula",
                            page=page_hint,
                        )
                    )
    res.index_candidates = list(res.index_in_clause)
    return res


def try_extract_pdf_via_process_documents(
    pdf_bytes: bytes,
    *,
    max_pages: int | None = None,
    full_text_first: bool = True,
) -> tuple[str | None, int]:
    """Extract text from PDF bytes using PyPDF2/pypdf. Returns (text, page_count).

    For priority deepen: process all pages (max_pages=None). When full_text_first,
    extract all pages then caller selects evidence windows from the full text.
    Legacy default was first 50 pages; pass max_pages=50 to restore that cap.
    """
    if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
        return None, 0
    try:
        try:
            from pypdf import PdfReader  # type: ignore[import-untyped]

            method = "pypdf"
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore[import-untyped]

            method = "PyPDF2"
        del method
        reader = PdfReader(BytesIO(pdf_bytes))
        parts: list[str] = []
        n_pages = len(reader.pages)
        page_iter = reader.pages if max_pages is None else reader.pages[: max(1, max_pages)]
        for i, page in enumerate(page_iter):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                parts.append(f"[page={i + 1}]\n{t}")
        text = "\n".join(parts).strip()
        # full_text_first is informational for callers; extraction already covers pages
        _ = full_text_first
        return (text or None), n_pages
    except Exception:
        return None, 0


def try_extract_docx(data: bytes) -> tuple[str | None, str]:
    """Extract plain text from DOCX (Office Open XML)."""
    import zipfile

    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                return None, "not_docx"
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        # strip tags crudely
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return (text or None), "docx"
    except Exception as exc:
        return None, f"docx_error:{type(exc).__name__}"


def try_extract_xlsx_ods(data: bytes, *, filename: str = "") -> tuple[str | None, str]:
    """Extract cell text from XLSX or ODS for budget/competence search."""
    import zipfile

    name = filename.lower()
    try:
        if name.endswith(".ods") or data[:2] == b"PK":
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = zf.namelist()
                # XLSX shared strings + sheets
                if any(n.startswith("xl/") for n in names):
                    parts: list[str] = []
                    if "xl/sharedStrings.xml" in names:
                        ss = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                        parts.append(re.sub(r"<[^>]+>", " ", ss))
                    for n in names:
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"):
                            sheet = zf.read(n).decode("utf-8", errors="replace")
                            parts.append(re.sub(r"<[^>]+>", " ", sheet))
                    text = re.sub(r"\s+", " ", "\n".join(parts)).strip()
                    return (text or None), "xlsx"
                if "content.xml" in names:
                    content = zf.read("content.xml").decode("utf-8", errors="replace")
                    text = re.sub(r"<[^>]+>", " ", content)
                    text = re.sub(r"\s+", " ", text).strip()
                    return (text or None), "ods"
        return None, "unknown_spreadsheet"
    except Exception as exc:
        return None, f"sheet_error:{type(exc).__name__}"


def safe_zip_list(data: bytes, *, max_members: int = 40, max_member_bytes: int = 15_000_000) -> list[tuple[str, bytes]]:
    """Safely list and read ZIP members (zip-slip resistant, size capped)."""
    import zipfile

    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            for info in zf.infolist()[:max_members]:
                name = info.filename
                if name.endswith("/"):
                    continue
                # zip-slip
                if ".." in name.replace("\\", "/").split("/"):
                    continue
                if info.file_size > max_member_bytes:
                    continue
                try:
                    raw = zf.read(info)
                except Exception:  # noqa: S112
                    continue
                if len(raw) > max_member_bytes:
                    continue
                out.append((name, raw))
    except Exception:
        return []
    return out


def _classify_doc_type(title: str) -> str | None:
    t = title.lower()
    if re.search(r"edital", t):
        return "edital"
    if re.search(r"contrato|minuta", t):
        return "contrato_ou_minuta"
    if re.search(r"or[cç]amento\s+estimado|orcamento estimado", t):
        return "orcamento_estimado"
    if re.search(r"planilha|or[cç]ament", t):
        return "planilha_orcamentaria"
    if re.search(r"termo\s+de\s+refer|projeto\s+b[aá]sico", t):
        return "termo_referencia_ou_projeto_basico"
    if re.search(r"cronograma", t):
        return "cronograma"
    if re.search(r"apostila", t):
        return "apostilas"
    if re.search(r"aditiv", t):
        return "termos_aditivos"
    if re.search(r"reajust", t):
        return "publicacoes_reajuste"
    if re.search(r"medi[cç]|pagamento|empenho", t):
        return "medicoes_ou_pagamentos"
    return None


def _empty_doc_inventory() -> dict[str, Any]:
    return {
        dtype: {"sought": True, "found": False, "processed": False, "unavailable": True} for dtype in DOC_TYPES_SOUGHT
    }


def _http_get(
    url: str, *, timeout: float = 45.0, max_bytes: int = 8_000_000, accept: str = "*/*"
) -> tuple[bytes | None, str | None, str]:
    """GET raw bytes. Returns (body, error, content_type)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(max_bytes)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            return raw, None, ctype
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}", "error"


def fetch_url_text(url: str, *, timeout: float = 12.0, max_bytes: int = 500_000) -> tuple[str | None, str | None, str]:
    """Fetch public URL body as text/kind triple (html|pdf_binary|json|error|empty)."""
    raw, err, ctype = _http_get(url, timeout=timeout, max_bytes=max_bytes)
    if err:
        return None, err, "error"
    if not raw:
        return None, "empty", "empty"
    if "pdf" in ctype or raw[:4] == b"%PDF":
        placeholder = f"[PDF_BINARY bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()[:16]}]"
        return placeholder, None, "pdf_binary"
    if "json" in ctype:
        return raw.decode("utf-8", errors="replace"), None, "json"
    return raw.decode("utf-8", errors="replace"), None, "html"


def fetch_pncp_contract_meta(cnpj: str, ano: int, sequencial: int) -> dict[str, Any] | None:
    url = f"{PNCP_API}/orgaos/{cnpj}/contratos/{ano}/{sequencial}"
    raw, err, ctype = _http_get(url, timeout=40, accept="application/json")
    if err or not raw:
        return None
    if "json" not in ctype and raw[:1] not in (b"{", b"["):
        return None
    import json

    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def list_pncp_compra_arquivos(cnpj: str, ano: int, sequencial: int) -> list[dict[str, Any]]:
    """List public arquivos for a PNCP compra (edital/anexos)."""
    import json

    for base in (PNCP_API, PNCP_API_ALT):
        url = f"{base}/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos"
        raw, err, ctype = _http_get(url, timeout=40, accept="application/json")
        if err or not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as parse_exc:  # noqa: S112
            _ = parse_exc  # try alternate API host; empty parse is non-fatal
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [d for d in data["data"] if isinstance(d, dict)]
    return []


def _arquivo_url(arq: dict[str, Any], cnpj: str, ano: int, seq: int) -> str | None:
    url = arq.get("url") or arq.get("uri") or arq.get("link")
    if isinstance(url, str) and url.startswith("/"):
        url = urljoin("https://pncp.gov.br", url)
    if isinstance(url, str) and url.startswith("http"):
        return url
    seq_doc = arq.get("sequencialDocumento") or arq.get("sequencial")
    if seq_doc is not None:
        return f"{PNCP_API_ALT}/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos/{seq_doc}"
    return None


def _rank_arquivo(arq: dict[str, Any]) -> int:
    title = f"{arq.get('titulo') or ''} {arq.get('tipoDocumentoNome') or ''}"
    score = 0
    if _PRIORITY_TITLE.search(title):
        score += 10
    if re.search(r"edital", title, re.I):
        score += 20
    if re.search(r"contrato", title, re.I):
        score += 15
    if re.search(r"termo\s+de\s+refer", title, re.I):
        score += 12
    if re.search(r"\.pdf", title, re.I) or "pdf" in title.lower():
        score += 5
    if re.search(r"planilha|\.xls", title, re.I):
        score -= 5
    return score


def recover_pncp_official_documents(
    *,
    contrato_id: str,
    orgao_cnpj: str | None,
    orgao_nome: str | None,
    max_pdfs: int = 3,
    priority_deep: bool = False,
    max_pages: int | None = 50,
    allow_non_pdf: bool = False,
    early_stop_on_regime_clause: bool = True,
    contract_object: str | None = None,
    contract_fornecedor: str | None = None,
    contract_fornecedor_cnpj: str | None = None,
    contract_processo: str | None = None,
    contract_numero: str | None = None,
) -> DocumentScanResult:
    """Real recovery: contract meta → linked compra → download files → extract text.

    Priority deepen (priority_deep=True):
      - no fixed 3-PDF cap (max_pdfs large)
      - all pages (max_pages=None)
      - no early stop after regime+clause
      - multi-format: PDF, DOCX, XLSX, ODS, ZIP
    """
    from scripts.commercial.reajuste_14133.domain.data_base_exact import extract_exact_data_base
    from scripts.commercial.reajuste_14133.domain.document_link import (
        DOCUMENT_LINK_CONFLICT,
        invalidate_signals_on_conflict,
        verify_document_link,
    )

    if priority_deep:
        max_pdfs = max(max_pdfs, 50)
        max_pages = None
        allow_non_pdf = True
        early_stop_on_regime_clause = False

    res = DocumentScanResult()
    res.doc_type_inventory = _empty_doc_inventory()
    res.early_stop_disabled = not early_stop_on_regime_clause
    parsed = parse_pncp_contrato_id(contrato_id)
    if not parsed:
        res.limitations.append("contrato_id_not_pncp_parseable")
        res.pipeline_state = DOC_UNAVAILABLE
        return res
    cnpj, ano, seq = parsed
    res.pipeline_state = DOC_URL_LOCATED

    meta = fetch_pncp_contract_meta(cnpj, ano, seq)
    compra_key = None
    meta_object = None
    if meta:
        compra_key = meta.get("numeroControlePncpCompra") or meta.get("numeroControlePNCPCompra")
        meta_object = str(meta.get("objetoContrato") or meta.get("objeto") or "")
        res.evidences.append(
            Evidence(
                doc_type="pncp_contrato_api",
                orgao_emissor=orgao_nome,
                identificador_oficial=contrato_id,
                url_or_location=f"{PNCP_API}/orgaos/{cnpj}/contratos/{ano}/{seq}",
                consulted_at=_now(),
                excerpt=meta_object[:300],
                content_hash=hashlib.sha256(str(meta).encode()).hexdigest()[:32],
                extraction_method="http_get_api",
                confidence="medium",
                field_found="contrato_metadata",
            )
        )
        # Structured value for quality checks is elsewhere; regime never from meta year alone
    else:
        res.limitations.append("pncp_contrato_meta_unavailable")
        res.network_error = True

    compra_parsed = parse_pncp_compra_id(str(compra_key) if compra_key else None)
    if not compra_parsed:
        # Fallback: try same cnpj/ano with contract sequencial as compra (often wrong)
        res.limitations.append("numeroControlePncpCompra_ausente")
        return res

    ccnpj, cano, cseq = compra_parsed
    arquivos = list_pncp_compra_arquivos(ccnpj, cano, cseq)
    res.arquivos_listed = len(arquivos)
    if not arquivos:
        res.limitations.append("pncp_compra_arquivos_empty")
        return res

    # Inventory: mark found types from titles
    for arq in arquivos:
        title = str(arq.get("titulo") or arq.get("tipoDocumentoNome") or "")
        dtype = _classify_doc_type(title)
        if dtype and dtype in res.doc_type_inventory:
            res.doc_type_inventory[dtype]["found"] = True
            res.doc_type_inventory[dtype]["unavailable"] = False

    ranked = sorted(arquivos, key=_rank_arquivo, reverse=True)
    files_done = 0
    combined_official_text: list[str] = []
    any_conflict = False
    best_link_status: str | None = None

    def _process_text_blob(
        text: str,
        *,
        title: str,
        url: str | None,
        method: str,
        page_hint: str | None,
        is_spreadsheet: bool = False,
    ) -> None:
        nonlocal any_conflict, best_link_status
        # Document link gate before using signals
        # Bind compra files to the contract via numeroControlePncpCompra.
        # Do NOT compare contract sequencial with compra sequencial (different spaces).
        # When meta already linked this compra, both sides use the compra identity.
        link = verify_document_link(
            contract_numero_controle_pncp_compra=str(compra_key) if compra_key else None,
            contract_orgao_cnpj=orgao_cnpj or cnpj,
            contract_ano=cano,
            contract_sequencial=cseq,
            contract_processo=contract_processo,
            contract_numero=contract_numero or contrato_id,
            contract_object=contract_object or meta_object,
            contract_contratacao_object=meta_object,
            contract_fornecedor=contract_fornecedor,
            contract_fornecedor_cnpj=contract_fornecedor_cnpj,
            doc_numero_controle_pncp_compra=str(compra_key) if compra_key else None,
            doc_orgao_cnpj=ccnpj,
            doc_ano=cano,
            doc_sequencial=cseq,
            doc_object_or_title=title,
            doc_text=text[:20000],
            doc_fornecedor_mentions=text[:8000],
        )
        best_link_status = link.status
        res.document_link = link.as_dict()
        res.document_link_status = link.status
        if link.status == DOCUMENT_LINK_CONFLICT:
            any_conflict = True
            res.signals_usable = False
            wiped = invalidate_signals_on_conflict(
                extract_from_text(
                    text,
                    doc_type=f"pncp_file:{title[:60]}",
                    url=url,
                    orgao=orgao_nome,
                    official_id=contrato_id,
                    method=method,
                    is_official_document=True,
                    page_hint=page_hint,
                ).as_dict(),
                link,
            )
            res.limitations.extend(wiped.get("limitations") or [])
            res.evidences.append(
                Evidence(
                    doc_type=f"pncp_file_conflict:{title[:40]}",
                    orgao_emissor=orgao_nome,
                    identificador_oficial=contrato_id,
                    url_or_location=url,
                    consulted_at=_now(),
                    excerpt=f"DOCUMENT_LINK_CONFLICT: {', '.join(link.reasons)[:200]}",
                    content_hash=hashlib.sha256(text[:2000].encode()).hexdigest()[:32],
                    extraction_method=method,
                    confidence="none",
                    field_found="document_link_conflict",
                    page=page_hint,
                )
            )
            return

        page = extract_from_text(
            text,
            doc_type=f"pncp_file:{title[:60]}",
            url=url,
            orgao=orgao_nome,
            official_id=contrato_id,
            method=method,
            is_official_document=True,
            page_hint=page_hint,
        )
        _merge_official(res, page)
        combined_official_text.append(text)
        # Exact data-base
        db = extract_exact_data_base(
            text,
            document=title[:120],
            page_hint=page_hint,
            is_budget_spreadsheet=is_spreadsheet,
        )
        if db.data_base_exata_localizada:
            res.data_base_exata_localizada = True
            res.exact_data_base = db.as_dict()
        elif res.exact_data_base is None:
            res.exact_data_base = db.as_dict()
        # Index/formula bound to clause
        if page.index_in_clause:
            res.index_formula = {
                "indices": list(page.index_in_clause),
                "document": title[:120],
                "page": page_hint,
                "bound_to_reajuste_clause": True,
                "formula": None,
                "weights": None,
            }
        dtype = _classify_doc_type(title)
        if dtype and dtype in res.doc_type_inventory:
            res.doc_type_inventory[dtype]["processed"] = True
            res.doc_type_inventory[dtype]["found"] = True
            res.doc_type_inventory[dtype]["unavailable"] = False

    for arq in ranked:
        if files_done >= max_pdfs:
            break
        title = str(arq.get("titulo") or arq.get("tipoDocumentoNome") or "documento")
        url = _arquivo_url(arq, ccnpj, cano, cseq)
        if not url:
            continue
        time.sleep(0.15 if priority_deep else 0.2)
        body, err, ctype = _http_get(url, timeout=90 if priority_deep else 60, max_bytes=20_000_000)
        if err or not body:
            res.limitations.append(f"arquivo_fetch_error:{title[:40]}:{err}")
            res.network_error = True
            continue

        is_pdf = body[:4] == b"%PDF" or "pdf" in (ctype or "")
        is_zip = body[:2] == b"PK" and re.search(r"\.zip(\b|$)", title, re.I)
        is_docx = bool(re.search(r"\.docx(\b|$)", title, re.I)) or (body[:2] == b"PK" and "word" in title.lower())
        is_sheet = bool(re.search(r"\.(xlsx|xls|ods)(\b|$)", title, re.I))

        if is_pdf:
            res.pdfs_downloaded += 1
            res.pdf_binary_located = True
            res.pipeline_state = DOC_DOWNLOADED
            res.deep_document_work = True
            text, n_pages = try_extract_pdf_via_process_documents(body, max_pages=max_pages, full_text_first=True)
            if not text:
                res.limitations.append(f"pdf_parse_failed:{title[:40]}")
                res.pipeline_state = DOC_PARSE_FAILED
                res.evidences.append(
                    Evidence(
                        doc_type="pncp_compra_pdf",
                        orgao_emissor=orgao_nome,
                        identificador_oficial=contrato_id,
                        url_or_location=url,
                        consulted_at=_now(),
                        excerpt=f"[PDF_BINARY bytes={len(body)} pages={n_pages} title={title[:80]}]",
                        content_hash=hashlib.sha256(body).hexdigest(),
                        extraction_method="http_get_pdf_binary",
                        confidence="low",
                        field_found="pdf_binary_only",
                    )
                )
                files_done += 1
                continue
            res.pdfs_text_extracted += 1
            res.pdf_text_pages += n_pages
            page_hint = f"1-{n_pages}" if n_pages else None
            if "pdf" not in res.formats_processed:
                res.formats_processed.append("pdf")
            _process_text_blob(
                text,
                title=title,
                url=url,
                method="pncp_pdf_pypdf2",
                page_hint=page_hint,
            )
            files_done += 1
            res.files_processed += 1
        elif allow_non_pdf and is_docx:
            text, kind = try_extract_docx(body)
            res.deep_document_work = True
            if text:
                if "docx" not in res.formats_processed:
                    res.formats_processed.append("docx")
                _process_text_blob(text, title=title, url=url, method="pncp_docx", page_hint=None)
                files_done += 1
                res.files_processed += 1
            else:
                res.limitations.append(f"docx_parse_failed:{title[:40]}:{kind}")
        elif allow_non_pdf and is_sheet:
            text, kind = try_extract_xlsx_ods(body, filename=title)
            res.deep_document_work = True
            if text:
                if kind not in res.formats_processed:
                    res.formats_processed.append(kind)
                _process_text_blob(
                    text,
                    title=title,
                    url=url,
                    method=f"pncp_{kind}",
                    page_hint="sheet",
                    is_spreadsheet=True,
                )
                files_done += 1
                res.files_processed += 1
            else:
                res.limitations.append(f"sheet_parse_failed:{title[:40]}:{kind}")
        elif allow_non_pdf and is_zip:
            res.deep_document_work = True
            members = safe_zip_list(body)
            if "zip" not in res.formats_processed:
                res.formats_processed.append("zip")
            for mname, mbody in members:
                if mbody[:4] == b"%PDF":
                    text, n_pages = try_extract_pdf_via_process_documents(
                        mbody, max_pages=max_pages, full_text_first=True
                    )
                    if text:
                        _process_text_blob(
                            text,
                            title=f"{title}/{mname}",
                            url=url,
                            method="pncp_zip_pdf",
                            page_hint=f"1-{n_pages}" if n_pages else None,
                        )
                        res.pdfs_text_extracted += 1
                elif mname.lower().endswith(".docx"):
                    text, _k = try_extract_docx(mbody)
                    if text:
                        _process_text_blob(
                            text,
                            title=f"{title}/{mname}",
                            url=url,
                            method="pncp_zip_docx",
                            page_hint=None,
                        )
                elif re.search(r"\.(xlsx|ods)$", mname, re.I):
                    text, kind = try_extract_xlsx_ods(mbody, filename=mname)
                    if text:
                        _process_text_blob(
                            text,
                            title=f"{title}/{mname}",
                            url=url,
                            method=f"pncp_zip_{kind}",
                            page_hint="sheet",
                            is_spreadsheet=True,
                        )
            files_done += 1
            res.files_processed += 1
        else:
            if not is_pdf:
                res.limitations.append(f"arquivo_skipped_format:{title[:40]}")
            continue

        # Early stop only when NOT priority deep and we have regime+clause
        if (
            early_stop_on_regime_clause
            and res.regime_14133_mention
            and res.reajuste_clause_mention
            and res.data_base_exata_localizada
        ):
            break
        if (
            early_stop_on_regime_clause
            and not priority_deep
            and res.regime_14133_mention
            and res.reajuste_clause_mention
        ):
            break

    # Final exact data-base pass on combined text
    if combined_official_text and not res.data_base_exata_localizada:
        db = extract_exact_data_base(
            "\n".join(combined_official_text),
            document="combined_official",
            page_hint=None,
        )
        res.exact_data_base = db.as_dict()
        res.data_base_exata_localizada = db.data_base_exata_localizada

    if any_conflict and not res.signals_usable:
        # Wipe aggregate signals if conflict was the only content
        if not any(
            e.field_found not in {"document_link_conflict", "contrato_metadata", "portal_url", "pdf_binary_only"}
            for e in res.evidences
        ):
            res.regime_14133_mention = False
            res.reajuste_clause_mention = False
            res.index_in_clause = []
            res.index_candidates = []
            res.data_base_exata_localizada = False

    if res.document_link_status is None and best_link_status:
        res.document_link_status = best_link_status

    if res.official_text_extracted and res.signals_usable:
        res.docs_accessible = True
        res.text_extracted = True
        if res.reajuste_clause_mention:
            res.pipeline_state = DOC_CLAUSE_LOCATED
        else:
            res.pipeline_state = DOC_TEXT_EXTRACTED
    elif res.pdfs_downloaded and not res.pdfs_text_extracted:
        res.pipeline_state = DOC_PARSE_FAILED
        res.docs_accessible = False
    return res


def _merge_official(merged: DocumentScanResult, page: DocumentScanResult) -> None:
    """Merge official PDF extract — promotes documentary accessibility."""
    if page.official_text_extracted:
        merged.docs_accessible = True
        merged.text_extracted = True
        merged.official_text_extracted = True
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
    merged.pdf_text_pages += page.pdf_text_pages


def verify_contract_documents(
    *,
    contrato_id: str,
    orgao_cnpj: str | None,
    orgao_nome: str | None,
    objeto: str | None,
    fetch_remote: bool = False,
    max_fetches: int = 1,
    priority_deep: bool = False,
    fornecedor_nome: str | None = None,
    fornecedor_cnpj: str | None = None,
    processo: str | None = None,
    numero_contrato: str | None = None,
) -> DocumentScanResult:
    """Scan contract signals. Real documentary proof only via PNCP arquivos.

    Object + portal URL are always recorded as low-confidence signals.
    When fetch_remote=True, recover compra files and extract text.
    priority_deep lifts 3-PDF / 50-page / early-stop / non-PDF exclusions.
    """
    merged = DocumentScanResult()
    # --- Object field: signal only ---
    obj_scan = extract_from_text(
        objeto or "",
        doc_type="objeto_contrato_pncp",
        url=None,
        orgao=orgao_nome,
        official_id=contrato_id,
        method="object_field_scan",
        is_official_document=False,
    )
    for e in obj_scan.evidences:
        e.confidence = "low"
        e.doc_type = "objeto_contrato_pncp_field"
        merged.evidences.append(e)
    merged.index_outside_clause_only = list(obj_scan.index_outside_clause_only)
    # do not promote object-only indices to index_in_clause
    merged.regime_14133_mention = obj_scan.regime_14133_mention
    merged.regime_8666_mention = obj_scan.regime_8666_mention
    merged.reajuste_clause_mention = obj_scan.reajuste_clause_mention
    merged.data_base_mention = obj_scan.data_base_mention
    merged.apostila_mention = obj_scan.apostila_mention
    merged.already_adjusted_hint = obj_scan.already_adjusted_hint
    merged.limitations.append("Varredura do campo objeto_contrato não substitui edital/contrato/apostila.")
    merged.docs_accessible = False
    merged.text_extracted = False
    merged.official_text_extracted = False
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
                consulted_at=_now(),
                excerpt="URL canônica do portal PNCP — NÃO é prova documental por si só.",
                content_hash=None,
                extraction_method="url_builder",
                confidence="high",
                field_found="portal_url",
            )
        )
        merged.limitations.append("URL do portal localizada ≠ documento oficial acessível / texto extraído.")

    if not fetch_remote or max_fetches <= 0:
        merged.limitations.append(
            "Ausência de apostila no PNCP não prova, isoladamente, que o reajuste não foi concedido."
        )
        return merged

    # --- Real path: PNCP contract meta + compra arquivos + multi-format extract ---
    deep = recover_pncp_official_documents(
        contrato_id=contrato_id,
        orgao_cnpj=orgao_cnpj,
        orgao_nome=orgao_nome,
        max_pdfs=50 if priority_deep else min(3, max(1, max_fetches)),
        priority_deep=priority_deep,
        max_pages=None if priority_deep else 50,
        allow_non_pdf=priority_deep,
        early_stop_on_regime_clause=not priority_deep,
        contract_object=objeto,
        contract_fornecedor=fornecedor_nome,
        contract_fornecedor_cnpj=fornecedor_cnpj,
        contract_processo=processo,
        contract_numero=numero_contrato,
    )
    # Merge deep into merged without letting portal HTML promote docs_accessible
    merged.arquivos_listed = deep.arquivos_listed
    merged.pdfs_downloaded = deep.pdfs_downloaded
    merged.pdfs_text_extracted = deep.pdfs_text_extracted
    merged.pdf_text_pages = deep.pdf_text_pages
    merged.deep_document_work = deep.deep_document_work
    merged.network_error = merged.network_error or deep.network_error
    merged.pdf_binary_located = merged.pdf_binary_located or deep.pdf_binary_located
    merged.evidences.extend(deep.evidences)
    merged.limitations.extend(deep.limitations)
    merged.document_link_status = deep.document_link_status
    merged.document_link = deep.document_link
    merged.signals_usable = deep.signals_usable
    merged.exact_data_base = deep.exact_data_base
    merged.data_base_exata_localizada = deep.data_base_exata_localizada
    merged.index_formula = deep.index_formula
    merged.doc_type_inventory = deep.doc_type_inventory
    merged.formats_processed = deep.formats_processed
    merged.files_processed = deep.files_processed
    merged.early_stop_disabled = deep.early_stop_disabled

    if deep.official_text_extracted and deep.signals_usable:
        merged.docs_accessible = True
        merged.text_extracted = True
        merged.official_text_extracted = True
        merged.regime_14133_mention = merged.regime_14133_mention or deep.regime_14133_mention
        merged.regime_8666_mention = merged.regime_8666_mention or deep.regime_8666_mention
        merged.regime_rdc_mention = merged.regime_rdc_mention or deep.regime_rdc_mention
        merged.regime_conflict = merged.regime_conflict or deep.regime_conflict
        merged.reajuste_clause_mention = deep.reajuste_clause_mention or merged.reajuste_clause_mention
        merged.data_base_mention = deep.data_base_mention or merged.data_base_mention
        merged.apostila_mention = deep.apostila_mention or merged.apostila_mention
        merged.already_adjusted_hint = deep.already_adjusted_hint or merged.already_adjusted_hint
        for idx in deep.index_in_clause:
            if idx not in merged.index_in_clause:
                merged.index_in_clause.append(idx)
        for idx in deep.index_outside_clause_only:
            if idx not in merged.index_outside_clause_only and idx not in merged.index_in_clause:
                merged.index_outside_clause_only.append(idx)
        merged.index_candidates = list(merged.index_in_clause)
        if deep.reajuste_clause_mention:
            merged.pipeline_state = DOC_CLAUSE_LOCATED
        else:
            merged.pipeline_state = DOC_TEXT_EXTRACTED
    elif deep.official_text_extracted and not deep.signals_usable:
        # Conflict: keep raw evidences but block documentary gates
        merged.docs_accessible = False
        merged.text_extracted = False
        merged.official_text_extracted = False
        merged.signals_usable = False
        merged.limitations.append("document_signals_invalidated_by_link_conflict")
        if deep.pipeline_state in {DOC_DOWNLOADED, DOC_PARSE_FAILED, DOC_TEXT_EXTRACTED, DOC_CLAUSE_LOCATED}:
            merged.pipeline_state = deep.pipeline_state
    else:
        # Keep URL-located / downloaded / parse-failed — never pretend HTML is official
        if deep.pipeline_state in {DOC_DOWNLOADED, DOC_PARSE_FAILED}:
            merged.pipeline_state = deep.pipeline_state
        merged.docs_accessible = False
        merged.text_extracted = False
        merged.official_text_extracted = False

    merged.limitations.append("Ausência de apostila no PNCP não prova, isoladamente, que o reajuste não foi concedido.")
    return merged
