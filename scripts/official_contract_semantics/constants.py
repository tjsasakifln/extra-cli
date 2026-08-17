"""Versions, enums and fail-closed constants for official contract observations."""

from __future__ import annotations

SCHEMA_VERSION = "official-contract-observation/1.0"
EXTRACTOR_VERSION = "official-contract-semantics-extract/1.0"
RECONCILE_VERSION = "official-contract-semantics-reconcile/1.0"
EXPORT_COMPARABLES_VERSION = "official-contract-semantics-export-comparables/1.0"
EXPORT_PUBLICATION_VERSION = "official-contract-semantics-export-publication/1.0"
LIVE_VERSION = "official-contract-semantics-live-readonly/1.0"
POLICY_VERSION = "official-contract-semantics-policy/1.0"

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

AMENDMENT_TYPES = (
    "prazo",
    "valor",
    "prazo_e_valor",
    "qualificacao",
    "outro",
)

# Execution timestamps never enter the semantic hash or observation_id.
EXECUTION_TIMESTAMP_FIELDS = frozenset({"extracted_at"})

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
