"""Deterministic reconciliation: DOE/DOM × Compras SC × PNCP.

Links official publication acts and Portal Compras SC records to PNCP
bids/contracts using explicit identifier rules only (no fuzzy text linking).

Outputs reversible match rows and a run report under ``output/reconciliation/``.

Usage::

    python3 -m scripts.matching.official_acts_reconcile --mode smoke
    python3 -m scripts.matching.official_acts_reconcile --mode sample --limit 500
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.common import digits_only
from scripts.crawl.run_evidence import build_run_evidence, new_run_id, sha256_file
from scripts.lib.name_normalizer import normalize_name

_logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "output" / "reconciliation"

# ---------------------------------------------------------------------------
# Match rules (priority order) — higher score wins; first registered on tie
# ---------------------------------------------------------------------------

# Scores are confidence metadata; evaluation order is RULE_PRIORITY (user-defined).
RULE_SCORES: dict[str, float] = {
    "pncp_number_exact": 1.0,
    "process_number_orgao_cnpj": 0.95,
    "process_number_year_modalidade": 0.90,
    "contract_number_orgao_cnpj": 0.88,
    "edital_number_year_orgao_cnpj": 0.85,
    "edital_number_year_orgao_name": 0.80,
    "compras_sc_id_crosswalk": 0.92,
    "deterministic_hash": 0.75,
}

RULE_PRIORITY: list[str] = [
    "pncp_number_exact",
    "process_number_orgao_cnpj",
    "process_number_year_modalidade",
    "contract_number_orgao_cnpj",
    "edital_number_year_orgao_cnpj",
    "edital_number_year_orgao_name",
    "compras_sc_id_crosswalk",
    "deterministic_hash",
]

# Deterministic evaluation order = explicit priority list (not score-sorted).
_RULE_ORDER = list(RULE_PRIORITY)

SOURCE_PNCP = "pncp"
SOURCE_DOE = "doe"
SOURCE_DOM = "dom"
SOURCE_COMPRAS_SC = "compras_sc"

# Value / date divergence thresholds
_VALUE_REL_TOL = 0.01  # 1%
_VALUE_ABS_TOL = 1.0  # R$ 1
_DATE_DAYS_TOL = 0  # exact for divergence flag (any delta is noted)

_RE_PNCP = re.compile(r"\b(\d{14}-\d{1,2}-\d{1,7}/\d{4})\b")
_RE_PROCESS = re.compile(
    r"(?i)\bprocesso(?:\s+(?:administrativo|licitat[oó]rio|seletivo|n[ºo°\.]))?\s*"
    r"(?:n[ºo°\.]?\s*)?[:\s]*"
    r"(\d{1,6}\s*[./-]\s*\d{2,4})"
)
_RE_EDITAL = re.compile(
    r"(?i)\bedital\s*(?:n[ºo°\.]?\s*)?[:\s_]*"
    r"(\d{1,6}\s*[./-_]\s*\d{2,4})"
)
_RE_CONTRATO = re.compile(
    r"(?i)\bcontrato(?:\s+administrativo)?\s*(?:n[ºo°\.]?\s*)?[:\s]*"
    r"(\d{1,6}\s*[./-]\s*\d{2,4})"
)
_RE_SC_ID = re.compile(r"(?i)\bsc-(\d+)\b")
_RE_COMPRAS_URL = re.compile(r"compras\.sc\.gov\.br/editais/(\d+)")

_MODALIDADE_ALIASES: dict[str, str] = {
    "pregao eletronico": "pregao_eletronico",
    "pregao presencial": "pregao_presencial",
    "pregao": "pregao",
    "concorrencia eletronica": "concorrencia",
    "concorrencia": "concorrencia",
    "dispensa de licitacao": "dispensa",
    "dispensa com cotacao eletronica": "dispensa",
    "dispensa": "dispensa",
    "inexigibilidade": "inexigibilidade",
    "inexigencia de licitacao": "inexigibilidade",
    "inexigencia": "inexigibilidade",
    "leilao": "leilao",
    "credenciamento": "credenciamento",
    "dialogo competitivo": "dialogo_competitivo",
    "manifestacao de interesse": "manifestacao_interesse",
    "pre_qualificacao": "pre_qualificacao",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Record:
    """Normalized record from any source system."""

    source_system: str
    source_id: str
    pncp_number: str | None = None
    process_number: str | None = None
    contract_number: str | None = None
    edital_number: str | None = None
    orgao_cnpj: str | None = None
    orgao_nome: str | None = None
    orgao_nome_norm: str | None = None
    year: int | None = None
    modalidade: str | None = None
    status: str | None = None
    publication_date: str | None = None
    value: float | None = None
    compras_sc_id: str | None = None
    has_documents: bool | None = None
    act_db_id: int | None = None  # official_acts.id when loaded from DB
    target_table: str | None = None  # for PNCP: pncp_raw_bids | pncp_supplier_contracts
    metadata: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.source_system}:{self.source_id}"


@dataclass
class MatchResult:
    """A reversible deterministic match between two records."""

    left_id: str
    right_id: str
    left_system: str
    right_system: str
    rule: str
    score: float
    justification: str
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    divergent_fields: list[str] = field(default_factory=list)
    needs_review: bool = False
    reversible: bool = True
    match_id: str = ""
    left_source_id: str = ""
    right_source_id: str = ""

    def __post_init__(self) -> None:
        if not self.match_id:
            material = f"{self.left_id}|{self.right_id}|{self.rule}"
            self.match_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass
class ReconciliationReport:
    run_id: str
    mode: str
    started_at: str
    completed_at: str | None = None
    sources_loaded: dict[str, int] = field(default_factory=dict)
    matches: list[MatchResult] = field(default_factory=list)
    reconciled_count: int = 0
    pncp_only: int = 0
    doe_only: int = 0
    dom_only: int = 0
    compras_sc_only: int = 0
    status_divergences: int = 0
    date_divergences: int = 0
    value_divergences: int = 0
    missing_documents: int = 0
    needs_review_count: int = 0
    rules_applied: dict[str, int] = field(default_factory=dict)
    claims_allowed: list[str] = field(default_factory=list)
    claims_forbidden: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    output_dir: str | None = None
    db_matches_written: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "sources_loaded": self.sources_loaded,
            "reconciled_count": self.reconciled_count,
            "pncp_only": self.pncp_only,
            "doe_only": self.doe_only,
            "dom_only": self.dom_only,
            "compras_sc_only": self.compras_sc_only,
            "status_divergences": self.status_divergences,
            "date_divergences": self.date_divergences,
            "value_divergences": self.value_divergences,
            "missing_documents": self.missing_documents,
            "needs_review_count": self.needs_review_count,
            "rules_applied": self.rules_applied,
            "match_count": len(self.matches),
            "matches_sample": [asdict(m) for m in self.matches[:50]],
            "db_matches_written": self.db_matches_written,
            "claims_allowed": self.claims_allowed,
            "claims_forbidden": self.claims_forbidden,
            "errors": self.errors,
            "notes": self.notes,
            "output_dir": self.output_dir,
        }


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def strip_accents(text: str) -> str:
    nk = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nk if not unicodedata.combining(c))


def normalize_identifier(value: str | None) -> str | None:
    """Normalize process/edital/contract numbers for exact comparison.

    ``001/2026``, ``1-2026``, ``1.2026`` → ``1/2026``
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = strip_accents(raw).upper()
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("º", "").replace("°", "").replace("N.", "").replace("Nº", "")
    raw = raw.replace(".", "/").replace("-", "/").replace("_", "/")
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return None
    norm_parts: list[str] = []
    for p in parts:
        digits = re.sub(r"\D", "", p)
        if not digits:
            continue
        # Keep year (4 digits) as-is; strip leading zeros on sequential parts
        if len(digits) == 4 and digits.startswith(("19", "20")):
            norm_parts.append(digits)
        else:
            norm_parts.append(str(int(digits)))
    if not norm_parts:
        return None
    return "/".join(norm_parts)


