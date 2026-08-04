"""Document verification helpers (public PNCP / local harvest).

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
from typing import Any

# Patterns for extraction from free text / HTML snippets
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentScanResult:
    evidences: list[Evidence] = field(default_factory=list)
    index_candidates: list[str] = field(default_factory=list)
    regime_14133_mention: bool = False
    reajuste_clause_mention: bool = False
    data_base_mention: bool = False
    apostila_mention: bool = False
    already_adjusted_hint: bool = False
    docs_accessible: bool = False
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


def extract_from_text(
    text: str,
    *,
    doc_type: str,
    url: str | None,
    orgao: str | None = None,
    official_id: str | None = None,
    method: str = "regex_text",
) -> DocumentScanResult:
    """Extract reajuste-related signals from a text blob."""
    res = DocumentScanResult()
    if not text or not text.strip():
        res.limitations.append("empty_text")
        return res
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    res.docs_accessible = True

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

    m_rej = REAJUSTE_CLAUSE.search(text)
    if m_rej:
        res.reajuste_clause_mention = True
        window = text[max(0, m_rej.start() - 80) : min(len(text), m_rej.end() + 120)]
        if re.search(r"j[aá]\s+reajust|reajuste\s+concedido|apostilado\s+o\s+reajuste", window, re.I):
            res.already_adjusted_hint = True
        res.evidences.append(
            Evidence(
                doc_type=doc_type,
                orgao_emissor=orgao,
                identificador_oficial=official_id,
                url_or_location=url,
                consulted_at=now,
                excerpt=window.strip(),
                content_hash=h,
                extraction_method=method,
                confidence="medium",
                field_found="clausula_reajuste",
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

    for pat in INDEX_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            idx = m.group(1).upper().replace(" ", "_")
            if idx not in res.index_candidates:
                res.index_candidates.append(idx)
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
                        confidence="medium",
                        field_found="indice",
                    )
                )

    return res


def fetch_url_text(url: str, *, timeout: float = 12.0, max_bytes: int = 500_000) -> tuple[str | None, str | None]:
    """Fetch public URL body as text; returns (text, error)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "extra-cli-reajuste-14133/1.0 (+research; read-only)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(max_bytes)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype or raw[:4] == b"%PDF":
                # do not invent PDF text — mark as binary present
                return f"[PDF_BINARY bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()[:16]}]", None
            return raw.decode("utf-8", errors="replace"), None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


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

    Always scans the object text. Optionally fetches PNCP portal page
    (HTML only; PDF binary noted without clause invention).
    """
    merged = DocumentScanResult()
    # Object text is NOT an official contract document — low confidence scan
    obj_scan = extract_from_text(
        objeto or "",
        doc_type="objeto_contrato_pncp",
        url=None,
        orgao=orgao_nome,
        official_id=contrato_id,
        method="object_field_scan",
    )
    # Downgrade: object mentions don't set docs_accessible for HOT
    merged.index_candidates = list(obj_scan.index_candidates)
    merged.regime_14133_mention = obj_scan.regime_14133_mention
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

    url = pncp_contract_url(contrato_id, orgao_cnpj)
    if url:
        merged.evidences.append(
            Evidence(
                doc_type="pncp_portal_url",
                orgao_emissor=orgao_nome,
                identificador_oficial=contrato_id,
                url_or_location=url,
                consulted_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                excerpt="URL canônica do portal PNCP (consulta humana / fetch opcional).",
                content_hash=None,
                extraction_method="url_builder",
                confidence="high",
                field_found="portal_url",
            )
        )

    if fetch_remote and url and max_fetches > 0:
        text, err = fetch_url_text(url)
        if err:
            merged.network_error = True
            merged.limitations.append(f"fetch_error:{err}")
        elif text:
            page = extract_from_text(
                text,
                doc_type="pncp_portal_html",
                url=url,
                orgao=orgao_nome,
                official_id=contrato_id,
                method="http_get_html",
            )
            merged.docs_accessible = page.docs_accessible
            merged.regime_14133_mention = merged.regime_14133_mention or page.regime_14133_mention
            merged.reajuste_clause_mention = merged.reajuste_clause_mention or page.reajuste_clause_mention
            merged.data_base_mention = merged.data_base_mention or page.data_base_mention
            merged.apostila_mention = merged.apostila_mention or page.apostila_mention
            merged.already_adjusted_hint = merged.already_adjusted_hint or page.already_adjusted_hint
            for idx in page.index_candidates:
                if idx not in merged.index_candidates:
                    merged.index_candidates.append(idx)
            merged.evidences.extend(page.evidences)
            if text.startswith("[PDF_BINARY"):
                merged.limitations.append(
                    "Documento PDF detectado sem extração de texto — cláusula não confirmada automaticamente."
                )
                merged.docs_accessible = True  # located but not fully parsed
        else:
            merged.limitations.append("fetch_empty_body")

    merged.limitations.append(
        "Ausência de apostila no PNCP não prova, isoladamente, que o reajuste não foi concedido."
    )
    return merged
