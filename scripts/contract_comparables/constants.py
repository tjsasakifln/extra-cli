"""Canonical versions, gates and reason codes for inbound comparables (#415)."""

from __future__ import annotations

SCHEMA = "comparable-contracts/1.0"
SCHEMA_ALIAS = "public-read-comparable-contracts/1.0"
CONTRACT_VERSION = "v1.0.0"
METHOD_VERSION = "comparable-contracts-peer-group/1.0"
POLICY_VERSION = "contract-comparables-policy/1.0"
QUESTION_ID = "paving_nominal_total_value_position"
QUESTION = (
    "Como o valor integral nominal de um contrato público de pavimentação "
    "se posiciona frente a contratos comparáveis?"
)
CONSUMER_ID = "public-read-contract-analysis/#400"
CONSUMER_FAMILY = "web-cfg / contract-analysis family"

STATUS_COMPARABLE = "COMPARABLE"
STATUS_HOLD = "HOLD_FOR_DATA"
STATUS_NOT = "NOT_COMPARABLE"
STATUS_ENUM = (STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT)

LEGACY_STATUS_MAP = {
    "PEER_VALID": STATUS_COMPARABLE,
    "PEER_WEAK": STATUS_HOLD,
    "NO_VALID_PEER_GROUP": STATUS_NOT,
}

VALUE_SEMANTIC_CANONICAL = "valor_integral_nominal"
UNIT_CANONICAL = "BRL_TOTAL"
CATALOG_FIXTURE = "fixture"
CATALOG_LIVE_CANDIDATE = "live_candidate"
CATALOG_FIXTURE_ONLY = "FIXTURE_ONLY"
OFFICIAL_LIVE = "official_live"

MIN_USABLE_N_COMPARABLE = 5
MIN_USABLE_N_HOLD = 3
MIN_COVERAGE_COMPARABLE = 0.50
MIN_COVERAGE_HOLD = 0.30
MIN_TYPOLOGY_CONFIDENCE = 0.80
MAX_YEAR_DELTA_COMPARABLE = 1
MAX_YEAR_DELTA_HOLD = 2
IQR_OUTLIER_K = 1.5
ROBUST_DISTANCE_OUTLIER = 3.0

REASON_TARGET_NOT_FOUND = "target_not_found"
REASON_INCOMPATIBLE_UNIT = "incompatible_unit"
REASON_UNIT_UNKNOWN = "unit_unknown"
REASON_AMBIGUOUS_TYPOLOGY = "ambiguous_typology"
REASON_TYPOLOGY_MISMATCH = "typology_mismatch"
REASON_DISTINCT_SCOPE = "distinct_scope"
REASON_INCOMPATIBLE_REGIME = "incompatible_regime"
REASON_PERIOD_NOT_COMPARABLE = "period_not_comparable"
REASON_GEOGRAPHY_NOT_COMPARABLE = "geography_not_comparable"
REASON_INSUFFICIENT_N = "insufficient_n"
REASON_INSUFFICIENT_COVERAGE = "insufficient_coverage"
REASON_VALUE_SEMANTIC_MISMATCH = "value_semantic_mismatch"
REASON_DUPLICATE_OR_RECTIFICATION = "duplicate_or_rectification"
REASON_ORIGINAL_VS_UPDATED_MIX = "original_vs_updated_mix"
REASON_MISSING_VALUE = "missing_value"
REASON_UNKNOWN_EXCLUDED = "unknown_excluded_from_denominator"
REASON_LIVE_COLUMNS = "live_columns_unavailable"
REASON_PHYSICAL_UNIT = "physical_unit_price_not_verified"
REASON_FIXTURE_NOT_LIVE = "fixture_not_official_live"
REASON_STATISTICAL_DIFF = "statistical_difference_only"
REASON_PORTE_NOT_COMPARABLE = "porte_not_comparable"
REASON_TEXT_SIMILARITY_ONLY = "text_similarity_only"
REASON_EMBEDDING_NOT_AUTHORITY = "embedding_not_authority"
REASON_FIELDS_UNAVAILABLE = "fields_unavailable"

HARD_REFUSAL_REASONS = frozenset(
    {
        REASON_INCOMPATIBLE_UNIT,
        REASON_TYPOLOGY_MISMATCH,
        REASON_DISTINCT_SCOPE,
        REASON_INCOMPATIBLE_REGIME,
        REASON_PERIOD_NOT_COMPARABLE,
        REASON_GEOGRAPHY_NOT_COMPARABLE,
        REASON_VALUE_SEMANTIC_MISMATCH,
        REASON_DUPLICATE_OR_RECTIFICATION,
        REASON_ORIGINAL_VS_UPDATED_MIX,
        REASON_PORTE_NOT_COMPARABLE,
        REASON_TEXT_SIMILARITY_ONLY,
        REASON_EMBEDDING_NOT_AUTHORITY,
    }
)

