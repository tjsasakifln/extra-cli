"""Project a snapshot record into facts the detectors can read.

Reuses the UNKNOWN-safe margin-defense projector. Absence is never 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from scripts.contract_publication.schema import FORBIDDEN_CONCLUSION_FIELDS, content_hash
from scripts.contracts_truth import canonical_contract_identity
from scripts.public_read.margin_defense import (
    FieldFact,
    ForbiddenConclusionError,
    MarginFacts,
    project_margin_facts,
)


@dataclass(frozen=True)
class ProjectedRecord:
    record: dict[str, Any]
    facts: MarginFacts
    canonical_contract_id: str | None
    by_name: dict[str, FieldFact]
    catalog_mode: str


def text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    found = str(value).strip()
    return found or None


def explicit_evidence_refs(record: dict[str, Any]) -> tuple[str, ...]:
    refs: list[str] = []
    for key in (
        "evidence_ref",
        "adjustment_base_document_id",
        "adjustment_clause_ref",
        "index_document_id",
        "index_clause_ref",
        "document_ref",
    ):
        found = text(record.get(key))
        if found and found not in refs:
            refs.append(found)
    for item in record.get("documents") or ():
        if isinstance(item, dict):
            found = text(item.get("ref") or item.get("evidence_ref") or item.get("id") or item.get("sha256"))
        else:
            found = text(item)
        if found and found not in refs:
            refs.append(found)
    for item in record.get("source_urls") or ():
        found = text(item if not isinstance(item, dict) else item.get("url"))
        if found and found not in refs:
            refs.append(found)
    return tuple(refs)


def resolve_canonical_id(record: dict[str, Any], facts: MarginFacts) -> str | None:
    if facts.canonical_contract_id:
        return facts.canonical_contract_id
    official = text(
        record.get("numero_controle_pncp")
        or record.get("official_id")
        or record.get("contrato_id")
        or record.get("source_record_id")
    )
    source = text(record.get("source") or record.get("source_id") or "pncp") or "pncp"
    if not official and not text(record.get("source_contract_id")):
        return None
    identity = canonical_contract_identity(
        source=source,
        official_id=official,
        source_contract_id=text(record.get("source_contract_id")),
        parent_procurement_id=text(record.get("parent_procurement_id")),
    )
    return identity.canonical_contract_id


def project_record(record: dict[str, Any], *, as_of: str, catalog_mode: str = "fixture") -> ProjectedRecord:
    extra_forbidden = FORBIDDEN_CONCLUSION_FIELDS.intersection(record)
    if extra_forbidden:
        raise ForbiddenConclusionError(f"forbidden_conclusion_fields:{sorted(extra_forbidden)}")
    facts = project_margin_facts(record, as_of=as_of)
    by_name = {fact.name: fact for fact in facts.fields}
    return ProjectedRecord(
        record=record,
        facts=facts,
        canonical_contract_id=resolve_canonical_id(record, facts),
        by_name=by_name,
        catalog_mode=catalog_mode,
    )


def fact_value(projected: ProjectedRecord, name: str) -> Any:
    fact = projected.by_name.get(name)
    if fact is None or fact.status != "KNOWN":
        return None
    return fact.value


def fact_status(projected: ProjectedRecord, name: str) -> str:
    fact = projected.by_name.get(name)
    return fact.status if fact else "UNKNOWN"


def fact_reason(projected: ProjectedRecord, name: str) -> str | None:
    fact = projected.by_name.get(name)
    return fact.reason_code if fact else "not_projected"


def nominal_amount(projected: ProjectedRecord) -> Decimal | None:
    value = fact_value(projected, "nominal_value")
    if not isinstance(value, dict):
        raw = projected.record.get("valor_total")
        if raw is None:
            raw = projected.record.get("nominal_value")
        if raw in (None, ""):
            return None
        return Decimal(str(raw))
    amount = value.get("amount")
    if isinstance(amount, Decimal):
        return amount
    if amount is None:
        return None
    return Decimal(str(amount))


def parse_as_of(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_optional_datetime(value: Any) -> datetime | None:
    found = text(value)
    if not found:
        return None
    if len(found) == 10:
        found = f"{found}T00:00:00+00:00"
    try:
        return datetime.fromisoformat(found.replace("Z", "+00:00"))
    except ValueError:
        return None


def freshness_hours(as_of: str, observed_at: str | None) -> float | None:
    observed = parse_optional_datetime(observed_at)
    if observed is None:
        return None
    try:
        cutoff = parse_as_of(as_of)
    except ValueError:
        return None
    return max(0.0, (cutoff - observed).total_seconds() / 3600.0)


def object_family(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.casefold()
    if any(token in lowered for token in ("obra", "engenharia", "reforma", "paviment", "sicro", "sinapi")):
        return "obras-engenharia"
    if any(token in lowered for token in ("limpeza", "conservacao", "portaria")):
        return "servicos-prediais"
    if any(token in lowered for token in ("software", "informatica", "ti ", "sistema")):
        return "tecnologia"
    return "outros"


def geographic_scope(record: dict[str, Any]) -> str | None:
    claimed = text(record.get("claimed_scope") or record.get("geography_kind") or record.get("scope"))
    if claimed:
        return claimed.casefold()
    if text(record.get("uf")) or text(record.get("municipio")):
        return "local"
    return None


def claims_national(record: dict[str, Any]) -> bool:
    claimed = geographic_scope(record)
    return claimed in {"nacional", "national", "br", "brasil"}


def material_fields(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "canonical_contract_id",
        "contrato_id",
        "numero_controle_pncp",
        "valor_total",
        "nominal_value",
        "data_assinatura",
        "data_inicio",
        "data_fim",
        "signed_at",
        "start_at",
        "end_at",
        "amendments",
        "aditivos",
        "apostilas",
        "value_changes",
        "term_changes",
        "scope_changes",
        "suspension",
        "resumption",
        "rescission",
        "indices",
        "documents",
        "events",
        "peer_group",
        "observed_at",
    )
    return {key: record.get(key) for key in keys if key in record}


def material_fingerprint(record: dict[str, Any]) -> str:
    return content_hash(material_fields(record))


def catalog_mode_of(record: dict[str, Any], default: str = "fixture") -> str:
    claimed = text(record.get("catalog_mode") or record.get("claimed_catalog_mode"))
    if claimed == "official_live":
        return "official_live"
    if claimed:
        return claimed
    return default
