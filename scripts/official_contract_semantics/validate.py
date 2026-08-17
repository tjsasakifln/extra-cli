"""Fail-closed validation of official contract observations."""

from __future__ import annotations

from typing import Any

from scripts.official_contract_semantics.constants import (
    AMENDMENT_TYPES,
    CONFIDENCE_CLASSES,
    EXTRACTOR_VERSION,
    REASON_CNPJ_ROOT_ESTABLISHMENT_MERGE,
    REASON_CREDENTIAL_MARKER,
    REASON_INFERRED_FROM_ABSENCE,
    REASON_INFERRED_UNIT_OR_QUANTITY,
    REASON_INVALID_SCHEMA,
    REASON_INVALID_SOURCE_KIND,
    REASON_INVALID_STATUS,
    REASON_INVALID_VALUE_SEMANTIC,
    REASON_MISSING_OFFICIAL_IDENTITY,
    REASON_PRESUMED_PERIOD_OR_AMENDMENT,
    REASON_VALUE_WITHOUT_SEMANTIC,
    SCHEMA_VERSION,
    SOURCE_KINDS,
    STATUSES,
    VALUE_SEMANTICS,
)
from scripts.official_contract_semantics.identity import detect_secret, official_identity_present
from scripts.official_contract_semantics.models import OfficialContractObservation, observation_from_mapping


class ObservationValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message


INFERENCE_RULES = frozenset(
    {
        "inferred_from_absence",
        "inferred_from_generic_context",
        "presumed_unpublished_means_absent",
        "default_global_unit",
        "default_value_semantic",
    }
)


def _fail(code: str, message: str) -> None:
    raise ObservationValidationError(code, message)


def validate_mapping(raw: dict[str, Any]) -> OfficialContractObservation:
    if raw.get("schema_version") not in {None, SCHEMA_VERSION} and raw.get("schema_version") != SCHEMA_VERSION:
        _fail(REASON_INVALID_SCHEMA, str(raw.get("schema_version")))
    if raw.get("infer_from_absence") or raw.get("assume_missing_if_unpublished"):
        _fail(REASON_INFERRED_FROM_ABSENCE, "absence_is_not_a_fact")
    rule = raw.get("extraction_rule")
    if rule in INFERENCE_RULES:
        _fail(REASON_INFERRED_FROM_ABSENCE, str(rule))
    if raw.get("unit_inferred") or raw.get("quantity_inferred"):
        _fail(REASON_INFERRED_UNIT_OR_QUANTITY, "unit_or_quantity_not_explicit")
    if raw.get("period_presumed") or raw.get("amendment_presumed"):
        _fail(REASON_PRESUMED_PERIOD_OR_AMENDMENT, "period_or_amendment_not_published")
    if not official_identity_present(raw):
        _fail(REASON_MISSING_OFFICIAL_IDENTITY, "need_official_url_or_document_hash_or_source_record")
    source_kind = raw.get("source_kind")
    if source_kind not in SOURCE_KINDS:
        _fail(REASON_INVALID_SOURCE_KIND, str(source_kind))
    status = raw.get("status") or "observed"
    if status not in STATUSES:
        _fail(REASON_INVALID_STATUS, str(status))
    confidence = raw.get("confidence_class") or "unknown"
    if confidence not in CONFIDENCE_CLASSES:
        _fail(REASON_INVALID_STATUS, str(confidence))
    semantic = raw.get("value_semantic")
    amount = raw.get("value_amount")
    if amount not in {None, ""} and not semantic:
        _fail(REASON_VALUE_WITHOUT_SEMANTIC, "value_amount_requires_value_semantic")
    if semantic and semantic not in VALUE_SEMANTICS:
        _fail(REASON_INVALID_VALUE_SEMANTIC, str(semantic))
    amendment_type = raw.get("amendment_type")
    if amendment_type and amendment_type not in AMENDMENT_TYPES:
        _fail(REASON_PRESUMED_PERIOD_OR_AMENDMENT, str(amendment_type))
    if raw.get("merge_cnpj_root_with_establishment"):
        _fail(REASON_CNPJ_ROOT_ESTABLISHMENT_MERGE, "root_and_establishment_must_stay_distinct")
    excerpt = raw.get("evidence_excerpt")
    object_text = raw.get("object_text")
    if detect_secret(excerpt) or detect_secret(object_text) or detect_secret(str(raw.get("official_url") or "")):
        _fail(REASON_CREDENTIAL_MARKER, "credential_marker_in_observation")
    if raw.get("schema_version") is None:
        raw = {**raw, "schema_version": SCHEMA_VERSION}
    if raw.get("extractor_version") is None:
        raw = {**raw, "extractor_version": EXTRACTOR_VERSION}
    observation = observation_from_mapping(raw)
    if not observation.observation_id:
        _fail(REASON_MISSING_OFFICIAL_IDENTITY, "observation_id_required")
    if not observation.raw_record_hash:
        _fail(REASON_MISSING_OFFICIAL_IDENTITY, "raw_record_hash_required")
    if not observation.source_system:
        _fail(REASON_MISSING_OFFICIAL_IDENTITY, "source_system_required")
    return observation


def validate_observation(observation: OfficialContractObservation) -> OfficialContractObservation:
    return validate_mapping(observation.as_dict())


def validate_many(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[tuple[OfficialContractObservation, ...], tuple[dict[str, Any], ...]]:
    accepted: list[OfficialContractObservation] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        try:
            accepted.append(validate_mapping(row))
        except ObservationValidationError as exc:
            rejected.append({"code": exc.code, "message": exc.message, "row": row})
    accepted_sorted = tuple(sorted(accepted, key=lambda item: item.observation_id))
    rejected_sorted = tuple(
        sorted(rejected, key=lambda item: (item["code"], str(item["row"].get("source_document_id"))))
    )
    return accepted_sorted, rejected_sorted