HOLD_REASONS = frozenset(
    {
        REASON_AMBIGUOUS_TYPOLOGY,
        REASON_MISSING_VALUE,
        REASON_INSUFFICIENT_COVERAGE,
        REASON_LIVE_COLUMNS,
        REASON_PHYSICAL_UNIT,
        REASON_UNIT_UNKNOWN,
        REASON_FIELDS_UNAVAILABLE,
        REASON_UNKNOWN_EXCLUDED,
    }
)

FORBIDDEN_CLAIM_TOKENS = (
    "sobrepreco",
    "sobrepreço",
    "overprice",
    "fraude",
    "fraud",
    "irregularidade",
    "irregularity",
    "irregular",
    "caro",
    "barato",
    "custo/km",
    "custo/m2",
    "custo/m²",
    "custo por km",
    "custo por m",
    "preco unitario",
    "preço unitário",
    "ranking nacional",
    "market share",
)

FORBIDDEN_METRIC_KEYS = frozenset(
    {
        "cost_per_km",
        "cost_per_m2",
        "custo_por_km",
        "custo_por_m2",
        "unit_price",
        "preco_unitario",
        "sobrepreco",
        "overprice",
    }
)

PAVING_KEYWORDS = (
    "pavimentacao",
    "recapeamento",
    "revestimento asfaltico",
    "cbuq",
    "tsd",
    "microrevestimento",
    "restauracao asfaltica",
    "capa asfaltica",
    "asfaltamento",
    "concreto betuminoso usinado",
)

AMBIGUOUS_TYPOLOGY_KEYWORDS = (
    "infraestrutura viaria",
    "obras viarias",
    "recuperacao de vias",
    "melhoria viaria",
)

NON_PAVING_KEYWORDS = (
    "edificacao",
    "escola",
    "predio",
    "hospital",
    "unidade basica",
    "almoxarifado",
    "reforma predial",
    "construcao de sede",
)

REGIME_GLOBAL = frozenset(
    {
        "empreitada_global",
        "preco_global",
        "empreitada por preco global",
        "global",
        "preco global",
    }
)
REGIME_UNITARIO = frozenset(
    {
        "empreitada_unitaria",
        "preco_unitario",
        "empreitada por preco unitario",
        "unitario",
        "preco unitario",
    }
)

VALUE_SEMANTIC_ALIASES = {
    "valor_integral_nominal": VALUE_SEMANTIC_CANONICAL,
    "contratado": VALUE_SEMANTIC_CANONICAL,
    "valor_contratado": VALUE_SEMANTIC_CANONICAL,
    "signed": VALUE_SEMANTIC_CANONICAL,
    "estimado": "estimado",
    "valor_estimado": "estimado",
    "estimated": "estimado",
    "homologado": "homologado",
    "valor_homologado": "homologado",
    "awarded": "homologado",
    "pago": "pago",
    "valor_pago": "pago",
    "paid": "pago",
    "atualizado": "atualizado",
    "valor_atualizado": "atualizado",
    "unknown": "unknown",
}

UNIT_TOTAL_ALIASES = frozenset({"brl_total", "valor_integral", "brl", "r$", "total"})
UNIT_KM_ALIASES = frozenset({"km", "quilometro", "quilometros"})
UNIT_M2_ALIASES = frozenset({"m2", "m²", "metro quadrado", "metros quadrados"})

REGION_BY_UF = {
    "AC": "N",
    "AP": "N",
    "AM": "N",
    "PA": "N",
    "RO": "N",
    "RR": "N",
    "TO": "N",
    "AL": "NE",
    "BA": "NE",
    "CE": "NE",
    "MA": "NE",
    "PB": "NE",
    "PE": "NE",
    "PI": "NE",
    "RN": "NE",
    "SE": "NE",
    "DF": "CO",
    "GO": "CO",
    "MS": "CO",
    "MT": "CO",
    "ES": "SE",
    "MG": "SE",
    "RJ": "SE",
    "SP": "SE",
    "PR": "S",
    "RS": "S",
    "SC": "S",
}

LIVE_OFFICIAL_COLUMNS = (
    "contrato_id",
    "orgao_cnpj",
    "orgao_nome",
    "fornecedor_cnpj",
    "fornecedor_nome",
    "objeto_contrato",
    "valor_total",
    "data_inicio",
    "data_fim",
    "data_publicacao",
    "uf",
    "municipio",
    "source",
    "source_id",
    "ingested_at",
    "is_active",
    "codigo_municipio_ibge",
)

LIVE_MISSING_SEMANTIC_COLUMNS = (
    "unidade",
    "quantidade",
    "regime",
    "modalidade",
    "valor_semantic",
)
