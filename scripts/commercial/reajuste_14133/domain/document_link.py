"""Contract ↔ document binding gate (fail-closed).

Before any document may prove regime, clause, index or data-base, the document
must pass a cumulative link check against the analysed contract. A CONFLICT
invalidates all signals extracted from that document and blocks score use.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

DOCUMENT_LINK_VERIFIED = "DOCUMENT_LINK_VERIFIED"
DOCUMENT_LINK_PARTIAL = "DOCUMENT_LINK_PARTIAL"
DOCUMENT_LINK_CONFLICT = "DOCUMENT_LINK_CONFLICT"
DOCUMENT_LINK_UNVERIFIED = "DOCUMENT_LINK_UNVERIFIED"

DOCUMENT_LINK_STATES = (
    DOCUMENT_LINK_VERIFIED,
    DOCUMENT_LINK_PARTIAL,
    DOCUMENT_LINK_CONFLICT,
    DOCUMENT_LINK_UNVERIFIED,
)

# Sector contradiction tokens: document sector vs contract object sector
_PHARMA_DOC = (
    "lisdexanfetamina",
    "lisdexanfetamine",
    "medicamento",
    "farmaceutic",
    "farmaco",
    "principio ativo",
    "anvisa",
    "psicoativo",
    "psicoestimulante",
)
_SOFTWARE_DOC = (
    "software",
    "licenca de uso",
    "licenciamento de software",
    "sistema de gestao",
    "saas",
    "tecnologia da informacao",
    "infraestrutura de ti",
)
_VEHICLE_DOC = (
    "locacao de veiculos",
    "locacao de veiculo",
    "frota de veiculos",
    "veiculos especiais",
    "aluguel de veiculos",
)
_MINING_DOC = (
    "fornecimento de agregado",
    "fornecimento de brita",
    "fornecimento de areia",
    "mineracao sem obra",
)
_CONSTRUCTION_OBJ = (
    "obra",
    "obras",
    "paviment",
    "construcao",
    "empreitada",
    "terraplen",
    "saneamento",
    "drenagem",
    "edific",
    "infraestrutura",
    "rodovia",
    "asfalt",
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _token_overlap(a: str, b: str) -> float:
    """Jaccard-like token overlap on content words (≥4 chars)."""
    ta = {t for t in a.split() if len(t) >= 4}
    tb = {t for t in b.split() if len(t) >= 4}
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def semantic_object_similarity(contract_object: str | None, doc_text: str | None) -> float:
    """0..1 similarity between contract object and document excerpt/title/body."""
    a = _norm(contract_object)
    b = _norm(doc_text)
    if not a or not b:
        return 0.0
    # Direct containment boosts
    if len(a) >= 20 and a[:80] in b:
        return max(0.7, _token_overlap(a, b[:4000]))
    return _token_overlap(a, b[:8000])


def sector_contradiction(contract_object: str | None, doc_text: str | None) -> list[str]:
    """Return reason codes when document sector clearly conflicts with obra object."""
    c = _norm(contract_object)
    d = _norm(doc_text)
    if not d:
        return []
    reasons: list[str] = []
    has_construction_obj = any(t in c for t in _CONSTRUCTION_OBJ) if c else False
    # Pharma doc vs construction contract (or any non-pharma contract)
    if any(t in d for t in _PHARMA_DOC):
        if has_construction_obj or not any(t in c for t in _PHARMA_DOC):
            reasons.append("pharma_document_vs_non_pharma_contract")
    if any(t in d for t in _SOFTWARE_DOC) and has_construction_obj:
        # software mention alone in construction docs can be false; require heavy software
        if any(
            t in d
            for t in (
                "licenciamento de software",
                "licenca de uso de software",
                "sistema de gestao de obras",
            )
        ) and not any(
            t in d for t in ("execucao de obra", "empreitada", "pavimentacao", "construcao civil")
        ):
            reasons.append("software_document_vs_construction_contract")
    if any(t in d for t in _VEHICLE_DOC) and has_construction_obj:
        if not any(t in d for t in ("obra", "paviment", "empreitada", "construcao")):
            reasons.append("vehicle_rental_document_vs_construction_contract")
    if any(t in d for t in _MINING_DOC) and has_construction_obj:
        reasons.append("aggregate_supply_document_without_obra_execution")
    return reasons


@dataclass
class DocumentLinkResult:
    status: str
    checks: dict[str, bool | None]
    checks_passed: int
    checks_failed: int
    checks_unknown: int
    reasons: list[str] = field(default_factory=list)
    signals_usable: bool = False
    similarity: float = 0.0
    sector_conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_document_link(
    *,
    contract_numero_controle_pncp_compra: str | None = None,
    contract_orgao_cnpj: str | None = None,
    contract_ano: int | str | None = None,
    contract_sequencial: int | str | None = None,
    contract_processo: str | None = None,
    contract_numero: str | None = None,
    contract_object: str | None = None,
    contract_contratacao_object: str | None = None,
    contract_fornecedor: str | None = None,
    contract_fornecedor_cnpj: str | None = None,
    # Document-side identifiers / content
    doc_numero_controle_pncp_compra: str | None = None,
    doc_orgao_cnpj: str | None = None,
    doc_ano: int | str | None = None,
    doc_sequencial: int | str | None = None,
    doc_processo: str | None = None,
    doc_numero_contrato: str | None = None,
    doc_object_or_title: str | None = None,
    doc_text: str | None = None,
    doc_fornecedor_mentions: str | None = None,
    min_similarity_verified: float = 0.12,
    min_similarity_partial: float = 0.05,
) -> DocumentLinkResult:
    """Cumulatively validate that a document belongs to the analysed contract.

    States:
      DOCUMENT_LINK_VERIFIED  — strong multi-key match, no sector conflict
      DOCUMENT_LINK_PARTIAL   — some keys match, none conflict, weak object similarity
      DOCUMENT_LINK_CONFLICT  — any hard identifier conflict or sector contradiction
      DOCUMENT_LINK_UNVERIFIED — insufficient evidence to link
    """
    checks: dict[str, bool | None] = {
        "numeroControlePncpCompra": None,
        "cnpj_orgao": None,
        "ano_sequencial": None,
        "numero_processo": None,
        "numero_contrato": None,
        "objeto_contrato": None,
        "objeto_contratacao": None,
        "fornecedor_ou_consorcio": None,
        "similaridade_semantica": None,
        "sem_contradicao_setorial": None,
    }
    reasons: list[str] = []

    # --- Identifier checks (True match / False conflict / None unknown) ---
    c_compra = _norm(contract_numero_controle_pncp_compra).replace(" ", "")
    d_compra = _norm(doc_numero_controle_pncp_compra).replace(" ", "")
    if c_compra and d_compra:
        checks["numeroControlePncpCompra"] = c_compra == d_compra or c_compra in d_compra or d_compra in c_compra
        if not checks["numeroControlePncpCompra"]:
            reasons.append("numeroControlePncpCompra_mismatch")

    c_org = _digits(contract_orgao_cnpj)
    d_org = _digits(doc_orgao_cnpj)
    if len(c_org) == 14 and len(d_org) == 14:
        checks["cnpj_orgao"] = c_org == d_org
        if not checks["cnpj_orgao"]:
            # Soft when compra control number already matches (linked via meta)
            if checks.get("numeroControlePncpCompra") is True:
                checks["cnpj_orgao"] = None
                reasons.append("orgao_cnpj_differs_but_compra_linked")
            else:
                reasons.append("orgao_cnpj_mismatch")
    elif len(c_org) == 14 and doc_text:
        # soft: cnpj appears in text
        if c_org in re.sub(r"\D", "", doc_text):
            checks["cnpj_orgao"] = True
        # leave unknown if not found — not auto-conflict

    if contract_ano is not None and contract_sequencial is not None and doc_ano is not None and doc_sequencial is not None:
        try:
            checks["ano_sequencial"] = (
                int(contract_ano) == int(doc_ano) and int(contract_sequencial) == int(doc_sequencial)
            )
            if not checks["ano_sequencial"]:
                reasons.append("ano_sequencial_mismatch")
        except (TypeError, ValueError):
            checks["ano_sequencial"] = None

    c_proc = _norm(contract_processo).replace(" ", "")
    d_proc = _norm(doc_processo).replace(" ", "")
    if c_proc and d_proc:
        checks["numero_processo"] = c_proc == d_proc or c_proc in d_proc or d_proc in c_proc
        if not checks["numero_processo"]:
            reasons.append("processo_mismatch")
    elif c_proc and doc_text:
        if c_proc in _norm(doc_text).replace(" ", ""):
            checks["numero_processo"] = True

    c_num = _norm(contract_numero).replace(" ", "")
    d_num = _norm(doc_numero_contrato).replace(" ", "")
    if c_num and d_num:
        checks["numero_contrato"] = c_num == d_num or c_num in d_num or d_num in c_num
        if not checks["numero_contrato"]:
            reasons.append("numero_contrato_mismatch")
    elif c_num and doc_text:
        if c_num in _norm(doc_text).replace(" ", ""):
            checks["numero_contrato"] = True

    # Object similarity
    blob = " ".join(filter(None, [doc_object_or_title or "", (doc_text or "")[:12000]]))
    sim_contract = semantic_object_similarity(contract_object, blob)
    sim_contratacao = semantic_object_similarity(contract_contratacao_object, blob)
    sim = max(sim_contract, sim_contratacao)
    if contract_object or contract_contratacao_object:
        checks["objeto_contrato"] = sim_contract >= min_similarity_partial if contract_object else None
        checks["objeto_contratacao"] = (
            sim_contratacao >= min_similarity_partial if contract_contratacao_object else None
        )
        checks["similaridade_semantica"] = sim >= min_similarity_partial
        if sim < min_similarity_partial and blob.strip():
            reasons.append("low_object_similarity")
    else:
        checks["similaridade_semantica"] = None

    # Supplier mention
    forn_norm = _norm(contract_fornecedor)
    forn_cnpj = _digits(contract_fornecedor_cnpj)
    doc_forn = _norm(doc_fornecedor_mentions or "") + " " + _norm(doc_text or "")[:8000]
    if forn_norm or forn_cnpj:
        ok_name = False
        ok_cnpj = False
        if forn_norm and len(forn_norm) >= 6:
            # use significant tokens of company name
            tokens = [t for t in forn_norm.split() if len(t) >= 4 and t not in {"ltda", "eireli", "s/a", "sa", "e"}]
            if tokens:
                hits = sum(1 for t in tokens[:4] if t in doc_forn)
                ok_name = hits >= max(1, min(2, len(tokens[:4])))
        if len(forn_cnpj) == 14 and forn_cnpj in re.sub(r"\D", "", doc_forn):
            ok_cnpj = True
        if ok_name or ok_cnpj:
            checks["fornecedor_ou_consorcio"] = True
        elif blob.strip() and (forn_norm or forn_cnpj):
            # Unknown is safer than hard-fail: many editais omit the eventual winner
            checks["fornecedor_ou_consorcio"] = None
            if len(_norm(doc_text or "")) > 400:
                reasons.append("fornecedor_not_mentioned_in_document_soft")

    # Sector contradiction — hard conflict
    sector = sector_contradiction(contract_object or contract_contratacao_object, blob)
    if sector:
        checks["sem_contradicao_setorial"] = False
        reasons.extend(sector)
    else:
        checks["sem_contradicao_setorial"] = True

    failed = [k for k, v in checks.items() if v is False]
    passed = [k for k, v in checks.items() if v is True]
    unknown = [k for k, v in checks.items() if v is None]

    # Hard identifier conflicts (sector + explicit compra/processo/contract number)
    # ano_sequencial alone is hard only when compra control also mismatches/unknown
    hard_keys = {
        "numeroControlePncpCompra",
        "cnpj_orgao",
        "numero_processo",
        "numero_contrato",
        "sem_contradicao_setorial",
    }
    hard_fail = [k for k in failed if k in hard_keys]
    if checks.get("ano_sequencial") is False and checks.get("numeroControlePncpCompra") is not True:
        hard_fail.append("ano_sequencial")

    if hard_fail or "pharma_document_vs_non_pharma_contract" in reasons:
        return DocumentLinkResult(
            status=DOCUMENT_LINK_CONFLICT,
            checks=checks,
            checks_passed=len(passed),
            checks_failed=len(failed),
            checks_unknown=len(unknown),
            reasons=reasons + ["document_link_conflict"],
            signals_usable=False,
            similarity=sim,
            sector_conflicts=sector,
        )

    # Verified: enough positive keys + similarity + no sector conflict
    id_hits = sum(
        1
        for k in (
            "numeroControlePncpCompra",
            "cnpj_orgao",
            "ano_sequencial",
            "numero_processo",
            "numero_contrato",
            "fornecedor_ou_consorcio",
        )
        if checks.get(k) is True
    )
    if (
        checks.get("sem_contradicao_setorial") is True
        and sim >= min_similarity_verified
        and id_hits >= 2
        and len(failed) == 0
    ):
        return DocumentLinkResult(
            status=DOCUMENT_LINK_VERIFIED,
            checks=checks,
            checks_passed=len(passed),
            checks_failed=len(failed),
            checks_unknown=len(unknown),
            reasons=reasons or ["document_link_verified"],
            signals_usable=True,
            similarity=sim,
            sector_conflicts=sector,
        )

    if id_hits >= 1 and checks.get("sem_contradicao_setorial") is True and len(failed) == 0:
        return DocumentLinkResult(
            status=DOCUMENT_LINK_PARTIAL,
            checks=checks,
            checks_passed=len(passed),
            checks_failed=len(failed),
            checks_unknown=len(unknown),
            reasons=reasons or ["document_link_partial"],
            signals_usable=True,  # partial may support weak signals; score policy decides
            similarity=sim,
            sector_conflicts=sector,
        )

    if sim >= min_similarity_verified and checks.get("sem_contradicao_setorial") is True and id_hits >= 1:
        return DocumentLinkResult(
            status=DOCUMENT_LINK_PARTIAL,
            checks=checks,
            checks_passed=len(passed),
            checks_failed=len(failed),
            checks_unknown=len(unknown),
            reasons=reasons or ["document_link_partial_similarity"],
            signals_usable=True,
            similarity=sim,
            sector_conflicts=sector,
        )

    return DocumentLinkResult(
        status=DOCUMENT_LINK_UNVERIFIED,
        checks=checks,
        checks_passed=len(passed),
        checks_failed=len(failed),
        checks_unknown=len(unknown),
        reasons=reasons or ["document_link_unverified"],
        signals_usable=False,
        similarity=sim,
        sector_conflicts=sector,
    )


def invalidate_signals_on_conflict(scan_dict: dict[str, Any], link: DocumentLinkResult) -> dict[str, Any]:
    """Wipe documentary signals when link is CONFLICT. Returns a copy-like dict."""
    out = dict(scan_dict)
    if link.status != DOCUMENT_LINK_CONFLICT:
        out["document_link"] = link.as_dict()
        out["signals_usable"] = link.signals_usable
        return out
    out["document_link"] = link.as_dict()
    out["signals_usable"] = False
    out["regime_14133_mention"] = False
    out["regime_8666_mention"] = False
    out["regime_rdc_mention"] = False
    out["regime_conflict"] = False
    out["reajuste_clause_mention"] = False
    out["data_base_mention"] = False
    out["apostila_mention"] = False
    out["already_adjusted_hint"] = False
    out["index_in_clause"] = []
    out["index_candidates"] = []
    out["index_outside_clause_only"] = []
    out["docs_accessible"] = False
    out["text_extracted"] = False
    out["official_text_extracted"] = False
    out["invalidated_by_document_link_conflict"] = True
    out["limitations"] = list(out.get("limitations") or []) + [
        "DOCUMENT_LINK_CONFLICT: all signals from this document invalidated",
        *link.reasons,
    ]
    # Keep evidences but mark unusable
    evs = []
    for e in out.get("evidences") or []:
        if isinstance(e, dict):
            e = dict(e)
            e["usable_for_score"] = False
            e["document_link_status"] = DOCUMENT_LINK_CONFLICT
            evs.append(e)
        else:
            evs.append(e)
    out["evidences"] = evs
    return out
