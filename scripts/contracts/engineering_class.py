"""Persisted engineering class per contract (#544).

Canonical authority for commercial engineering classes. Reuses
``contract_relevance.normalize_text`` / ``neutralize_evidence``; does not
treat projeto as out-of-scope. Views must consume this table, not regex.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.commercial_leads.contract_relevance import neutralize_evidence, normalize_text

RULE_VERSION = "engineering-class-v1"

ENGINEERING_CLASSES: tuple[str, ...] = (
    "OBRA_EXECUCAO",
    "OBRA_COM_PROJETO",
    "PROJETO_ENGENHARIA",
    "FISCALIZACAO_GERENCIAMENTO",
    "MANUTENCAO_PREDIAL_INFRA",
    "INSTALACOES",
    "FORNECIMENTO_COM_INSTALACAO",
    "NAO_ENGENHARIA",
)

ORGAO_SPAN_RE = re.compile(
    r"\b(?:secretaria|ministerio|autarquia|prefeitura|camara municipal|"
    r"departamento|superintendencia|companhia|agencia)"
    r"(?:\s+(?:municipal|estadual|federal|metropolitana))?"
    r"(?:\s+(?:de|da|do|das|dos))?"
    r"(?:\s+[a-z]+){0,8}"
)

SUPPLIER_EXCLUDE_RE = re.compile(
    r"\b(fundacao|universidade|faculdade|concessionaria|advocacia|"
    r"escritorio de advocacia|sociedade de advogados)\b"
)

INTEGRATED_RE = re.compile(r"\b(semi[-\s]?integrad|contratacao integrada|regime integrado|integrada)\b")

PROJETO_PHRASES = (
    "elaboracao de projeto",
    "elaboracao de projetos",
    "projeto executivo",
    "projeto estrutural",
    "projeto de engenharia",
    "projetos de engenharia",
    "projeto basico de engenharia",
    "projeto basico e executivo",
    "anteprojeto de engenharia",
)
PROJETO_NEGATIVE = (
    "projeto cultural",
    "projeto de software",
    "projeto pedagogico",
    "projeto social",
    "projeto de pesquisa",
    "projeto academico",
)

FISCAL_PHRASES = ("fiscalizacao de obra", "supervisao de obra", "gerenciamento de obra", "acompanhamento de obra")
FISCAL_TOKENS = ("fiscalizacao", "supervisao", "gerenciamento")
OBRA_CONTEXT = (
    "obra",
    "obras",
    "engenharia",
    "paviment",
    "edific",
    "construcao",
    "saneamento",
    "drenagem",
)
FISCAL_NEGATIVE = ("publicidade", "propaganda", "midia", "marketing", "comunicacao social")

MANUT_PHRASES = (
    "manutencao predial",
    "manutencao de edificio",
    "manutencao rodoviaria",
    "conservacao rodoviaria",
    "manutencao de infraestrutura",
)
MANUT_NEGATIVE = (
    "equipamento medico",
    "equipamentos medicos",
    "respirador",
    "engenharia clinica",
    "hospitalar",
    "manutencao de veiculo",
    "manutencao de impressora",
)

INSTAL_PHRASES = (
    "instalacoes prediais",
    "instalacoes hidraulicas",
    "instalacoes eletricas",
    "instalacao eletrica predial",
    "instalacao hidraulica",
)
SUPPLY_INSTALL_PHRASES = (
    "fornecimento e instalacao",
    "fornecimento com instalacao",
    "fornecimento, instalacao",
)

OBRA_PHRASES = (
    "execucao de obra",
    "execucao de obras",
    "obra de engenharia",
    "construcao civil",
    "pavimentacao",
    "terraplenagem",
    "drenagem urbana",
    "edificacao",
    "empreitada",
    "construcao de",
    "reforma predial",
    "recuperacao estrutural",
)

ENGINEERING_CATEGORIA = {
    "obras",
    "servicos de engenharia",
    "servico de engenharia",
    "obras e servicos de engenharia",
}


@dataclass
class EngineeringClassResult:
    engineering_class: str
    confidence: float
    categories: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION
    computed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["class"] = self.engineering_class
        return payload


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def neutralize_orgao_spans(norm: str) -> str:
    return ORGAO_SPAN_RE.sub(" ", norm)


def _hits(norm: str, phrases: tuple[str, ...]) -> list[str]:
    return [p for p in phrases if p in norm]


def _official_engineering_categoria(nome: str | None) -> bool:
    if not nome:
        return False
    return normalize_text(nome) in ENGINEERING_CATEGORIA


def _regime_integrated(regime: str | None) -> bool:
    if not regime:
        return False
    return bool(INTEGRATED_RE.search(normalize_text(regime)))


def classify_engineering_class(
    *,
    objeto: str | None,
    fornecedor_nome: str | None = None,
    categoria_processo_nome: str | None = None,
    regime_execucao_nome: str | None = None,
    tipo_contrato_nome: str | None = None,
    srp: bool | None = None,
    cnae_principal: str | None = None,
) -> EngineeringClassResult:
    """Return a versioned class. Never infers class from objeto regex in SQL."""
    computed = _now()
    raw_norm = normalize_text(objeto)
    norm = neutralize_orgao_spans(neutralize_evidence(objeto))
    evidence: list[str] = []
    categories: list[str] = []
    supplier = normalize_text(fornecedor_nome)
    tipo = normalize_text(tipo_contrato_nome)

    if supplier and SUPPLIER_EXCLUDE_RE.search(supplier) and not _hits(norm, OBRA_PHRASES):
        return EngineeringClassResult(
            "NAO_ENGENHARIA",
            0.92,
            ["supplier_excluded"],
            [f"supplier:{SUPPLIER_EXCLUDE_RE.search(supplier).group(0)}"],
            computed_at=computed,
        )

    if any(neg in norm for neg in FISCAL_NEGATIVE) and not _hits(norm, OBRA_PHRASES):
        return EngineeringClassResult(
            "NAO_ENGENHARIA",
            0.9,
            ["publicidade"],
            ["publicidade_or_midia"],
            computed_at=computed,
        )

    if any(neg in norm for neg in MANUT_NEGATIVE):
        return EngineeringClassResult(
            "NAO_ENGENHARIA",
            0.9,
            ["clinical_or_equipment"],
            _hits(norm, MANUT_NEGATIVE) or ["manutencao_nao_predial"],
            computed_at=computed,
        )

    if any(neg in norm for neg in PROJETO_NEGATIVE) and not _hits(norm, PROJETO_PHRASES):
        return EngineeringClassResult(
            "NAO_ENGENHARIA",
            0.88,
            ["projeto_nao_engenharia"],
            _hits(norm, PROJETO_NEGATIVE),
            computed_at=computed,
        )

    integrated = _regime_integrated(regime_execucao_nome) or bool(INTEGRATED_RE.search(norm))
    if _regime_integrated(regime_execucao_nome):
        evidence.append("regime_execucao_oficial")
        categories.append("regime_integrado")

    projeto_hits = _hits(norm, PROJETO_PHRASES)
    fiscal_phrase_hits = _hits(norm, FISCAL_PHRASES)
    fiscal_token = any(tok in norm for tok in FISCAL_TOKENS)
    obra_ctx = any(tok in norm for tok in OBRA_CONTEXT)
    manut_hits = _hits(norm, MANUT_PHRASES)
    instal_hits = _hits(norm, INSTAL_PHRASES)
    supply_hits = _hits(norm, SUPPLY_INSTALL_PHRASES)
    obra_hits = _hits(norm, OBRA_PHRASES)
    cat_eng = _official_engineering_categoria(categoria_processo_nome)
    if cat_eng:
        evidence.append("categoria_processo_oficial")
        categories.append("categoria_processo")

    def _conf(base: float) -> float:
        score = base
        if cat_eng:
            score = min(1.0, score + 0.08)
        if cnae_principal and any(k in normalize_text(cnae_principal) for k in ("obra", "engenharia", "construcao")):
            score = min(1.0, score + 0.05)
            evidence.append("cnae")
        if tipo in {"empenho", "ata de registro de precos"} or srp is True:
            score = max(0.0, score - 0.15)
            evidence.append("empenho_or_srp_penalty")
        return round(score, 3)

    if integrated and (obra_hits or cat_eng or projeto_hits or obra_ctx):
        return EngineeringClassResult(
            "OBRA_COM_PROJETO",
            _conf(0.86 if _regime_integrated(regime_execucao_nome) else 0.8),
            categories + ["integrado"],
            evidence + (["regime_sem_keyword_objeto"] if not INTEGRATED_RE.search(raw_norm) else ["integrado_no_objeto"]),
            computed_at=computed,
        )

    if projeto_hits:
        return EngineeringClassResult(
            "PROJETO_ENGENHARIA",
            _conf(0.88),
            categories + ["projeto"],
            evidence + projeto_hits,
            computed_at=computed,
        )

    if fiscal_phrase_hits or (fiscal_token and obra_ctx):
        return EngineeringClassResult(
            "FISCALIZACAO_GERENCIAMENTO",
            _conf(0.86 if fiscal_phrase_hits else 0.78),
            categories + ["fiscalizacao"],
            evidence + (fiscal_phrase_hits or ["fiscalizacao+obra_context"]),
            computed_at=computed,
        )
    if fiscal_token and not obra_ctx:
        return EngineeringClassResult(
            "NAO_ENGENHARIA",
            0.84,
            ["fiscalizacao_sem_obra"],
            ["fiscalizacao_without_obra_context"],
            computed_at=computed,
        )

    if manut_hits:
        return EngineeringClassResult(
            "MANUTENCAO_PREDIAL_INFRA",
            _conf(0.84),
            categories + ["manutencao"],
            evidence + manut_hits,
            computed_at=computed,
        )

    if supply_hits:
        return EngineeringClassResult(
            "FORNECIMENTO_COM_INSTALACAO",
            _conf(0.82),
            categories + ["fornecimento_instalacao"],
            evidence + supply_hits,
            computed_at=computed,
        )

    if instal_hits:
        return EngineeringClassResult(
            "INSTALACOES",
            _conf(0.83),
            categories + ["instalacoes"],
            evidence + instal_hits,
            computed_at=computed,
        )

    if obra_hits:
        return EngineeringClassResult(
            "OBRA_EXECUCAO",
            _conf(0.87),
            categories + ["obra"],
            evidence + obra_hits,
            computed_at=computed,
        )

    if cat_eng:
        return EngineeringClassResult(
            "OBRA_EXECUCAO",
            0.62,
            categories,
            evidence + ["categoria_only_low_object_evidence"],
            computed_at=computed,
        )

    return EngineeringClassResult(
        "NAO_ENGENHARIA",
        0.7,
        ["no_engineering_evidence"],
        ["no_class_evidence"],
        computed_at=computed,
    )


def attach_engineering_class(record: dict[str, Any]) -> dict[str, Any]:
    result = classify_engineering_class(
        objeto=record.get("objeto_contrato") or record.get("objeto"),
        fornecedor_nome=record.get("fornecedor_nome"),
        categoria_processo_nome=record.get("categoria_processo_nome"),
        regime_execucao_nome=record.get("regime_execucao_nome"),
        tipo_contrato_nome=record.get("tipo_contrato_nome"),
        srp=record.get("srp"),
        cnae_principal=record.get("cnae_principal"),
    )
    record["engineering_class"] = result.engineering_class
    record["engineering_confidence"] = result.confidence
    record["engineering_categories"] = result.categories
    record["engineering_evidence"] = result.evidence
    record["engineering_rule_version"] = result.rule_version
    record["engineering_computed_at"] = result.computed_at
    return record


def stamp_engineering_class_labels(conn: Any, records: Iterable[Mapping[str, Any]]) -> int:
    payload = []
    for raw in records:
        contrato_id = str(raw.get("contrato_id") or "").strip()
        if not contrato_id:
            continue
        row = dict(raw)
        if not row.get("engineering_class"):
            attach_engineering_class(row)
        payload.append(
            {
                "contrato_id": contrato_id,
                "engineering_class": row.get("engineering_class"),
                "confidence": row.get("engineering_confidence"),
                "categories": row.get("engineering_categories") or [],
                "evidence": row.get("engineering_evidence") or [],
                "rule_version": row.get("engineering_rule_version") or RULE_VERSION,
                "computed_at": row.get("engineering_computed_at"),
            }
        )
    if not payload:
        return 0
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT contrato_id FROM apply_contract_engineering_class(%s::jsonb)",
            (json.dumps(payload, default=str),),
        )
        rows = cur.fetchall() or []
        return len(rows)
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
