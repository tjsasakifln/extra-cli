"""Versions, enums and fail-closed constants for official contract observations."""

from __future__ import annotations

SCHEMA_VERSION_V10 = "official-contract-observation/1.0"
SCHEMA_VERSION = "official-contract-observation/1.1"
ACCEPTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION_V10, SCHEMA_VERSION})
EXTRACTOR_VERSION = "official-contract-semantics-extract/1.1"
RECONCILE_VERSION = "official-contract-semantics-reconcile/1.0"
EXPORT_COMPARABLES_VERSION = "official-contract-semantics-export-comparables/1.1"
EXPORT_PUBLICATION_VERSION = "official-contract-semantics-export-publication/1.1"
LIVE_VERSION = "official-contract-semantics-live-readonly/1.1"
POLICY_VERSION = "official-contract-semantics-policy/1.1"

PACKAGE_NAME = "official_contract_semantics"
USER_AGENT = (
    "ExtraConsultoria-official-contract-semantics/1.0 "
    "(+https://github.com/tjsasakifln/extra-cli; read-only official research)"
)

SOURCE_KINDS = (
    "contract",
    "amendment",
    "notice",
    "process_document",
    "official_page",
)

VALUE_SEMANTICS = (
    "valor_estimado",
    "valor_homologado",
    "valor_contratado",
    "valor_unitario",
    "valor_global",
    "valor_mensal",
    "valor_anual",
    "valor_medido",
    "valor_pago",
    "valor_saldo",
    "valor_integral_nominal",
)

STATUSES = (
    "observed",
    "conflicted",
    "superseded_by_official_evidence",
    "unknown",
)

CONFIDENCE_CLASSES = (
    "explicit_structured_field",
    "explicit_labeled_text",
    "explicit_table_cell",
    "unknown",
)

# Epistemic taxonomy. Independent of reconcile status (observed/conflicted/...).
# FACT_OFFICIAL: explicitly supported by an official source field/label.
# OBSERVATION_DERIVED: deterministic transform of official facts; method must be named.
# UNKNOWN / HOLD_FOR_DATA: required field or contract not demonstrated.
# NOT_APPLICABLE: only when the official source demonstrates inapplicability.
# NOT_FOUND: delimited search of a specific official URL/bound returned empty/404.
# UNAVAILABLE: transport/DSN/timeout — not a search result, not world absence.
EPISTEMIC_FACT_OFFICIAL = "FACT_OFFICIAL"
EPISTEMIC_OBSERVATION_DERIVED = "OBSERVATION_DERIVED"
EPISTEMIC_UNKNOWN = "UNKNOWN"
EPISTEMIC_HOLD_FOR_DATA = "HOLD_FOR_DATA"
EPISTEMIC_NOT_APPLICABLE = "NOT_APPLICABLE"
EPISTEMIC_NOT_FOUND = "NOT_FOUND"
EPISTEMIC_UNAVAILABLE = "UNAVAILABLE"
EPISTEMIC_ABSENT = "ABSENT"

EPISTEMIC_CLASSES = (
    EPISTEMIC_FACT_OFFICIAL,
    EPISTEMIC_OBSERVATION_DERIVED,
    EPISTEMIC_UNKNOWN,
    EPISTEMIC_HOLD_FOR_DATA,
    EPISTEMIC_NOT_APPLICABLE,
    EPISTEMIC_NOT_FOUND,
    EPISTEMIC_UNAVAILABLE,
    EPISTEMIC_ABSENT,
)

FIELD_EPISTEMIC_CLASSES = (
    EPISTEMIC_FACT_OFFICIAL,
    EPISTEMIC_OBSERVATION_DERIVED,
    EPISTEMIC_UNKNOWN,
    EPISTEMIC_NOT_APPLICABLE,
)

SEARCH_EPISTEMIC_CLASSES = (
    EPISTEMIC_NOT_FOUND,
    EPISTEMIC_UNAVAILABLE,
    EPISTEMIC_ABSENT,
)

NOT_APPLICABLE_TOKENS = frozenset(
    {
        "not_applicable",
        "n/a",
        "na",
        "nao_se_aplica",
        "não_se_aplica",
        "nao se aplica",
        "não se aplica",
        "inaplicavel",
        "inaplicável",
    }
)

