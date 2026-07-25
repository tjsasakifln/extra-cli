"""Deterministic supplier sector-fit classification for CONFENGE.

Uses multi-evidence: legal name, trade name, contract objects concentration,
optional CNAE, and negative sector markers. Does NOT treat contract keyword
alone as proof the supplier is an engineering firm.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial_leads.contract_relevance import (
    classify_contract_relevance,
    normalize_text,
)

RULE_VERSION = "supplier-sector-fit-v1"

# Classes required by goal
CLASS_CONFIRMED = "CONFIRMED_ENGINEERING"
CLASS_STRONG = "STRONG_ENGINEERING_FIT"
CLASS_POSSIBLE = "POSSIBLE_ENGINEERING_FIT"
CLASS_OUT = "OUT_OF_SCOPE"
CLASS_UNKNOWN = "UNKNOWN"
CLASS_CONFLICTING = "CONFLICTING"

PUBLISHABLE = frozenset({CLASS_CONFIRMED, CLASS_STRONG})

# Name markers — positive
NAME_ENGINEERING: tuple[str, ...] = (
    "engenharia",
    "engenheir",
    "construtora",
    "construcoes",
    "construcao",
    "empreiteira",
    "paviment",
    "terraplenagem",
    "saneamento",
    "estruturas",
    "geotecnia",
    "topografia",
    "arquitetura e engenharia",
    "projetos de engenharia",
    "consultoria e projetos",
    "obras publicas",
    "infraestrutura",
)

# Name markers — strong out of scope
NAME_OUT_OF_SCOPE: tuple[str, ...] = (
    "autopeca",
    "auto peca",
    "autopecas",
    "pecas e servicos",
    "comercio de pneus",
    "pneus",
    "tratorpeca",
    "tratorpecas",
    "auto eletrica",
    "autoeletrica",
    "churrascaria",
    "pizzaria",
    "restaurante",
    "padaria",
    "supermercado",
    "farmacia",
    "drogaria",
    "terceirizacao",
    "terceirizacoes",
    "limpeza",
    "conservacao e limpeza",
    "vigilancia",
    "seguranca patrimonial",
    "locacoes de equipamentos",
    "locacao de equipamentos",
    "locadora",
    "transportes",
    "logistica",
    "frete",
    "materiais p construcao",
    "materiais de construcao",
    "comercio de materiais",
    "comercio varejista",
    "comercio de",
    "comercio e",
    " distribuidora",
    "patrometal",
    "pinturas",
    "tintas",
    "posto de combustivel",
    "combustiveis",
    "informatica",
    "tecnologia da informacao",
    "software",
    "contabilidade",
    "contabil",
    "advocacia",
    "advogados",
    "imobiliario",
    "imobiliarios",
)

# CNAE prefixes (2-digit / 4-digit) associated with construction & technical services
CNAE_ENGINEERING_PREFIXES: tuple[str, ...] = (
    "41",  # construção de edifícios
    "42",  # obras de infraestrutura
    "43",  # serviços especializados para construção
    "7111",  # serviços de arquitetura
    "7112",  # serviços de engenharia
    "7113",  # testes e análises técnicas
    "7120",
)

CNAE_OUT_PREFIXES: tuple[str, ...] = (
    "45",  # comércio e reparação de veículos
    "46",  # comércio por atacado
    "47",  # comércio varejista
    "49",  # transporte terrestre
    "56",  # alimentação
    "62",  # TI
    "63",
    "81",  # serviços para edifícios e paisagismo (limpeza etc.) often out
    "78",  # seleção e agenciamento de mão de obra
    "80",  # segurança/vigilância
)

# Concentration threshold for STRONG without CNAE
STRONG_CONCENTRATION = 0.60
STRONG_MIN_RELEVANT = 2
CONFIRMED_CONCENTRATION = 0.75


@dataclass
class SectorFitDecision:
    classification: str
    confidence: float
    rule_version: str = RULE_VERSION
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    run_id: str | None = None
    relevant_contract_ratio: float = 0.0
    relevant_contract_count: int = 0
    total_contract_count: int = 0
    name_hits_positive: list[str] = field(default_factory=list)
    name_hits_negative: list[str] = field(default_factory=list)
    cnae_principal: str | None = None
    cnae_secondary: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def publishable(self) -> bool:
        return self.classification in PUBLISHABLE


def _norm_name(name: str | None) -> str:
    return normalize_text(name)


def _hits(norm: str, patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if p in norm]


def _cnae_digits(cnae: str | None) -> str:
    if not cnae:
        return ""
    return re.sub(r"\D", "", str(cnae))


def _cnae_matches(cnae: str | None, prefixes: tuple[str, ...]) -> bool:
    d = _cnae_digits(cnae)
    if not d:
        return False
    return any(d.startswith(p) for p in prefixes)


def classify_supplier_sector_fit(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
    object_field: str = "objeto_contrato",
    run_id: str | None = None,
) -> SectorFitDecision:
    """Classify supplier sector fit with full provenance."""
    contracts = contracts or []
    cnaes_secundarios = cnaes_secundarios or []
    name_norm = f"{_norm_name(razao_social)} {_norm_name(nome_fantasia)}".strip()
    pos_name = _hits(name_norm, NAME_ENGINEERING)
    neg_name = _hits(name_norm, NAME_OUT_OF_SCOPE)

    evidence: list[dict[str, Any]] = []
    conflicting: list[dict[str, Any]] = []
    sources: list[str] = ["razao_social"]
    reasons: list[str] = []

    if pos_name:
        evidence.append({"type": "legal_name_positive", "hits": pos_name})
        reasons.append("name_engineering_marker")
    if neg_name:
        conflicting.append({"type": "legal_name_negative", "hits": neg_name})
        reasons.append("name_out_of_scope_marker")

    # Contract object analysis
    relevant = 0
    total = 0
    object_labels: list[str] = []
    for row in contracts:
        total += 1
        obj = None
        if isinstance(row, dict):
            obj = row.get(object_field) or row.get("objeto") or row.get("objeto_contrato")
        else:
            obj = getattr(row, "objeto", None) or getattr(row, "objeto_contrato", None)
        rel = classify_contract_relevance(obj)
        object_labels.append(rel.status)
        if rel.status == "PASS":
            relevant += 1
            evidence.append(
                {
                    "type": "relevant_contract",
                    "objeto": (str(obj)[:160] if obj else None),
                    "reason_codes": rel.reason_codes,
                    "strong_hits": rel.strong_hits[:5],
                }
            )
        elif rel.status == "FAIL" and rel.negative_context:
            conflicting.append(
                {
                    "type": "out_of_scope_contract",
                    "objeto": (str(obj)[:160] if obj else None),
                    "negative": rel.negative_context[:5],
                }
            )
    ratio = (relevant / total) if total else 0.0
    if total:
        sources.append("contract_objects")
        evidence.append(
            {
                "type": "contract_concentration",
                "relevant": relevant,
                "total": total,
                "ratio": round(ratio, 4),
            }
        )

    # CNAE
    cnae_eng = _cnae_matches(cnae_principal, CNAE_ENGINEERING_PREFIXES)
    cnae_out = _cnae_matches(cnae_principal, CNAE_OUT_PREFIXES)
    sec_eng = any(_cnae_matches(c, CNAE_ENGINEERING_PREFIXES) for c in cnaes_secundarios)
    if cnae_principal:
        sources.append("cnae_principal")
        evidence.append({"type": "cnae_principal", "value": cnae_principal, "engineering": cnae_eng, "out": cnae_out})
    if cnaes_secundarios:
        sources.append("cnae_secondary")

    # Decision tree
    classification = CLASS_UNKNOWN
    confidence = 0.2

    # Supply/commerce of materials — contracts about "materiais de construção"
    # do not make a retailer an engineering firm.
    supply_only_markers = (
        "aquisicao de materiais",
        "fornecimento de materiais",
        "materiais de construcao",
        "materiais para construcao",
    )
    supply_hits = 0
    eng_service_hits = 0
    for row in contracts:
        raw_obj = None
        if isinstance(row, dict):
            raw_obj = row.get(object_field) or row.get("objeto") or row.get("objeto_contrato")
        else:
            raw_obj = getattr(row, "objeto", None) or getattr(row, "objeto_contrato", None)
        obj = normalize_text(raw_obj)
        if any(m in obj for m in supply_only_markers):
            supply_hits += 1
        if any(
            m in obj
            for m in (
                "execucao de obra",
                "servicos de engenharia",
                "pavimentacao",
                "construcao civil",
                "empreitada",
                "fiscalizacao de obra",
                "projeto de engenharia",
            )
        ):
            eng_service_hits += 1

    # Hard OUT: strong name negative without engineering name/CNAE/contracts
    if neg_name and not pos_name and not cnae_eng and ratio < 0.85:
        classification = CLASS_OUT
        confidence = 0.9
        reasons.append("name_out_dominates")
    elif neg_name and not pos_name and eng_service_hits == 0:
        classification = CLASS_OUT
        confidence = 0.88
        reasons.append("name_out_no_engineering_services")
    elif supply_hits > 0 and eng_service_hits == 0 and not pos_name and not cnae_eng:
        classification = CLASS_OUT
        confidence = 0.82
        reasons.append("materials_supply_only")
    elif cnae_out and not cnae_eng and ratio < STRONG_CONCENTRATION:
        classification = CLASS_OUT
        confidence = 0.85
        reasons.append("cnae_out_of_scope")
    elif cnae_eng and ratio >= 0.4:
        classification = CLASS_CONFIRMED
        confidence = 0.95
        reasons.append("cnae_principal_engineering_plus_contracts")
    elif cnae_eng and pos_name:
        classification = CLASS_CONFIRMED
        confidence = 0.92
        reasons.append("cnae_and_name_engineering")
    elif cnae_eng and not neg_name:
        classification = CLASS_CONFIRMED
        confidence = 0.88
        reasons.append("cnae_principal_engineering")
    elif sec_eng and ratio >= CONFIRMED_CONCENTRATION and relevant >= STRONG_MIN_RELEVANT and not neg_name:
        classification = CLASS_CONFIRMED
        confidence = 0.86
        reasons.append("secondary_cnae_plus_dominant_contracts")
    elif (
        ratio >= STRONG_CONCENTRATION
        and relevant >= STRONG_MIN_RELEVANT
        and not neg_name
        and not cnae_out
    ) or (
        ratio >= 0.99
        and relevant >= 1
        and not neg_name
        and not cnae_out
        and eng_service_hits >= 1
    ):
        classification = CLASS_STRONG
        confidence = 0.8 if pos_name else 0.72
        reasons.append("strong_contract_concentration")
        if pos_name:
            reasons.append("name_supports")
    elif pos_name and ratio >= 0.4 and relevant >= 1 and not neg_name:
        classification = CLASS_STRONG
        confidence = 0.75
        reasons.append("name_engineering_plus_relevant_contracts")
    elif pos_name and neg_name:
        classification = CLASS_CONFLICTING
        confidence = 0.55
        reasons.append("name_conflict")
    elif neg_name and ratio >= STRONG_CONCENTRATION:
        classification = CLASS_CONFLICTING
        confidence = 0.5
        reasons.append("name_out_but_contracts_engineering")
    elif ratio >= 0.35 and relevant >= 1 and not neg_name:
        classification = CLASS_POSSIBLE
        confidence = 0.55
        reasons.append("some_relevant_contracts")
    elif pos_name and total == 0:
        classification = CLASS_POSSIBLE
        confidence = 0.45
        reasons.append("name_only_no_contracts")
    elif total == 0 and not pos_name and not cnae_principal:
        classification = CLASS_UNKNOWN
        confidence = 0.15
        reasons.append("no_evidence")
    elif ratio == 0 and total > 0 and not pos_name:
        # contracts loaded but none engineering-relevant
        if neg_name or any(
            classify_contract_relevance(
                (r.get(object_field) if isinstance(r, dict) else None)
            ).negative_context
            for r in contracts[:5]
        ):
            classification = CLASS_OUT
            confidence = 0.8
            reasons.append("contracts_not_engineering")
        else:
            classification = CLASS_UNKNOWN
            confidence = 0.3
            reasons.append("no_relevant_contracts")
    else:
        classification = CLASS_POSSIBLE if relevant else CLASS_UNKNOWN
        confidence = 0.4 if relevant else 0.25
        reasons.append("default_low_evidence")

    # Multiservice / mixed: relevant minority with strong out markers
    if total >= 3 and 0 < ratio < 0.35 and neg_name:
        classification = CLASS_OUT
        confidence = max(confidence, 0.75)
        reasons.append("multiservice_out_dominant")

    return SectorFitDecision(
        classification=classification,
        confidence=round(confidence, 4),
        evidence=evidence[:40],
        reason_codes=reasons,
        conflicting_evidence=conflicting[:20],
        data_sources=sources,
        run_id=run_id,
        relevant_contract_ratio=round(ratio, 4),
        relevant_contract_count=relevant,
        total_contract_count=total,
        name_hits_positive=pos_name,
        name_hits_negative=neg_name,
        cnae_principal=cnae_principal,
        cnae_secondary=list(cnaes_secundarios),
    )


def sector_fit_histogram(decisions: list[SectorFitDecision]) -> dict[str, int]:
    c: Counter[str] = Counter(d.classification for d in decisions)
    return dict(c)
