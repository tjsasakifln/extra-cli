"""Contract constants for public-read-bofu-evidence/1.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA = "public-read-bofu-evidence/1.0"
CONTRACT_VERSION = "v1.0.0"
PACK_VERSION = "1.0"
CONTRACT_PATH = "docs/contracts/bofu-evidence-v1.json"
NATIONAL_SCHEMA = "national-coverage/1.0"
NATIONAL_CONTRACT_PATH = Path("docs/contracts/national-coverage/national-coverage-v1.json")
COMPARABLE_ACCEPTED_SCHEMAS = frozenset(
    {
        "comparable-contracts/1.0",
        "public-read-comparable-contracts/1.0",
        "authority-handoff-contract-comparables/1.0",
    }
)
NATIONAL_VERDICTS = frozenset({"NATIONAL_CLAIM_AUTHORIZED", "PARTIAL", "NOT_MEASURED", "BLOCKED"})
FORBIDDEN_NATIONAL_SOURCES = frozenset(
    {
        "extra_1093",
        "extra-1093",
        "extra_1093_monitored",
        "extra-canonical-seed",
        "sc_public_entities.raio_200km",
        "icp_commercial",
        "observed_corpus",
        "raw_national",
        "row_count",
    }
)


class BofuInputError(ValueError):
    """Expired, incompatible, missing, or fixture-as-live input."""


FAMILIES: tuple[str, ...] = (
    "reequilibrio",
    "aditivos",
    "medicoes_glosas",
    "atrasos_prorrogacoes",
    "defesa_tecnica",
    "orcamento_bdi",
    "pre_licitacao_bid_room",
    "gestao_acompanhamento",
)

FAMILY_QUESTIONS: dict[str, str] = {
    "reequilibrio": (
        "Quais eventos documentados de reequilibrio economico-financeiro constam no recorte do contrato focal?"
    ),
    "aditivos": "Quais termos aditivos documentados constam no recorte do contrato focal?",
    "medicoes_glosas": "Quais medicoes e glosas documentadas constam no recorte do contrato focal?",
    "atrasos_prorrogacoes": (
        "Quais prorrogacoes ou registros de atraso documentados constam no recorte do contrato focal?"
    ),
    "defesa_tecnica": "Quais pecas tecnicas documentadas constam no recorte do contrato focal?",
    "orcamento_bdi": (
        "Qual e a distribuicao observada de valor integral nominal (BRL_TOTAL) "
        "entre contratos comparaveis de pavimentacao em paralelepipedo?"
    ),
    "pre_licitacao_bid_room": "Quais artefatos de Bid Room / pre-licitacao documentados constam no recorte?",
    "gestao_acompanhamento": ("Quais eventos de gestao ou acompanhamento contratual documentados constam no recorte?"),
}

EPISTEMIC_CLASSES = frozenset({"FACT", "CALCULATION", "OBSERVATION", "UNKNOWN"})
PACK_STATES = frozenset({"READY", "HOLD", "REJECT"})
COMPARABLE_PERTINENT_FAMILIES = frozenset({"orcamento_bdi"})
COMPARABLE_UNIT = "BRL_TOTAL"
COMPARABLE_METRIC = "valor_integral_nominal"
FRESHNESS_MAX_AGE_HOURS = 48

REQUIRED_PACK_FIELDS: tuple[str, ...] = (
    "schema",
    "pack_id",
    "version",
    "family",
    "question",
    "as_of",
    "expires",
    "expires_at",
    "source",
    "method",
    "coverage",
    "claims",
    "calculations",
    "limitations",
    "prohibited_claims",
    "state",
    "publication",
    "index",
    "national",
    "content_hash",
)

FORBIDDEN_FIELDS = frozenset(
    {
        "has_right",
        "irregular",
        "fraude",
        "should_adjust",
        "seo_title",
        "cta",
        "INDEX",
        "imbalance",
        "loss",
        "direito",
        "desequilibrio",
    }
)

FORBIDDEN_TOKENS = (
    "has_right",
    "irregular",
    "fraude",
    "should_adjust",
    "seo_title",
    "cta",
    "INDEX",
    "custo/km",
    "nacional completo",
)

UNIT_PROMOTION_UNITS = frozenset(
    {
        "BRL_KM",
        "BRL_PER_KM",
        "BRL/KM",
        "BRL_M2",
        "BRL_PER_M2",
        "BRL/M2",
        "CUSTO_KM",
        "UNIT_COST",
        "BRL_UNIT",
    }
)

NEGATIVE_ABSENCE_MARKERS = (
    "nao houve",
    "não houve",
    "nao existe aditivo",
    "não existe aditivo",
    "glosa indevida",
    "sem direito",
    "there was no",
    "no amendment occurred",
)

PROHIBITED_CLAIMS: tuple[str, ...] = (
    "inferencia de direito ou de margem",
    "promover BRL_TOTAL a preco unitario",
    "claim nacional sob denominador PARTIAL",
    "ausencia de documento como fato negativo",
    "autoridade de publicacao ou de indice",
)

FAMILY_DOCUMENT_KINDS: dict[str, frozenset[str]] = {
    "reequilibrio": frozenset({"reequilibrio", "rebalancing", "economic_rebalancing"}),
    "aditivos": frozenset({"aditivo", "amendment", "termo_aditivo"}),
    "medicoes_glosas": frozenset({"medicao", "glosa", "measurement", "withholding"}),
    "atrasos_prorrogacoes": frozenset({"prorrogacao", "atraso", "extension", "delay"}),
    "defesa_tecnica": frozenset({"technical_opinion", "parecer_tecnico", "defesa_tecnica"}),
    "orcamento_bdi": frozenset(),
    "pre_licitacao_bid_room": frozenset({"bid_room", "pre_licitacao", "proposta"}),
    "gestao_acompanhamento": frozenset({"management_record", "management_followup", "ata_acompanhamento"}),
}


def pack_id_for(family: str) -> str:
    return f"bofu-{family}-{PACK_VERSION}"


def validate_pack(pack: dict[str, Any]) -> list[str]:
    errors = [f"missing:{field}" for field in REQUIRED_PACK_FIELDS if field not in pack]
    if pack.get("schema") != SCHEMA:
        errors.append("invalid_schema")
    if pack.get("family") not in FAMILIES:
        errors.append("invalid_family")
    if pack.get("state") not in PACK_STATES:
        errors.append("invalid_state")
    if pack.get("publication") is not False:
        errors.append("publication_not_false")
    if pack.get("index") is not False:
        errors.append("index_not_false")
    if pack.get("national") is not False:
        errors.append("national_not_false")
    for item in list(pack.get("claims") or []) + list(pack.get("calculations") or []):
        klass = item.get("epistemic_class")
        if klass not in EPISTEMIC_CLASSES:
            errors.append(f"invalid_epistemic:{item.get('claim_id')}")
        if klass in {"FACT", "CALCULATION"} and not item.get("evidence_refs"):
            errors.append(f"missing_evidence_ref:{item.get('claim_id')}")
    return errors