DERIVATION_COMPARABLES_CANONICAL = "export_comparables/valor_global_or_contratado_to_valor_integral_nominal/1.1"

AMENDMENT_TYPES = (
    "prazo",
    "valor",
    "prazo_e_valor",
    "qualificacao",
    "outro",
)

# Execution timestamps never enter the semantic hash or observation_id.
EXECUTION_TIMESTAMP_FIELDS = frozenset({"extracted_at", "retrieved_at", "verified_at"})

SEMANTIC_FIELDS = (
    "object_text",
    "lot_identifier",
    "item_identifier",
    "unit",
    "quantity",
    "execution_regime",
    "procurement_modality",
    "currency",
    "value_amount",
    "value_semantic",
    "period_start",
    "period_end",
    "amendment_type",
    "amendment_value_delta",
    "amendment_term_delta",
)

IDENTITY_FIELDS = (
    "schema_version",
    "source_system",
    "source_kind",
    "official_url",
    "source_document_id",
    "source_document_sha256",
    "process_identifier",
    "contracting_entity_identifier",
    "supplier_identifier",
    "contract_identifier",
    "effective_at",
    "extractor_version",
    "locator",
    "evidence_excerpt",
    "raw_record_hash",
)

COVERAGE_FIELDS = (
    "unit",
    "quantity",
    "execution_regime",
    "procurement_modality",
    "value_amount",
    "value_semantic",
    "period_start",
    "period_end",
    "currency",
    "supplier_identifier",
    "object_text",
)

MAX_EVIDENCE_EXCERPT = 240
DEFAULT_HTTP_TIMEOUT_S = 15.0
DEFAULT_HTTP_RETRIES = 2
DEFAULT_RATE_LIMIT_S = 1.0
DEFAULT_LIVE_LIMIT = 8
MAX_LIVE_LIMIT = 12

FORBIDDEN_PUBLIC_STATES = frozenset({"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX", "REVIEW_CANDIDATE"})

REASON_MISSING_OFFICIAL_IDENTITY = "missing_official_identity"
REASON_VALUE_WITHOUT_SEMANTIC = "value_without_semantic"
REASON_CONFLICTING_VALUE_FIELDS = "conflicting_value_fields"
REASON_CONFLICTING_LABELED_VALUES = "conflicting_labeled_values"
REASON_AMBIGUOUS_DATE = "ambiguous_date"
REASON_INVALID_AMENDMENT_TYPE = "invalid_amendment_type"
REASON_INVALID_EPISTEMIC_CLASS = "invalid_epistemic_class"
REASON_MASKED_IDENTIFIER = "masked_or_incomplete_identifier"
REASON_INFERRED_UNIT_OR_QUANTITY = "inferred_unit_or_quantity"
REASON_PRESUMED_PERIOD_OR_AMENDMENT = "presumed_period_or_amendment"
REASON_INFERRED_FROM_ABSENCE = "inferred_from_absence"
REASON_INVALID_SOURCE_KIND = "invalid_source_kind"
REASON_INVALID_STATUS = "invalid_status"
REASON_INVALID_SCHEMA = "invalid_schema_version"
REASON_INVALID_VALUE_SEMANTIC = "invalid_value_semantic"
REASON_CNPJ_ROOT_ESTABLISHMENT_MERGE = "cnpj_root_establishment_merge"
REASON_CREDENTIAL_MARKER = "credential_marker_detected"
REASON_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
REASON_PARSER_ERROR = "parser_error"
REASON_SOURCE_UNAVAILABLE = "official_source_unavailable"
REASON_CONFLICT_PRESERVED = "official_conflict_preserved"
REASON_SUPERSEDED = "superseded_by_official_evidence"
REASON_FIELDS_UNAVAILABLE = "fields_unavailable"
REASON_HOLD_FOR_DATA = "HOLD_FOR_DATA"

COMPARABLES_CANONICAL_SEMANTIC = "valor_integral_nominal"
COMPARABLES_CANONICAL_UNIT = "BRL_TOTAL"
EXPORT_SEMANTIC_TO_COMPARABLES = {
    "valor_global": COMPARABLES_CANONICAL_SEMANTIC,
    "valor_contratado": COMPARABLES_CANONICAL_SEMANTIC,
    "valor_integral_nominal": COMPARABLES_CANONICAL_SEMANTIC,
}