def normalize_pncp_number(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    m = _RE_PNCP.search(s)
    if m:
        return m.group(1)
    # Accept sc-NNNN as secondary pncp-like id (Compras SC ingested into PNCP)
    m2 = _RE_SC_ID.search(s)
    if m2:
        return f"sc-{m2.group(1)}"
    if s.lower().startswith("sc-"):
        return s.lower()
    # Bare digits-only not treated as PNCP control number
    return s if re.fullmatch(r"\d{14}-\d+-\d+/\d{4}", s) else (s if s.startswith("sc-") else None)


def normalize_modalidade(value: str | int | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        # Common PNCP modalidade ids
        id_map = {
            1: "leilao",
            2: "dialogo_competitivo",
            3: "concurso",
            4: "concorrencia",
            5: "pregao_eletronico",
            6: "pregao_presencial",
            7: "dispensa",
            8: "inexigibilidade",
            9: "manifestacao_interesse",
            10: "pre_qualificacao",
            11: "credenciamento",
            12: "dispensa",  # some portals overload 7/12
        }
        return id_map.get(value)
    s = strip_accents(str(value)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(.*?\)", "", s).strip()
    if s in _MODALIDADE_ALIASES:
        return _MODALIDADE_ALIASES[s]
    for alias, canon in _MODALIDADE_ALIASES.items():
        if alias in s:
            return canon
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or None


def normalize_status(value: str | None) -> str | None:
    if not value:
        return None
    s = strip_accents(str(value)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    mapping = {
        "homologado": "homologado",
        "homologacao": "homologado",
        "aguardando homologacao": "aguardando_homologacao",
        "publicado": "publicado",
        "aberta": "aberto",
        "aberto": "aberto",
        "encerrado": "encerrado",
        "cancelado": "cancelado",
        "revogado": "revogado",
        "suspenso": "suspenso",
        "deserto": "deserto",
        "fracassado": "fracassado",
        "em andamento": "em_andamento",
        "active": "ativo",
        "ativo": "ativo",
    }
    if s in mapping:
        return mapping[s]
    for k, v in mapping.items():
        if k in s:
            return v
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or None


def extract_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and 1990 <= value <= 2100:
        return value
    s = str(value)
    m = re.search(r"(20\d{2}|19\d{2})", s)
    if m:
        return int(m.group(1))
    return None


def year_from_identifier(ident: str | None) -> int | None:
    if not ident:
        return None
    parts = ident.split("/")
    for p in reversed(parts):
        if re.fullmatch(r"20\d{2}|19\d{2}", p):
            return int(p)
        if re.fullmatch(r"\d{2}", p):
            y = int(p)
            return 2000 + y if y < 80 else 1900 + y
    return None


def parse_date_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return None
    # ISO-ish
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        s = str(value).strip().replace("R$", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except (TypeError, ValueError):
            return None


def deterministic_entity_hash(
    cnpj: str | None,
    process: str | None,
    year: int | None,
    modalidade: str | None,
) -> str | None:
    """Rule 7 key: sha256 of cnpj|process|year|modalidade (all required)."""
    c = digits_only(cnpj) if cnpj else ""
    p = normalize_identifier(process) or ""
    y = str(year) if year else ""
    m = modalidade or ""
    if not (c and p and y and m):
        return None
    material = f"{c}|{p}|{y}|{m}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def extract_identifiers_from_text(text: str | None) -> dict[str, str | None]:
    """Pull process/edital/contract/pncp ids from free text (DOM/DOE bodies)."""
    out: dict[str, str | None] = {
        "pncp_number": None,
        "process_number": None,
        "edital_number": None,
        "contract_number": None,
        "compras_sc_id": None,
    }
    if not text:
        return out
    m = _RE_PNCP.search(text)
    if m:
        out["pncp_number"] = m.group(1)
    m = _RE_PROCESS.search(text)
    if m:
        out["process_number"] = normalize_identifier(m.group(1))
    m = _RE_EDITAL.search(text)
    if m:
        out["edital_number"] = normalize_identifier(m.group(1))
    m = _RE_CONTRATO.search(text)
    if m:
        out["contract_number"] = normalize_identifier(m.group(1))
    m = _RE_COMPRAS_URL.search(text) or _RE_SC_ID.search(text)
    if m:
        out["compras_sc_id"] = f"sc-{m.group(1)}"
    return out


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _latest_jsonl(glob_root: Path, pattern: str) -> Path | None:
    if not glob_root.exists():
        return None
    candidates = sorted(
        glob_root.rglob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def record_from_dom(raw: dict[str, Any], idx: int) -> Record:
    text = " ".join(
        str(raw.get(k) or "")
        for k in ("titulo", "texto", "act_evidence", "orgao", "entidade")
    )
    ids = extract_identifiers_from_text(text)
    codigo = str(raw.get("codigo") or raw.get("content_hash") or f"dom-{idx}")
    orgao = raw.get("orgao") or raw.get("entidade")
    cnpj = digits_only(raw.get("orgao_cnpj")) or None
    if not cnpj and ids.get("pncp_number"):
        # PNCP control number embeds orgao CNPJ as prefix
        maybe = ids["pncp_number"].split("-")[0]
        if len(maybe) == 14 and maybe.isdigit():
            cnpj = maybe
    year = (
        year_from_identifier(ids.get("process_number"))
        or year_from_identifier(ids.get("edital_number"))
        or year_from_identifier(ids.get("contract_number"))
        or extract_year(raw.get("data"))
    )
    return Record(
        source_system=SOURCE_DOM,
        source_id=codigo,
        pncp_number=ids.get("pncp_number"),
        process_number=ids.get("process_number"),
        contract_number=ids.get("contract_number"),
        edital_number=ids.get("edital_number"),
        orgao_cnpj=cnpj,
        orgao_nome=str(orgao) if orgao else None,
        orgao_nome_norm=normalize_name(str(orgao)) if orgao else None,
        year=year,
        modalidade=None,
        status=None,
        publication_date=parse_date_iso(raw.get("data") or raw.get("data_raw")),
        value=None,
        compras_sc_id=ids.get("compras_sc_id"),
        has_documents=bool(raw.get("url") or raw.get("texto_html_present")),
        metadata={"municipio": raw.get("municipio"), "category": raw.get("act_category")},
    )


def record_from_doe(raw: dict[str, Any], idx: int) -> Record:
    text = " ".join(
        str(raw.get(k) or "")
        for k in (
            "titulo",
            "texto_ou_extrato",
            "assunto",
            "orgao",
            "act_evidence",
            "tipo_ato",
        )
    )
    ids = extract_identifiers_from_text(text)
    sid = str(
        raw.get("record_hash")
        or raw.get("numero_publicacao")
        or raw.get("external_id")
        or f"doe-{idx}"
    )
    orgao = raw.get("orgao") or raw.get("unidade")
    year = (
        year_from_identifier(ids.get("process_number"))
        or year_from_identifier(ids.get("edital_number"))
        or year_from_identifier(ids.get("contract_number"))
        or extract_year(raw.get("data_publicacao") or raw.get("data_edicao"))
    )
    return Record(
        source_system=SOURCE_DOE,
        source_id=sid,
        pncp_number=ids.get("pncp_number"),
        process_number=ids.get("process_number"),
        contract_number=ids.get("contract_number"),
        edital_number=ids.get("edital_number"),
        orgao_cnpj=digits_only(raw.get("orgao_cnpj")) or None,
        orgao_nome=str(orgao) if orgao else None,
        orgao_nome_norm=normalize_name(str(orgao)) if orgao else None,
        year=year,
        modalidade=None,
        status=None,
        publication_date=parse_date_iso(
            raw.get("data_publicacao") or raw.get("data_edicao")
        ),
        value=None,
        compras_sc_id=ids.get("compras_sc_id"),
        has_documents=bool(raw.get("link_extrato") or raw.get("link_edicao")),
        metadata={"category": raw.get("act_category") or raw.get("categoria")},
    )


def record_from_compras_sc(raw: dict[str, Any], idx: int) -> Record:
    api_id = raw.get("api_id") or raw.get("source_id") or raw.get("pncp_id") or idx
    sc_id = None
    for candidate in (raw.get("source_id"), raw.get("pncp_id"), f"sc-{api_id}"):
        if candidate is None:
            continue
        s = str(candidate).lower()
        if s.startswith("sc-"):
            sc_id = s
            break
        m = _RE_SC_ID.search(s)
        if m:
            sc_id = f"sc-{m.group(1)}"
            break
    if sc_id is None and api_id is not None:
        sc_id = f"sc-{api_id}"

    pncp = normalize_pncp_number(raw.get("numero_controle_pncp") or raw.get("pncp_number"))
    # sc-* is both compras id and local pncp_id in this datalake
    if not pncp and sc_id:
        pncp = sc_id

    docs = raw.get("documentos")
    has_docs = None
    if isinstance(docs, list):
        has_docs = len(docs) > 0
    elif docs is not None:
        has_docs = bool(docs)

    year = extract_year(raw.get("ano_compra") or raw.get("data_publicacao"))
    process = normalize_identifier(raw.get("process_number") or raw.get("numero_processo"))
    edital = normalize_identifier(raw.get("edital_number") or raw.get("numero_edital"))
    contract = normalize_identifier(raw.get("contract_number") or raw.get("numero_contrato"))

    return Record(
        source_system=SOURCE_COMPRAS_SC,
        source_id=str(sc_id or api_id),
        pncp_number=pncp,
        process_number=process,
        contract_number=contract,
        edital_number=edital,
        orgao_cnpj=digits_only(raw.get("orgao_cnpj")) or None,
        orgao_nome=raw.get("orgao_razao_social") or raw.get("orgao_nome"),
        orgao_nome_norm=normalize_name(str(raw.get("orgao_razao_social") or raw.get("orgao_nome") or ""))
        or None,
        year=year,
        modalidade=normalize_modalidade(raw.get("modalidade_nome") or raw.get("modalidade_id")),
        status=normalize_status(raw.get("status") or raw.get("situacao_compra")),
        publication_date=parse_date_iso(raw.get("data_publicacao")),
        value=safe_float(raw.get("valor_total_estimado") or raw.get("valor_total")),
        compras_sc_id=sc_id,
        has_documents=has_docs,
        metadata={"api_id": raw.get("api_id"), "uf": raw.get("uf")},
    )


def record_from_pncp_bid(raw: dict[str, Any]) -> Record:
    pncp_id = str(raw.get("pncp_id") or raw.get("source_id") or "")
    numero = raw.get("numero_controle_pncp") or pncp_id
    pncp_norm = normalize_pncp_number(str(numero) if numero else None) or (
        pncp_id.lower() if pncp_id.lower().startswith("sc-") else None
    )
    sc_id = None
    if pncp_id.lower().startswith("sc-"):
        sc_id = pncp_id.lower()
    else:
        m = _RE_COMPRAS_URL.search(str(raw.get("link_pncp") or ""))
        if m:
            sc_id = f"sc-{m.group(1)}"
        else:
            m = _RE_SC_ID.search(pncp_id)
            if m:
                sc_id = f"sc-{m.group(1)}"

    process = normalize_identifier(
        raw.get("process_number") or raw.get("numero_processo")
    )
    # Some payloads embed process in informacao_complementar
    if not process and raw.get("informacao_complementar"):
        extracted = extract_identifiers_from_text(str(raw["informacao_complementar"]))
        process = extracted.get("process_number")

    year = extract_year(raw.get("ano_compra") or raw.get("data_publicacao"))
    if not year and pncp_norm and "/" in pncp_norm:
        year = extract_year(pncp_norm.split("/")[-1])

    return Record(
        source_system=SOURCE_PNCP,
        source_id=pncp_id or str(raw.get("source_id") or numero),
        pncp_number=pncp_norm,
        process_number=process,
        contract_number=normalize_identifier(raw.get("contract_number")),
        edital_number=normalize_identifier(raw.get("edital_number") or raw.get("numero_edital")),
        orgao_cnpj=digits_only(raw.get("orgao_cnpj")) or None,
        orgao_nome=raw.get("orgao_razao_social") or raw.get("orgao_nome"),
        orgao_nome_norm=normalize_name(
            str(raw.get("orgao_razao_social") or raw.get("orgao_nome") or "")
        )
        or None,
        year=year,
        modalidade=normalize_modalidade(raw.get("modalidade_nome") or raw.get("modalidade_id")),
        status=normalize_status(raw.get("situacao_compra") or raw.get("status")),
        publication_date=parse_date_iso(raw.get("data_publicacao")),
        value=safe_float(raw.get("valor_total_estimado") or raw.get("valor_total")),
        compras_sc_id=sc_id,
        has_documents=None,
        target_table="pncp_raw_bids",
        metadata={"uf": raw.get("uf"), "link_pncp": raw.get("link_pncp")},
    )


def record_from_pncp_contract(raw: dict[str, Any]) -> Record:
    contrato_id = str(raw.get("contrato_id") or raw.get("source_id") or raw.get("id") or "")
    # contrato_id often is the PNCP control number form
    pncp_norm = normalize_pncp_number(contrato_id) or normalize_pncp_number(
        raw.get("numero_controle_pncp")
    )
    cnpj = digits_only(raw.get("orgao_cnpj")) or None
    if not cnpj and pncp_norm and "-" in pncp_norm:
        maybe = pncp_norm.split("-")[0]
        if len(maybe) == 14:
            cnpj = maybe
    # contract sequential from contrato_id like CNPJ-TIPO-SEQ/YEAR
    contract_num = None
    m = re.search(r"-(\d+)/(\d{4})$", contrato_id)
    if m:
        contract_num = normalize_identifier(f"{m.group(1)}/{m.group(2)}")
    year = extract_year(raw.get("data_publicacao") or raw.get("data_assinatura"))
    if not year and m:
        year = int(m.group(2))

    return Record(
        source_system=SOURCE_PNCP,
        source_id=contrato_id,
        pncp_number=pncp_norm or contrato_id,
        process_number=normalize_identifier(raw.get("process_number")),
        contract_number=contract_num or normalize_identifier(raw.get("contract_number")),
        edital_number=normalize_identifier(raw.get("edital_number")),
        orgao_cnpj=cnpj,
        orgao_nome=raw.get("orgao_nome"),
        orgao_nome_norm=normalize_name(str(raw.get("orgao_nome") or "")) or None,
        year=year,
        modalidade=normalize_modalidade(raw.get("modalidade_nome") or raw.get("modalidade_id")),
        status=normalize_status(raw.get("status") or raw.get("situacao")),
        publication_date=parse_date_iso(
            raw.get("data_publicacao") or raw.get("data_assinatura")
        ),
        value=safe_float(raw.get("valor_total")),
        compras_sc_id=None,
        has_documents=None,
        target_table="pncp_supplier_contracts",
        metadata={"uf": raw.get("uf"), "fornecedor_cnpj": raw.get("fornecedor_cnpj")},
    )


def record_from_official_act_row(row: dict[str, Any]) -> Record:
    """Map a DB official_acts row into Record."""
    source = str(row.get("source") or "").lower()
    if "dom" in source or "ciga" in source:
        system = SOURCE_DOM
    elif "doe" in source or "dados_abertos" in source:
        system = SOURCE_DOE
    else:
        system = SOURCE_DOM if row.get("municipio") else SOURCE_DOE

    text = " ".join(
        str(row.get(k) or "")
        for k in ("title", "raw_text", "summary", "classification_evidence")
    )
    extracted = extract_identifiers_from_text(text)
    process = normalize_identifier(row.get("process_number")) or extracted.get(
        "process_number"
    )
    edital = normalize_identifier(row.get("edital_number")) or extracted.get(
        "edital_number"
    )
    contract = normalize_identifier(row.get("contract_number")) or extracted.get(
        "contract_number"
    )
    pncp = normalize_pncp_number(row.get("related_pncp_id")) or extracted.get(
        "pncp_number"
    )
    sid = str(row.get("external_id") or row.get("record_hash") or row.get("id"))
    orgao = row.get("orgao_nome")
    return Record(
        source_system=system,
        source_id=sid,
        pncp_number=pncp,
        process_number=process,
        contract_number=contract,
        edital_number=edital,
        orgao_cnpj=digits_only(row.get("orgao_cnpj")) or None,
        orgao_nome=orgao,
        orgao_nome_norm=normalize_name(str(orgao)) if orgao else None,
        year=year_from_identifier(process)
        or year_from_identifier(edital)
        or year_from_identifier(contract)
        or extract_year(row.get("publication_date")),
        modalidade=None,
        status=normalize_status(row.get("status")),
        publication_date=parse_date_iso(row.get("publication_date")),
        value=None,
        compras_sc_id=extracted.get("compras_sc_id"),
        has_documents=None,
        act_db_id=int(row["id"]) if row.get("id") is not None else None,
        metadata={"category": row.get("category"), "db_source": row.get("source")},
    )


def load_dom_records(limit: int | None = None) -> list[Record]:
    path = _latest_jsonl(ROOT / "output" / "ciga_dom", "publications.jsonl")
    if not path:
        _logger.warning("No DOM publications.jsonl found")
        return []
    raws = _read_jsonl(path, limit=limit)
    return [record_from_dom(r, i) for i, r in enumerate(raws)]


def load_doe_records(limit: int | None = None) -> list[Record]:
    path = _latest_jsonl(ROOT / "data" / "normalized" / "dados_abertos_sc", "*.jsonl")
    if not path:
        _logger.warning("No DOE normalized jsonl found")
        return []
    raws = _read_jsonl(path, limit=limit)
    return [record_from_doe(r, i) for i, r in enumerate(raws)]


def load_compras_sc_records(limit: int | None = None) -> list[Record]:
    root = ROOT / "output" / "sc_compras"
    if not root.exists():
        _logger.warning("No Compras SC output directory found")
        return []
    # Merge all licitacoes.jsonl (dedupe by source_id / api_id), newest first
    candidates = sorted(
        root.rglob("licitacoes.jsonl"),
        key=lambda p: (p.stat().st_mtime, p.stat().st_size),
        reverse=True,
    )
    if not candidates:
        _logger.warning("No Compras SC licitacoes.jsonl found")
        return []
    seen: set[str] = set()
    raws: list[dict[str, Any]] = []
    for path in candidates:
        for row in _read_jsonl(path, limit=None):
            key = str(
                row.get("source_id")
                or row.get("pncp_id")
                or row.get("api_id")
                or row.get("content_hash")
                or id(row)
            )
            if key in seen:
                continue
            seen.add(key)
            raws.append(row)
            if limit is not None and len(raws) >= limit:
                break
        if limit is not None and len(raws) >= limit:
            break
    return [record_from_compras_sc(r, i) for i, r in enumerate(raws)]


def _resolve_dsn() -> str | None:
    for key in ("LOCAL_DATALAKE_DSN", "DATABASE_URL", "TEST_DSN"):
        val = os.getenv(key)
        if val:
            return val
    return None


def load_pncp_from_db(
    limit: int | None = None,
    uf: str = "SC",
    ensure_ids: Sequence[str] | None = None,
) -> list[Record]:
    dsn = _resolve_dsn()
    if not dsn:
        _logger.warning("No DSN; skipping PNCP DB load")
        return []
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        _logger.warning("psycopg2 not available; skipping PNCP DB load")
        return []

    records: list[Record] = []
    seen_keys: set[str] = set()
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("PNCP DB connect failed: %s", exc)
        return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Explicitly fetch Compras SC / PNCP ids we already know about
            ensure = [str(x) for x in (ensure_ids or []) if x]
            if ensure:
                cur.execute(
                    """
                    SELECT pncp_id, numero_controle_pncp, source_id, orgao_cnpj,
                           orgao_razao_social, modalidade_id, modalidade_nome,
                           ano_compra, data_publicacao, valor_total_estimado,
                           situacao_compra, uf, link_pncp, informacao_complementar
                    FROM pncp_raw_bids
                    WHERE is_active IS DISTINCT FROM FALSE
                      AND (
                        pncp_id = ANY(%s)
                        OR source_id = ANY(%s)
                        OR numero_controle_pncp = ANY(%s)
                      )
                    """,
                    (ensure, ensure, ensure),
                )
                for row in cur.fetchall():
                    rec = record_from_pncp_bid(dict(row))
                    if rec.key() not in seen_keys:
                        seen_keys.add(rec.key())
                        records.append(rec)

            lim_sql = f"LIMIT {int(limit)}" if limit else ""
            # LIMIT sanitized via int(); uf parameterized
            cur.execute(
                f"""
                SELECT pncp_id, numero_controle_pncp, source_id, orgao_cnpj,
                       orgao_razao_social, modalidade_id, modalidade_nome,
                       ano_compra, data_publicacao, valor_total_estimado,
                       situacao_compra, uf, link_pncp, informacao_complementar
                FROM pncp_raw_bids
                WHERE (uf = %s OR uf IS NULL)
                  AND (is_active IS DISTINCT FROM FALSE)
                ORDER BY data_publicacao DESC NULLS LAST
                {lim_sql}
                """,  # noqa: S608
                (uf,),
            )
            for row in cur.fetchall():
                rec = record_from_pncp_bid(dict(row))
                if rec.key() not in seen_keys:
                    seen_keys.add(rec.key())
                    records.append(rec)

            # Contracts — use remaining budget if limit set
            c_limit = None
            if limit is not None:
                c_limit = max(limit, 100)
            lim_c = f"LIMIT {int(c_limit)}" if c_limit else "LIMIT 5000"
            # noqa: S608 — lim_c uses int() only; uf is parameterized
            cur.execute(
                f"""
                SELECT id, contrato_id, orgao_cnpj, orgao_nome, valor_total,
                       data_publicacao, data_assinatura, uf, source_id,
                       fornecedor_cnpj
                FROM pncp_supplier_contracts
                WHERE uf = %s
                  AND (is_active IS DISTINCT FROM FALSE)
                ORDER BY data_publicacao DESC NULLS LAST
                {lim_c}
                """,  # noqa: S608
                (uf,),
            )
            for row in cur.fetchall():
                rec = record_from_pncp_contract(dict(row))
                if rec.key() not in seen_keys:
                    seen_keys.add(rec.key())
                    records.append(rec)
    finally:
        conn.close()
    return records


def load_official_acts_from_db(limit: int | None = None) -> list[Record]:
    dsn = _resolve_dsn()
    if not dsn:
        return []
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return []
    try:
        conn = psycopg2.connect(dsn)
    except Exception:  # noqa: BLE001
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.official_acts')")
            reg = cur.fetchone()
            if not reg or reg[0] is None:
                return []
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            lim = f"LIMIT {int(limit)}" if limit else "LIMIT 10000"
            # noqa: S608 — lim uses int() only
            cur.execute(
                f"""
                SELECT id, source, external_id, record_hash, title, raw_text, summary,
                       classification_evidence, orgao_nome, orgao_cnpj,
                       process_number, edital_number, contract_number,
                       related_pncp_id, status, publication_date, category,
                       municipio, uf
                FROM official_acts
                WHERE is_active IS DISTINCT FROM FALSE
                ORDER BY publication_date DESC NULLS LAST
                {lim}
                """  # noqa: S608
            )
            return [record_from_official_act_row(dict(r)) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def detect_conflicts(left: Record, right: Record) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Compare matched pair for field divergences.

    Returns (conflicts, divergent_fields, needs_review).
    """
    conflicts: list[dict[str, Any]] = []
    divergent: list[str] = []

    def note(field_name: str, a: Any, b: Any, kind: str) -> None:
        conflicts.append(
            {
                "field": field_name,
                "left": a,
                "right": b,
                "kind": kind,
                "left_system": left.source_system,
                "right_system": right.source_system,
            }
        )
        divergent.append(field_name)

    # Status
    ls, rs = left.status, right.status
    if ls and rs and ls != rs:
        note("status", ls, rs, "status_divergence")

    # Dates
    ld, rd = left.publication_date, right.publication_date
    if ld and rd and ld != rd:
        note("publication_date", ld, rd, "date_divergence")

    # Values
    lv, rv = left.value, right.value
    if lv is not None and rv is not None:
        abs_diff = abs(lv - rv)
        rel = abs_diff / max(abs(lv), abs(rv), 1e-9)
        if abs_diff > _VALUE_ABS_TOL and rel > _VALUE_REL_TOL:
            note("value", lv, rv, "value_divergence")

    # CNPJ mismatch when both present (serious)
    lc, rc = left.orgao_cnpj, right.orgao_cnpj
    if lc and rc and lc != rc:
        # allow same root (8 digits)
        if lc[:8] != rc[:8]:
            note("orgao_cnpj", lc, rc, "cnpj_conflict")

    needs_review = any(
        c["kind"] in ("cnpj_conflict", "value_divergence", "status_divergence")
        for c in conflicts
    ) or (len(conflicts) >= 2)
    return conflicts, divergent, needs_review


# ---------------------------------------------------------------------------
# Index + matching engine
# ---------------------------------------------------------------------------


def _index_key_parts(*parts: Any) -> str | None:
    cleaned: list[str] = []
    for p in parts:
        if p is None or p == "":
            return None
        cleaned.append(str(p))
    return "|".join(cleaned)


class MatchIndex:
    """Multi-key indexes for deterministic matching."""

    def __init__(self) -> None:
        self.by_pncp: dict[str, list[Record]] = defaultdict(list)
        self.by_process_cnpj: dict[str, list[Record]] = defaultdict(list)
        self.by_process_year_mod: dict[str, list[Record]] = defaultdict(list)
        self.by_contract_cnpj: dict[str, list[Record]] = defaultdict(list)
        self.by_edital_year_cnpj: dict[str, list[Record]] = defaultdict(list)
        self.by_edital_year_orgao: dict[str, list[Record]] = defaultdict(list)
        self.by_compras_sc: dict[str, list[Record]] = defaultdict(list)
        self.by_hash: dict[str, list[Record]] = defaultdict(list)
        self.all: list[Record] = []

    def add(self, rec: Record) -> None:
        self.all.append(rec)
        if rec.pncp_number:
            self.by_pncp[rec.pncp_number].append(rec)
        k = _index_key_parts(rec.process_number, rec.orgao_cnpj)
        if k:
            self.by_process_cnpj[k].append(rec)
        k = _index_key_parts(rec.process_number, rec.year, rec.modalidade)
        if k:
            self.by_process_year_mod[k].append(rec)
        k = _index_key_parts(rec.contract_number, rec.orgao_cnpj)
        if k:
            self.by_contract_cnpj[k].append(rec)
        k = _index_key_parts(rec.edital_number, rec.year, rec.orgao_cnpj)
        if k:
            self.by_edital_year_cnpj[k].append(rec)
        k = _index_key_parts(rec.edital_number, rec.year, rec.orgao_nome_norm)
        if k:
            self.by_edital_year_orgao[k].append(rec)
        if rec.compras_sc_id:
            self.by_compras_sc[rec.compras_sc_id].append(rec)
        h = deterministic_entity_hash(
            rec.orgao_cnpj, rec.process_number, rec.year, rec.modalidade
        )
        if h:
            self.by_hash[h].append(rec)


def _candidates_for_rule(rule: str, probe: Record, index: MatchIndex) -> list[Record]:
    if rule == "pncp_number_exact":
        if not probe.pncp_number:
            return []
        return list(index.by_pncp.get(probe.pncp_number, []))
    if rule == "process_number_orgao_cnpj":
        k = _index_key_parts(probe.process_number, probe.orgao_cnpj)
        return list(index.by_process_cnpj.get(k, [])) if k else []
    if rule == "process_number_year_modalidade":
        k = _index_key_parts(probe.process_number, probe.year, probe.modalidade)
        return list(index.by_process_year_mod.get(k, [])) if k else []
    if rule == "contract_number_orgao_cnpj":
        k = _index_key_parts(probe.contract_number, probe.orgao_cnpj)
        return list(index.by_contract_cnpj.get(k, [])) if k else []
    if rule == "edital_number_year_orgao_cnpj":
        k = _index_key_parts(probe.edital_number, probe.year, probe.orgao_cnpj)
        return list(index.by_edital_year_cnpj.get(k, [])) if k else []
    if rule == "edital_number_year_orgao_name":
        if probe.orgao_cnpj:
            # Prefer CNPJ rule; skip name when CNPJ is present to avoid dual hits
            return []
        k = _index_key_parts(probe.edital_number, probe.year, probe.orgao_nome_norm)
        return list(index.by_edital_year_orgao.get(k, [])) if k else []
    if rule == "compras_sc_id_crosswalk":
        if not probe.compras_sc_id:
            return []
        return list(index.by_compras_sc.get(probe.compras_sc_id, []))
    if rule == "deterministic_hash":
        h = deterministic_entity_hash(
            probe.orgao_cnpj, probe.process_number, probe.year, probe.modalidade
        )
        return list(index.by_hash.get(h, [])) if h else []
    return []


def _justify(rule: str, probe: Record, cand: Record) -> str:
    parts = {
        "pncp_number_exact": f"pncp_number={probe.pncp_number!r}",
        "process_number_orgao_cnpj": (
            f"process={probe.process_number!r} cnpj={probe.orgao_cnpj!r}"
        ),
        "process_number_year_modalidade": (
            f"process={probe.process_number!r} year={probe.year} "
            f"modalidade={probe.modalidade!r}"
        ),
        "contract_number_orgao_cnpj": (
            f"contract={probe.contract_number!r} cnpj={probe.orgao_cnpj!r}"
        ),
        "edital_number_year_orgao_cnpj": (
            f"edital={probe.edital_number!r} year={probe.year} "
            f"cnpj={probe.orgao_cnpj!r}"
        ),
        "edital_number_year_orgao_name": (
            f"edital={probe.edital_number!r} year={probe.year} "
            f"orgao={probe.orgao_nome_norm!r}"
        ),
        "compras_sc_id_crosswalk": f"compras_sc_id={probe.compras_sc_id!r}",
        "deterministic_hash": (
            f"hash(cnpj|process|year|modalidade) "
            f"cnpj={probe.orgao_cnpj!r} process={probe.process_number!r} "
            f"year={probe.year} modalidade={probe.modalidade!r}"
        ),
    }
    base = parts.get(rule, rule)
    return (
        f"rule={rule} score={RULE_SCORES[rule]} keys=({base}) "
        f"left={probe.key()} right={cand.key()}"
    )


def match_record_against_index(
    probe: Record,
    index: MatchIndex,
    *,
    exclude_systems: set[str] | None = None,
) -> MatchResult | None:
    """Return best match for probe against index using priority rules.

    Only the first (highest priority) rule that yields candidates is used;
    among candidates, first non-self distinct-system hit is kept. Multiple
    candidates under the same rule → needs_review.
    """
    exclude_systems = exclude_systems or set()
    for rule in _RULE_ORDER:
        cands = [
            c
            for c in _candidates_for_rule(rule, probe, index)
            if c.key() != probe.key()
            and c.source_system != probe.source_system
            and c.source_system not in exclude_systems
        ]
        # de-dupe by key preserving order
        seen: set[str] = set()
        unique: list[Record] = []
        for c in cands:
            if c.key() in seen:
                continue
            seen.add(c.key())
            unique.append(c)
        if not unique:
            continue

        # Prefer PNCP targets when available
        unique.sort(
            key=lambda r: (
                0 if r.source_system == SOURCE_PNCP else 1,
                r.key(),
            )
        )
        best = unique[0]
        conflicts, divergent, needs = detect_conflicts(probe, best)
        if len(unique) > 1:
            needs = True
            conflicts.append(
                {
                    "field": "_candidates",
                    "left": probe.key(),
                    "right": [u.key() for u in unique[:10]],
                    "kind": "ambiguous_match",
                    "left_system": probe.source_system,
                    "right_system": best.source_system,
                }
            )
        return MatchResult(
            left_id=probe.key(),
            right_id=best.key(),
            left_system=probe.source_system,
            right_system=best.source_system,
            left_source_id=probe.source_id,
            right_source_id=best.source_id,
            rule=rule,
            score=RULE_SCORES[rule],
            justification=_justify(rule, probe, best),
            conflicts=conflicts,
            divergent_fields=divergent,
            needs_review=needs,
            reversible=True,
        )
    return None


def match_pair(left: Record, right: Record) -> MatchResult | None:
    """Match two explicit records (unit-test helper) using the same rules."""
    idx = MatchIndex()
    idx.add(right)
    return match_record_against_index(left, idx)


def reconcile_collections(
    pncp: Sequence[Record],
    doe: Sequence[Record],
    dom: Sequence[Record],
    compras: Sequence[Record],
) -> list[MatchResult]:
    """Reconcile non-PNCP sources against PNCP (+ crosswalk compras↔pncp)."""
    pncp_index = MatchIndex()
    for r in pncp:
        pncp_index.add(r)

    # Also index compras for DOE/DOM crosswalk via sc-id and reverse PNCP
    side_index = MatchIndex()
    for r in pncp:
        side_index.add(r)
    for r in compras:
        side_index.add(r)

    matches: list[MatchResult] = []
    pair_seen: set[tuple[str, str, str]] = set()

    def _accept(m: MatchResult | None) -> None:
        if not m:
            return
        a, b = sorted([m.left_id, m.right_id])
        key = (a, b, m.rule)
        if key in pair_seen:
            return
        # Also collapse same pair under different rules — keep first (higher score)
        pair_only = (a, b, "")
        if any(p[0] == a and p[1] == b for p in pair_seen):
            return
        pair_seen.add(key)
        pair_seen.add(pair_only)
        matches.append(m)

    # Compras SC → PNCP
    for rec in compras:
        _accept(match_record_against_index(rec, pncp_index))

    # DOM / DOE → PNCP + Compras
    for rec in list(dom) + list(doe):
        _accept(match_record_against_index(rec, side_index))

    return matches


# ---------------------------------------------------------------------------
# Report assembly + persistence
# ---------------------------------------------------------------------------


def build_report(
    *,
    run_id: str,
    mode: str,
    started_at: str,
    pncp: Sequence[Record],
    doe: Sequence[Record],
    dom: Sequence[Record],
    compras: Sequence[Record],
    matches: Sequence[MatchResult],
    errors: list[str] | None = None,
    notes: list[str] | None = None,
) -> ReconciliationReport:
    matched_ids: set[str] = set()
    for m in matches:
        matched_ids.add(m.left_id)
        matched_ids.add(m.right_id)

    def only_count(recs: Sequence[Record]) -> int:
        return sum(1 for r in recs if r.key() not in matched_ids)

    rules: dict[str, int] = defaultdict(int)
    status_div = date_div = value_div = needs = 0
    missing_docs = 0
    for m in matches:
        rules[m.rule] += 1
        if m.needs_review:
            needs += 1
        for c in m.conflicts:
            kind = c.get("kind")
            if kind == "status_divergence":
                status_div += 1
            elif kind == "date_divergence":
                date_div += 1
            elif kind == "value_divergence":
                value_div += 1

    # missing documents: matched compras_sc without docs
    compras_by_key = {r.key(): r for r in compras}
    for m in matches:
        for kid in (m.left_id, m.right_id):
            rec = compras_by_key.get(kid)
            if rec and rec.has_documents is False:
                missing_docs += 1

    # Unique entity pairs reconciled (count matches)
    reconciled = len(matches)

    claims_allowed = [
        "initial_deterministic_reconciliation_smoke_or_sample",
        "match_rows_reversible_file_backed",
        f"rules_used={','.join(sorted(rules))}" if rules else "rules_used=none",
        "sources_attempted=pncp,doe,dom,compras_sc",
    ]
    claims_forbidden = [
        "90_day_pilot_success",
        "3_year_backfill_complete",
        "full_coverage_claimed",
        "fuzzy_text_similarity_linking",
        "production_sync_complete",
        "official_acts_table_fully_populated",
    ]

    return ReconciliationReport(
        run_id=run_id,
        mode=mode,
        started_at=started_at,
        sources_loaded={
            "pncp": len(pncp),
            "doe": len(doe),
            "dom": len(dom),
            "compras_sc": len(compras),
        },
        matches=list(matches),
        reconciled_count=reconciled,
        pncp_only=only_count(pncp),
        doe_only=only_count(doe),
        dom_only=only_count(dom),
        compras_sc_only=only_count(compras),
        status_divergences=status_div,
        date_divergences=date_div,
        value_divergences=value_div,
        missing_documents=missing_docs,
        needs_review_count=needs,
        rules_applied=dict(rules),
        claims_allowed=claims_allowed,
        claims_forbidden=claims_forbidden,
        errors=list(errors or []),
        notes=list(notes or []),
    )


def write_outputs(report: ReconciliationReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report.completed_at = datetime.now(UTC).isoformat()
    report.output_dir = str(out_dir)

    matches_path = out_dir / "matches.jsonl"
    with matches_path.open("w", encoding="utf-8") as fh:
        for m in report.matches:
            row = asdict(m)
            row["reversible"] = True
            row["delete_instruction"] = (
                "Remove this line or set is_active=false; "
                "DB: DELETE FROM official_act_matches WHERE metadata->>'match_id' = match_id"
            )
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    report_dict = report.to_dict()
    report_json = out_dir / "report.json"
    report_json.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    md = _render_markdown(report)
    report_md = out_dir / "report.md"
    report_md.write_text(md, encoding="utf-8")

    evidence = build_run_evidence(
        run_id=report.run_id,
        started_at=report.started_at,
        completed_at=report.completed_at,
        command="scripts.matching.official_acts_reconcile",
        args={"mode": report.mode},
        output_path=str(report_json),
        status="ok" if not report.errors else "partial",
        errors=report.errors,
        counts_before={},
        counts_after={
            "reconciled_count": report.reconciled_count,
            "pncp_only": report.pncp_only,
            "doe_only": report.doe_only,
            "dom_only": report.dom_only,
            "compras_sc_only": report.compras_sc_only,
            "matches": len(report.matches),
            "sources_loaded": report.sources_loaded,
        },
        criteria={
            "deterministic_rules_only": True,
            "rules": RULE_PRIORITY,
            "no_fuzzy_text_linking": True,
        },
        claims_allowed=report.claims_allowed,
        claims_forbidden=report.claims_forbidden,
        mode=report.mode,
        rules_applied=report.rules_applied,
        divergences={
            "status": report.status_divergences,
            "date": report.date_divergences,
            "value": report.value_divergences,
            "missing_documents": report.missing_documents,
        },
    )
    # refresh output hash after write
    evidence["output_hash"] = sha256_file(report_json)
    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "report_json": report_json,
        "report_md": report_md,
        "matches": matches_path,
        "evidence": evidence_path,
    }


def _render_markdown(report: ReconciliationReport) -> str:
    lines = [
        f"# Reconciliation report — `{report.run_id}`",
        "",
        f"- **mode**: `{report.mode}`",
        f"- **started_at**: {report.started_at}",
        f"- **completed_at**: {report.completed_at}",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| reconciled (match pairs) | {report.reconciled_count} |",
        f"| PNCP-only | {report.pncp_only} |",
        f"| DOE-only | {report.doe_only} |",
        f"| DOM-only | {report.dom_only} |",
        f"| Compras SC-only | {report.compras_sc_only} |",
        f"| status divergences | {report.status_divergences} |",
        f"| date divergences | {report.date_divergences} |",
        f"| value divergences | {report.value_divergences} |",
        f"| missing documents | {report.missing_documents} |",
        f"| needs review | {report.needs_review_count} |",
        f"| DB matches written | {report.db_matches_written} |",
        "",
        "## Sources loaded",
        "",
    ]
    for k, v in report.sources_loaded.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Rules applied", ""]
    if report.rules_applied:
        for rule, n in sorted(report.rules_applied.items(), key=lambda x: -x[1]):
            lines.append(f"- `{rule}` (score={RULE_SCORES.get(rule, '?')}): {n}")
    else:
        lines.append("- _(none)_")
    lines += ["", "## Claims allowed", ""]
    for c in report.claims_allowed:
        lines.append(f"- ✅ {c}")
    lines += ["", "## Claims forbidden", ""]
    for c in report.claims_forbidden:
        lines.append(f"- 🚫 {c}")
    if report.notes:
        lines += ["", "## Notes", ""]
        for n in report.notes:
            lines.append(f"- {n}")
    if report.errors:
        lines += ["", "## Errors", ""]
        for e in report.errors:
            lines.append(f"- ⚠️ {e}")
    lines += [
        "",
        "## Sample matches (up to 20)",
        "",
    ]
    for m in report.matches[:20]:
        lines.append(
            f"- `{m.match_id}` rule=`{m.rule}` score={m.score} "
            f"{m.left_id} ↔ {m.right_id}"
            f"{' **needs_review**' if m.needs_review else ''}"
        )
        lines.append(f"  - {m.justification}")
    lines.append("")
    return "\n".join(lines)


def maybe_write_db_matches(
    matches: Sequence[MatchResult],
    records_by_key: dict[str, Record],
    *,
    run_id: str,
) -> int:
    """Persist reversible match rows via OfficialActsStore when act_db_id present."""
    written = 0
    try:
        from scripts.schema.official_acts import OfficialActsStore
    except Exception:  # noqa: BLE001
        return 0
    dsn = _resolve_dsn()
    if not dsn:
        return 0
    try:
        store = OfficialActsStore(dsn)
    except Exception:  # noqa: BLE001
        return 0

    for m in matches:
        left = records_by_key.get(m.left_id)
        right = records_by_key.get(m.right_id)
        if not left or not right:
            continue
        act = left if left.act_db_id else right if right.act_db_id else None
        target = right if act is left else left if act is right else None
        if not act or not act.act_db_id or not target:
            continue
        if target.source_system != SOURCE_PNCP:
            # only link acts → PNCP targets in DB helper
            if left.source_system == SOURCE_PNCP:
                act, target = right, left
            else:
                continue
            if not act.act_db_id:
                continue
        target_table = target.target_table or "pncp_raw_bids"
        try:
            store.add_match(
                act.act_db_id,
                match_type="bid" if target_table == "pncp_raw_bids" else "contract",
                target_table=target_table,
                target_id=str(target.source_id),
                match_method=m.rule,
                match_score=m.score,
                match_confidence="high" if m.score >= 0.9 and not m.needs_review else "medium",
                matched_by="official_acts_reconcile",
                metadata={
                    "match_id": m.match_id,
                    "run_id": run_id,
                    "justification": m.justification,
                    "conflicts": m.conflicts,
                    "needs_review": m.needs_review,
                    "reversible": True,
                },
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            _logger.warning("add_match failed for %s: %s", m.match_id, exc)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_reconciliation(
    mode: str = "smoke",
    limit: int | None = None,
    uf: str = "SC",
    write_db: bool = True,
) -> ReconciliationReport:
    started = datetime.now(UTC).isoformat()
    run_id = new_run_id("reconcile")
    errors: list[str] = []
    notes: list[str] = []

    if mode == "smoke":
        limit = limit if limit is not None else 200
    elif mode == "sample":
        limit = limit if limit is not None else 1000
    elif mode == "full":
        limit = limit  # may be None
    else:
        raise ValueError(f"Unknown mode: {mode}")

    notes.append(
        "Deterministic identifier matching only; no pure text-similarity linking."
    )
    notes.append("This run does NOT claim 90-day pilot success or 3-year backfill.")

    # Prefer DB official_acts when populated; always load file-based sources.
    official_db = load_official_acts_from_db(limit=limit)
    if official_db:
        notes.append(f"Loaded {len(official_db)} rows from official_acts DB.")
        doe = [r for r in official_db if r.source_system == SOURCE_DOE]
        dom = [r for r in official_db if r.source_system == SOURCE_DOM]
        # Still merge file extras if DB sparse
        if len(doe) == 0:
            doe = load_doe_records(limit=limit)
            notes.append("DOE loaded from files (none in official_acts).")
        if len(dom) == 0:
            dom = load_dom_records(limit=limit)
            notes.append("DOM loaded from files (none in official_acts).")
    else:
        notes.append("official_acts empty/unavailable — reconciling from files + PNCP.")
        try:
            doe = load_doe_records(limit=limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"doe_load: {exc}")
            doe = []
        try:
            dom = load_dom_records(limit=limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dom_load: {exc}")
            dom = []

    try:
        compras = load_compras_sc_records(limit=limit)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"compras_sc_load: {exc}")
        compras = []

    ensure_ids: list[str] = []
    for rec in compras:
        if rec.compras_sc_id:
            ensure_ids.append(rec.compras_sc_id)
        if rec.pncp_number:
            ensure_ids.append(rec.pncp_number)
        ensure_ids.append(rec.source_id)
    # Also pull ids mentioned in DOM/DOE text
    for rec in list(doe) + list(dom):
        if rec.compras_sc_id:
            ensure_ids.append(rec.compras_sc_id)
        if rec.pncp_number:
            ensure_ids.append(rec.pncp_number)

    try:
        pncp = load_pncp_from_db(
            limit=limit,
            uf=uf,
            ensure_ids=sorted(set(ensure_ids)),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pncp_load: {exc}")
        pncp = []

    matches = reconcile_collections(pncp, doe, dom, compras)
    report = build_report(
        run_id=run_id,
        mode=mode,
        started_at=started,
        pncp=pncp,
        doe=doe,
        dom=dom,
        compras=compras,
        matches=matches,
        errors=errors,
        notes=notes,
    )

    out_dir = OUTPUT_ROOT / run_id
    write_outputs(report, out_dir)

    if write_db:
        by_key = {r.key(): r for r in list(pncp) + list(doe) + list(dom) + list(compras)}
        report.db_matches_written = maybe_write_db_matches(
            matches, by_key, run_id=run_id
        )
        # refresh report files with db count
        write_outputs(report, out_dir)

    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Reconcile DOE/DOM/Compras SC with PNCP (deterministic rules)."
    )
    p.add_argument(
        "--mode",
        choices=("smoke", "sample", "full"),
        default="smoke",
        help="smoke=small sample, sample=medium, full=no default limit",
    )
    p.add_argument("--limit", type=int, default=None, help="Max records per source")
    p.add_argument("--uf", default="SC", help="UF filter for PNCP load")
    p.add_argument(
        "--no-db-write",
        action="store_true",
        help="Do not write official_act_matches even if act ids exist",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Load .env if present
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
        except ImportError:
            # minimal dotenv
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

    report = run_reconciliation(
        mode=args.mode,
        limit=args.limit,
        uf=args.uf,
        write_db=not args.no_db_write,
    )
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "mode": report.mode,
                "reconciled_count": report.reconciled_count,
                "sources_loaded": report.sources_loaded,
                "pncp_only": report.pncp_only,
                "doe_only": report.doe_only,
                "dom_only": report.dom_only,
                "compras_sc_only": report.compras_sc_only,
                "rules_applied": report.rules_applied,
                "status_divergences": report.status_divergences,
                "date_divergences": report.date_divergences,
                "value_divergences": report.value_divergences,
                "missing_documents": report.missing_documents,
                "needs_review_count": report.needs_review_count,
                "output_dir": report.output_dir,
                "claims_allowed": report.claims_allowed,
                "claims_forbidden": report.claims_forbidden,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not report.errors else 0  # soft-fail: still produce report


if __name__ == "__main__":
    sys.exit(main())
