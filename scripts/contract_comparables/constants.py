"""Canonical versions, gates and reason codes for inbound comparables (#415)."""

from __future__ import annotations

SCHEMA = "comparable-contracts/1.0"
SCHEMA_ALIAS = "public-read-comparable-contracts/1.0"
CONTRACT_VERSION = "v1.0.0"
METHOD_VERSION = "comparable-contracts-peer-group/1.0"
POLICY_VERSION = "contract-comparables-policy/1.0"
QUESTION_ID = "paving_nominal_total_value_position"
QUESTION = (
    "Como o valor integral nominal de um contrato público de pavimentação se posiciona frente a contratos comparáveis?"
)
CONSUMER_ID = "public-read-contract-analysis/#400"
CONSUMER_FAMILY = "web-cfg / contract-analysis family"

STATUS_COMPARABLE = "COMPARABLE"
STATUS_HOLD = "HOLD_FOR_DATA"
STATUS_NOT = "NOT_COMPARABLE"
STATUS_BLOCKED = "BLOCKED"
STATUS_ENUM = (STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT)
CANARY_STATUS_ENUM = (*STATUS_ENUM, STATUS_BLOCKED)

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
CATALOG_BLOCKED = "blocked"
OFFICIAL_LIVE = "official_live"
OFFICIAL_CANARY_SCHEMA = "comparable-contracts-official-canary/1.0"
METRIC_NOMINAL_TOTAL = "valor_integral_nominal"
PHYSICAL_UNIT_METRICS = frozenset(
    {
        "cost_per_km",
        "custo_por_km",
        "custo/km",
        "cost_per_m2",
        "custo_por_m2",
        "custo/m2",
        "unit_price",
        "preco_unitario",
        "preço_unitário",
    }
)

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
REASON_DSN_UNAVAILABLE = "dsn_unavailable"
REASON_HOST_UNAVAILABLE = "host_unavailable"
REASON_TABLE_MISSING = "official_table_missing"
REASON_DATASET_EMPTY = "official_dataset_empty"
REASON_PAVING_SAMPLE_EMPTY = "official_paving_sample_empty"
REASON_LIVE_PROBE_FAILED = "live_probe_failed"
REASON_IDENTITY_SWAP = "identity_swap"
REASON_CNPJ_IN_MUNICIPIO = "cnpj_in_municipio"
REASON_INVERTED_DATES = "inverted_dates"
REASON_CONFLICTING_OFFICIAL_VALUES = "conflicting_official_values"
REASON_GRAIN_MISMATCH = "grain_mismatch"
REASON_NATIONALIZED_STATE_SAMPLE = "nationalized_state_sample"
REASON_AREA_MISSING = "area_missing_for_unit_price"
REASON_PNCP_UNAVAILABLE = "pncp_unavailable"
REASON_STALE_HASH = "stale_hash_after_rectification"
REASON_FIXTURE_LABELED_LIVE = "fixture_labeled_official_live"
REASON_ZERO_FROM_MISSING = "missing_field_coerced"
REASON_REGIME_UNPUBLISHED = "regime_unpublished_on_locator"
REASON_CONSULTA_CNPJ_ORGAO = "consulta_cnpj_orgao_bounded"
REASON_PAVING_FAMILY_MISMATCH = "paving_family_mismatch"
REASON_UNIT_FROM_OFFICIAL_TOTAL = "unit_from_official_total_field"
LIVE_PAVING_ENVELOPE_SCHEMA = "comparable-contracts-live-paving-handoff/1.0"
LIVE_PAVING_HANDOFF_SCHEMA = "authority-handoff-contract-comparables/1.0"
FOCAL_CANARY_CONTRACT_ID = "14862788000150-2-000069/2026"
LIVE_PAVING_CANARY_ID = "paving-nominal-14862788000150-2-000069-2026"
CONSUMER_WEB_CFG = "web-cfg#83|#84"
PRODUCER_EXTRA_CLI = "extra-cli"

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
        REASON_IDENTITY_SWAP,
        REASON_CNPJ_IN_MUNICIPIO,
        REASON_INVERTED_DATES,
        REASON_CONFLICTING_OFFICIAL_VALUES,
        REASON_GRAIN_MISMATCH,
        REASON_NATIONALIZED_STATE_SAMPLE,
        REASON_FIXTURE_LABELED_LIVE,
        REASON_ZERO_FROM_MISSING,
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
        REASON_AREA_MISSING,
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

PAVING_FAMILY_PARALELEPIPEDO = "paralelepipedo"
PAVING_FAMILY_CBUQ = "cbuq"
PAVING_FAMILY_TSD = "tsd"
PAVING_FAMILY_RECAPEAMENTO = "recapeamento"
PAVING_FAMILY_ASFALTICO = "asfaltico"
PAVING_FAMILY_GENERIC = "pavimentacao"
DERIVATION_UNIT_FROM_OFFICIAL_TOTAL = "official_total_value_field_is_instrument_total/1.0"

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
