"""Pure official-fact projector for the margin-defense consumer.

No I/O. Missing source fields stay UNKNOWN with a reason_code.
Absence of evidence is never coerced to zero. Legal conclusions are refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

SCHEMA = "public-read-margin-defense/1.0"

FieldStatus = Literal["KNOWN", "UNKNOWN"]

FACT_FIELDS: tuple[str, ...] = (
    "canonical_contract_id",
    "object",
    "organ",
    "contractor",
    "nominal_value",
    "signed_at",
    "start_at",
    "end_at",
    "term",
    "adjustment_anniversary",
    "adjustment_base",
    "amendments",
    "value_changes",
    "term_changes",
    "scope_changes",
    "measurement_events",
    "payment_events",
    "suspension",
    "resumption",
    "extension",
    "indices",
)

FORBIDDEN_CONCLUSION_FIELDS = frozenset(
    {
        "has_right",
        "imbalance",
        "loss",
        "should_adjust",
        "direito",
        "desequilibrio",
        "perda",
        "deveria_reajustar",
    }
)

_IDENTITY_KEYS = ("canonical_contract_id", "contrato_id", "source_record_id")


class EvidenceIdentityError(ValueError):
    """Evidence was supplied without a contract identity."""


class ForbiddenConclusionError(ValueError):
    """A legal-conclusion field was present on the official record."""


@dataclass(frozen=True)
class FieldFact:
    name: str
    status: FieldStatus
    value: Any
    reason_code: str | None
    evidence_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "value": _jsonable(self.value),
            "reason_code": self.reason_code,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True)
class MarginFacts:
    schema: str
    canonical_contract_id: str | None
    fields: tuple[FieldFact, ...]
    source_id: str | None
    source_record_id: str | None
    observed_at: str | None
    as_of: str
    reason_codes: tuple[str, ...]

    @property
    def known_count(self) -> int:
        return sum(1 for fact in self.fields if fact.status == "KNOWN")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "canonical_contract_id": self.canonical_contract_id,
            "fields": {fact.name: fact.as_dict() for fact in self.fields},
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "observed_at": self.observed_at,
            "as_of": self.as_of,
            "reason_codes": list(self.reason_codes),
            "known_count": self.known_count,
            "field_count": len(self.fields),
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == ()


def _text(value: Any) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    if _blank(value):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed


def _known(name: str, value: Any, evidence_ref: str | None) -> FieldFact:
    return FieldFact(name, "KNOWN", value, None, evidence_ref)


def _unknown(name: str, reason_code: str, evidence_ref: str | None = None) -> FieldFact:
    return FieldFact(name, "UNKNOWN", None, reason_code, evidence_ref)


def _identity(record: dict[str, Any]) -> str | None:
    for key in _IDENTITY_KEYS:
        found = _text(record.get(key))
        if found:
            return found
    return None


def _evidence_ref(record: dict[str, Any]) -> str | None:
    return _text(record.get("evidence_ref") or record.get("source_id"))


def _explicit_adjustment_document(record: dict[str, Any]) -> bool:
    return bool(
        _text(record.get("adjustment_base_document_id"))
        or _text(record.get("adjustment_rule_text"))
        or _text(record.get("adjustment_clause_ref"))
    )


def _explicit_index_document(record: dict[str, Any]) -> bool:
    return bool(_text(record.get("index_document_id")) or _text(record.get("index_clause_ref")))


def project_margin_facts(record: dict[str, Any], *, as_of: str) -> MarginFacts:
    """Project one official contract record into UNKNOWN-safe facts."""
    forbidden = FORBIDDEN_CONCLUSION_FIELDS.intersection(record)
    if forbidden:
        raise ForbiddenConclusionError(f"forbidden_conclusion_fields:{sorted(forbidden)}")

    identity = _identity(record)
    evidence_hint = _text(record.get("evidence_ref"))
    if evidence_hint and not identity:
        raise EvidenceIdentityError("evidence_without_identity")

    evidence = _evidence_ref(record) if identity else None
    fields: list[FieldFact] = []

    if identity:
        fields.append(_known("canonical_contract_id", identity, evidence))
    else:
        fields.append(_unknown("canonical_contract_id", "missing_identity"))

    objeto = _text(record.get("objeto_contrato") or record.get("object") or record.get("objeto"))
    fields.append(_known("object", objeto, evidence) if objeto else _unknown("object", "missing_object"))

    organ_id = _text(record.get("orgao_cnpj"))
    organ_name = _text(record.get("orgao_nome"))
    if organ_id or organ_name:
        fields.append(
            _known(
                "organ",
                {"cnpj": organ_id, "name": organ_name},
                evidence,
            )
        )
    else:
        fields.append(_unknown("organ", "missing_organ"))

    contractor_id = _text(record.get("fornecedor_cnpj") or record.get("contractor_id"))
    contractor_name = _text(record.get("fornecedor_nome") or record.get("contractor_name"))
    if contractor_id or contractor_name:
        fields.append(
            _known(
                "contractor",
                {"cnpj": contractor_id, "name": contractor_name},
                evidence,
            )
        )
    else:
        fields.append(_unknown("contractor", "missing_contractor"))

    nominal = _decimal(record.get("valor_total") if "valor_total" in record else record.get("nominal_value"))
    if nominal is None:
        fields.append(_unknown("nominal_value", "missing_nominal_value"))
    else:
        fields.append(
            _known(
                "nominal_value",
                {
                    "amount": nominal,
                    "currency": "BRL",
                    "semantics": "integral_nominal_instrument",
                },
                evidence,
            )
        )

    signed = _text(record.get("data_assinatura") or record.get("signed_at"))
    fields.append(_known("signed_at", signed, evidence) if signed else _unknown("signed_at", "missing_signed_at"))

    start = _text(record.get("data_inicio") or record.get("start_at"))
    fields.append(_known("start_at", start, evidence) if start else _unknown("start_at", "missing_start_at"))

    end = _text(record.get("data_fim") or record.get("end_at"))
    fields.append(_known("end_at", end, evidence) if end else _unknown("end_at", "missing_end_at"))

    term = _text(record.get("term") or record.get("vigencia"))
    if term:
        fields.append(_known("term", term, evidence))
    elif start and end:
        fields.append(_known("term", {"start": start, "end": end, "derivation": "start_end_interval"}, evidence))
    else:
        fields.append(_unknown("term", "missing_term"))

    if _explicit_adjustment_document(record) and _text(record.get("adjustment_anniversary")):
        fields.append(_known("adjustment_anniversary", _text(record.get("adjustment_anniversary")), evidence))
    else:
        fields.append(_unknown("adjustment_anniversary", "no_explicit_adjustment_document"))

    if _explicit_adjustment_document(record) and _text(record.get("adjustment_base")):
        fields.append(_known("adjustment_base", _text(record.get("adjustment_base")), evidence))
    else:
        fields.append(_unknown("adjustment_base", "no_explicit_adjustment_rule"))

    amendments = record.get("amendments") or record.get("aditivos") or ()
    if amendments:
        fields.append(_known("amendments", tuple(amendments), evidence))
    else:
        fields.append(_unknown("amendments", "no_amendment_signal"))

    for name, key, reason in (
        ("value_changes", "value_changes", "no_amendment_signal"),
        ("term_changes", "term_changes", "no_amendment_signal"),
        ("scope_changes", "scope_changes", "no_amendment_signal"),
        ("suspension", "suspension", "not_observed"),
        ("resumption", "resumption", "not_observed"),
        ("extension", "extension", "not_observed"),
    ):
        observed = record.get(key)
        if observed:
            fields.append(_known(name, observed, evidence))
        else:
            fields.append(_unknown(name, reason))

    if record.get("measurement_events"):
        fields.append(_known("measurement_events", record["measurement_events"], evidence))
    else:
        fields.append(_unknown("measurement_events", "source_does_not_offer_measurements"))

    if record.get("payment_events"):
        fields.append(_known("payment_events", record["payment_events"], evidence))
    else:
        fields.append(_unknown("payment_events", "source_does_not_offer_payments"))

    indices = record.get("indices")
    if indices and _explicit_index_document(record):
        fields.append(_known("indices", indices, evidence))
    elif indices and not _explicit_index_document(record):
        fields.append(_unknown("indices", "index_without_document"))
    else:
        fields.append(_unknown("indices", "index_without_document"))

    names = {fact.name for fact in fields}
    if names != set(FACT_FIELDS):
        raise ValueError(f"projector_field_set_mismatch:{sorted(set(FACT_FIELDS) ^ names)}")

    reasons = tuple(fact.reason_code for fact in fields if fact.reason_code)
    return MarginFacts(
        schema=SCHEMA,
        canonical_contract_id=identity,
        fields=tuple(fields),
        source_id=_text(record.get("source") or record.get("source_id")),
        source_record_id=_text(record.get("source_id") or identity),
        observed_at=_text(record.get("observed_at") or record.get("last_seen_at") or record.get("ingested_at")),
        as_of=as_of,
        reason_codes=reasons,
    )
