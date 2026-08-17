"""Immutable OfficialContractObservation and related records."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any, Literal

from scripts.official_contract_semantics.constants import (
    AMENDMENT_TYPES,
    CONFIDENCE_CLASSES,
    EXTRACTOR_VERSION,
    SCHEMA_VERSION,
    SOURCE_KINDS,
    STATUSES,
    VALUE_SEMANTICS,
)
from scripts.official_contract_semantics.serialize import jsonable

SourceKind = Literal["contract", "amendment", "notice", "process_document", "official_page"]
ObservationStatus = Literal["observed", "conflicted", "superseded_by_official_evidence", "unknown"]
ConfidenceClass = Literal["explicit_structured_field", "explicit_labeled_text", "explicit_table_cell", "unknown"]


@dataclass(frozen=True)
class Locator:
    page: int | None = None
    section: str | None = None
    table: str | None = None
    cell: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    json_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in jsonable(self.__dict__).items() if value is not None}

    def is_empty(self) -> bool:
        return all(value is None for value in self.__dict__.values())


@dataclass(frozen=True)
class OfficialContractObservation:
    schema_version: str
    observation_id: str
    source_system: str
    source_kind: str
    official_url: str | None
    source_document_id: str | None
    source_document_sha256: str | None
    process_identifier: str | None
    contracting_entity_identifier: str | None
    supplier_identifier: str | None
    contract_identifier: str | None
    observed_at: str | None
    effective_at: str | None
    extractor_version: str
    locator: Locator
    evidence_excerpt: str | None
    raw_record_hash: str
    object_text: str | None
    lot_identifier: str | None
    item_identifier: str | None
    unit: str | None
    quantity: Decimal | None
    execution_regime: str | None
    procurement_modality: str | None
    currency: str | None
    value_amount: Decimal | None
    value_semantic: str | None
    period_start: str | None
    period_end: str | None
    amendment_type: str | None
    amendment_value_delta: Decimal | None
    amendment_term_delta: str | None
    confidence_class: str
    conflict_group_id: str | None
    status: str
    extracted_at: str | None = None
    extraction_rule: str | None = None
    extraction_rule_version: str | None = None
    supersedes_document_id: str | None = None
    supersedes_observation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "locator":
                payload[item.name] = value.as_dict()
            elif item.name == "extra":
                if value:
                    payload[item.name] = jsonable(value)
            else:
                payload[item.name] = jsonable(value)
        return payload

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.as_dict()
        payload.pop("extracted_at", None)
        return payload


@dataclass(frozen=True)
class ExtractionRejection:
    code: str
    message: str
    source_document_id: str | None = None
    official_url: str | None = None
    locator: dict[str, Any] | None = None
    evidence_excerpt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return jsonable(self.__dict__)


@dataclass(frozen=True)
class DocumentError:
    code: str
    message: str
    source_document_id: str | None = None
    official_url: str | None = None
    source_document_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return jsonable(self.__dict__)


@dataclass(frozen=True)
class SourceUnavailability:
    official_url: str
    error_kind: str
    recorded_as: str = "unavailable"
    http_status: int | None = None
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return jsonable(self.__dict__)


@dataclass(frozen=True)
class ExtractResult:
    observations: tuple[OfficialContractObservation, ...]
    rejections: tuple[ExtractionRejection, ...]
    document_errors: tuple[DocumentError, ...]
    unavailabilities: tuple[SourceUnavailability, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "observations": [item.as_dict() for item in self.observations],
            "rejections": [item.as_dict() for item in self.rejections],
            "document_errors": [item.as_dict() for item in self.document_errors],
            "unavailabilities": [item.as_dict() for item in self.unavailabilities],
        }


def locator_from_mapping(raw: Any) -> Locator:
    if raw is None:
        return Locator()
    if isinstance(raw, Locator):
        return raw
    if not isinstance(raw, dict):
        return Locator(section=str(raw))
    return Locator(
        page=raw.get("page"),
        section=raw.get("section"),
        table=raw.get("table"),
        cell=raw.get("cell"),
        char_start=raw.get("char_start"),
        char_end=raw.get("char_end"),
        json_path=raw.get("json_path"),
    )


def _check_enum(value: str, allowed: tuple[str, ...], label: str) -> None:
    if value not in allowed:
        raise ValueError(f"{label}_not_in_enum:{value}")


def observation_from_mapping(raw: dict[str, Any]) -> OfficialContractObservation:
    source_kind = str(raw.get("source_kind") or "")
    status = str(raw.get("status") or "observed")
    confidence = str(raw.get("confidence_class") or "unknown")
    if source_kind:
        _check_enum(source_kind, SOURCE_KINDS, "source_kind")
    if status:
        _check_enum(status, STATUSES, "status")
    if confidence:
        _check_enum(confidence, CONFIDENCE_CLASSES, "confidence_class")
    semantic = raw.get("value_semantic")
    if semantic:
        _check_enum(str(semantic), VALUE_SEMANTICS, "value_semantic")
    amendment_type = raw.get("amendment_type")
    if amendment_type:
        _check_enum(str(amendment_type), AMENDMENT_TYPES, "amendment_type")
    from scripts.official_contract_semantics.identity import parse_optional_decimal

    return OfficialContractObservation(
        schema_version=str(raw.get("schema_version") or SCHEMA_VERSION),
        observation_id=str(raw.get("observation_id") or ""),
        source_system=str(raw.get("source_system") or ""),
        source_kind=source_kind,
        official_url=raw.get("official_url"),
        source_document_id=raw.get("source_document_id"),
        source_document_sha256=raw.get("source_document_sha256"),
        process_identifier=raw.get("process_identifier"),
        contracting_entity_identifier=raw.get("contracting_entity_identifier"),
        supplier_identifier=raw.get("supplier_identifier"),
        contract_identifier=raw.get("contract_identifier"),
        observed_at=raw.get("observed_at"),
        effective_at=raw.get("effective_at"),
        extractor_version=str(raw.get("extractor_version") or EXTRACTOR_VERSION),
        locator=locator_from_mapping(raw.get("locator")),
        evidence_excerpt=raw.get("evidence_excerpt"),
        raw_record_hash=str(raw.get("raw_record_hash") or ""),
        object_text=raw.get("object_text"),
        lot_identifier=raw.get("lot_identifier"),
        item_identifier=raw.get("item_identifier"),
        unit=raw.get("unit"),
        quantity=parse_optional_decimal(raw.get("quantity")),
        execution_regime=raw.get("execution_regime"),
        procurement_modality=raw.get("procurement_modality"),
        currency=raw.get("currency"),
        value_amount=parse_optional_decimal(raw.get("value_amount")),
        value_semantic=semantic,
        period_start=raw.get("period_start"),
        period_end=raw.get("period_end"),
        amendment_type=amendment_type,
        amendment_value_delta=parse_optional_decimal(raw.get("amendment_value_delta")),
        amendment_term_delta=raw.get("amendment_term_delta"),
        confidence_class=confidence,
        conflict_group_id=raw.get("conflict_group_id"),
        status=status,
        extracted_at=raw.get("extracted_at"),
        extraction_rule=raw.get("extraction_rule"),
        extraction_rule_version=raw.get("extraction_rule_version"),
        supersedes_document_id=raw.get("supersedes_document_id"),
        supersedes_observation_id=raw.get("supersedes_observation_id"),
        extra=dict(raw.get("extra") or {}),
    )
