"""Immutable, hashable evidence pack. No brand, SEO, CTA or accusation."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from scripts.contract_publication.facts import (
    ProjectedRecord,
    explicit_evidence_refs,
    fact_value,
    parse_optional_datetime,
    text,
)
from scripts.contract_publication.models import Candidate, DetectorResult
from scripts.contract_publication.schema import (
    PACK_SCHEMA,
    SCORE_FORMULA_VERSION,
    canonical_dumps,
    hash_without_content_hash,
    producer_sha,
)
from scripts.contracts_identity import cpf_export_mask, normalize_supplier_identity
from scripts.linkage.keys import digits_only, is_valid_cpf11
from scripts.public_read.export import assert_truth_plane_clean

_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+55[\s-]?)?(?:\(?[1-9]\d\)?[\s-]?)(?:9\d{4}[\s-]?\d{4}|[2-8]\d{3}[\s-]?\d{4})(?!\d)")
_CPF_DIGITS = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_PII_KEYS = frozenset({"email", "phone", "telefone", "rg", "home_address", "endereco_residencial", "cpf"})


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


def _item(
    item_id: str, cls: str, value: Any, *, reason: str | None, refs: tuple[str, ...], limitation: str | None = None
) -> dict[str, Any]:
    payload = {
        "id": item_id,
        "epistemic_class": cls,
        "class": cls,
        "value": value,
        "reason_code": reason,
        "evidence_refs": list(refs),
    }
    if limitation:
        payload["limitation"] = limitation
    return payload


def _mask_text(blob: str) -> tuple[str, bool]:
    changed = False
    cleaned = _EMAIL.sub("[REDACTED_EMAIL]", blob)
    if cleaned != blob:
        changed = True
    next_text = _PHONE.sub("[REDACTED_PHONE]", cleaned)
    if next_text != cleaned:
        changed = True
        cleaned = next_text

    def _mask(match: re.Match[str]) -> str:
        digits = digits_only(match.group(1))
        if is_valid_cpf11(digits):
            nonlocal changed
            changed = True
            return cpf_export_mask()
        return match.group(1)

    return _CPF_DIGITS.sub(_mask, cleaned), changed


def _sanitize(node: Any) -> tuple[Any, list[str]]:
    stripped: list[str] = []
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            folded = str(key).strip().lower()
            if folded in _PII_KEYS:
                stripped.append(folded)
                continue
            child, child_stripped = _sanitize(value)
            stripped.extend(child_stripped)
            out[key] = child
        return out, stripped
    if isinstance(node, list):
        items = []
        for value in node:
            child, child_stripped = _sanitize(value)
            stripped.extend(child_stripped)
            items.append(child)
        return items, stripped
    if isinstance(node, str):
        cleaned, changed = _mask_text(node)
        if changed:
            stripped.append("inline_pii")
        return cleaned, stripped
    return node, stripped


def official_locator_refs(projected: ProjectedRecord) -> tuple[str, ...]:
    refs = list(explicit_evidence_refs(projected.record))
    for key in ("source_record_id", "numero_controle_pncp", "canonical_contract_id", "source_id"):
        found = text(projected.record.get(key))
        if key == "canonical_contract_id":
            found = found or projected.canonical_contract_id
        if key == "source_id":
            found = found or projected.facts.source_id
        if found and found not in refs:
            refs.append(f"official:{found}")
    return tuple(refs)


def _timeline(projected: ProjectedRecord) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for name in ("amendments", "value_changes", "term_changes", "scope_changes", "suspension", "resumption"):
        value = fact_value(projected, name)
        items = value if isinstance(value, (list, tuple)) else ((value,) if value else ())
        for item in items:
            if not isinstance(item, dict):
                continue
            stamp = item.get("at") or item.get("effective_at") or item.get("published_at")
            locators = official_locator_refs(projected)
            refs = _fact_refs(
                [ref for ref in (item.get("ref"), item.get("evidence_ref")) if ref],
                locators,
            )
            if not refs:
                continue
            events.append(
                {
                    "kind": name,
                    "at": stamp,
                    "id": item.get("id") or item.get("source_event_id"),
                    "epistemic_class": "FACT",
                    "evidence_refs": refs,
                }
            )
    locators = official_locator_refs(projected)
    for item in projected.record.get("events") or ():
        if isinstance(item, dict):
            refs = _fact_refs(
                [ref for ref in (item.get("ref"), item.get("raw_hash")) if ref],
                locators,
            )
            if not refs:
                continue
            events.append(
                {
                    "kind": item.get("family") or "event",
                    "at": item.get("effective_at") or item.get("at"),
                    "id": item.get("source_event_id") or item.get("id"),
                    "epistemic_class": "FACT",
                    "evidence_refs": refs,
                }
            )
    events.sort(key=lambda row: (str(row.get("at") or ""), str(row.get("kind") or ""), str(row.get("id") or "")))
    return events


def _calculations(projected: ProjectedRecord, detectors: tuple[DetectorResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    locators = official_locator_refs(projected)
    for item in detectors:
        if item.epistemic_class != "CALCULATION" or item.result is None:
            continue
        refs = list(item.evidence_refs) or list(locators)
        if not refs:
            continue
        rows.append(
            {
                "name": item.detector_id,
                "value": item.result,
                "unit": None,
                "epistemic_class": "CALCULATION",
                "method": item.method,
                "evidence_refs": refs,
                "reason_code": item.reason_code,
            }
        )
    start = parse_optional_datetime(fact_value(projected, "start_at") or projected.record.get("data_inicio"))
    end = parse_optional_datetime(fact_value(projected, "end_at") or projected.record.get("data_fim"))
    if start and end:
        refs = list(official_locator_refs(projected))
        if refs:
            days = (end - start).days
            rows.append(
                {
                    "name": "term_days",
                    "value": days,
                    "unit": "day",
                    "epistemic_class": "CALCULATION",
                    "method": {
                        "id": "term_days/1.0",
                        "version": "1.0",
                        "description": "end_at - start_at in days",
                    },
                    "evidence_refs": refs,
                    "reason_code": "term_interval",
                }
            )
    return rows


def _facts(projected: ProjectedRecord) -> list[dict[str, Any]]:
    rows = []
    locators = official_locator_refs(projected)
    for fact in projected.facts.fields:
        if fact.status != "KNOWN":
            continue
        value = fact.value
        if isinstance(value, Decimal):
            value = format(value, "f")
        refs = (fact.evidence_ref,) if fact.evidence_ref else locators
        if not refs:
            continue
        rows.append(_item(fact.name, "FACT", value, reason=None, refs=refs))
    return rows


def _unknowns(projected: ProjectedRecord, detectors: tuple[DetectorResult, ...]) -> list[dict[str, Any]]:
    rows = []
    for fact in projected.facts.fields:
        if fact.status == "UNKNOWN":
            rows.append(_item(fact.name, "UNKNOWN", None, reason=fact.reason_code, refs=()))
    for item in detectors:
        if item.status == "UNKNOWN":
            rows.append(_item(item.detector_id, "UNKNOWN", None, reason=item.reason_code, refs=()))
    return rows


def _inferences(detectors: tuple[DetectorResult, ...]) -> list[dict[str, Any]]:
    return [
        _item(
            item.detector_id,
            "INFERENCE",
            item.result,
            reason=item.reason_code,
            refs=item.evidence_refs,
            limitation=";".join(item.limitations) if item.limitations else None,
        )
        for item in detectors
        if item.epistemic_class == "INFERENCE"
    ]


def _peer(projected: ProjectedRecord) -> dict[str, Any]:
    provided = projected.record.get("peer_group")
    if not isinstance(provided, dict):
        return {
            "status": "ABSENT",
            "schema": None,
            "version": None,
            "content_hash": None,
            "metrics": {},
            "limitation": "peer_group_absent",
        }
    status = text(provided.get("status")) or "ABSENT"
    if status in {"NOT_COMPARABLE", "NO_VALID_PEER_GROUP"}:
        mapped = "NOT_COMPARABLE"
    elif status == "HOLD_FOR_DATA":
        mapped = "HOLD_FOR_DATA"
    elif status == "COMPARABLE":
        mapped = "COMPARABLE"
    else:
        mapped = status
    return {
        "status": mapped,
        "schema": provided.get("schema"),
        "version": provided.get("version") or provided.get("contract_version"),
        "content_hash": provided.get("content_hash"),
        "metrics": provided.get("metrics")
        or {"sample_size": provided.get("sample_size"), "median_value": provided.get("median_value")},
        "limitation": provided.get("limitation"),
        "catalog_mode": provided.get("catalog_mode") or "fixture",
    }


def _fact_refs(*groups: list[str] | tuple[str, ...]) -> list[str]:
    refs: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in refs:
                refs.append(item)
    return refs


def _values(projected: ProjectedRecord) -> list[dict[str, Any]]:
    rows = []
    locators = official_locator_refs(projected)
    nominal = fact_value(projected, "nominal_value")
    if isinstance(nominal, dict):
        refs = _fact_refs(explicit_evidence_refs(projected.record), locators)
        if refs:
            rows.append(
                {
                    "kind": "nominal_instrument",
                    "amount": str(nominal.get("amount")),
                    "currency": nominal.get("currency") or "BRL",
                    "semantics": nominal.get("semantics") or "integral_nominal_instrument",
                    "epistemic_class": "FACT",
                    "evidence_refs": refs,
                }
            )
    for change in fact_value(projected, "value_changes") or ():
        if isinstance(change, dict):
            refs = _fact_refs(
                [ref for ref in (change.get("ref"), change.get("evidence_ref")) if ref],
                locators,
            )
            if not refs:
                continue
            rows.append(
                {
                    "kind": "value_change",
                    "amount": change.get("delta") or change.get("value_delta"),
                    "currency": "BRL",
                    "semantics": "documented_delta",
                    "epistemic_class": "FACT",
                    "evidence_refs": refs,
                }
            )
    return rows


def _coverage(projected: ProjectedRecord, unknowns: list[dict[str, Any]]) -> dict[str, Any]:
    known = projected.facts.known_count
    total = len(projected.facts.fields)
    return {
        "known_fields": known,
        "total_fields": total,
        "missing_fields": total - known,
        "unknown_items": len(unknowns),
        "document_count": len(explicit_evidence_refs(projected.record)),
    }


def build_evidence_pack(projected: ProjectedRecord, candidate: Candidate) -> dict[str, Any]:
    refs = explicit_evidence_refs(projected.record)
    organ = fact_value(projected, "organ")
    contractor = fact_value(projected, "contractor")
    identity = normalize_supplier_identity(
        projected.record.get("fornecedor_cnpj")
        or projected.record.get("contractor_id")
        or projected.record.get("fornecedor_cpf")
        or projected.record.get("cpf"),
        declared_type=projected.record.get("fornecedor_tipo") or projected.record.get("contractor_type"),
        country=projected.record.get("fornecedor_pais"),
    )
    contractor_export = None
    if identity.supplier_id_type == "CPF":
        contractor_export = {
            "id_type": "CPF",
            "export": cpf_export_mask(),
            "name": (contractor or {}).get("name") if isinstance(contractor, dict) else None,
        }
    elif identity.supplier_id_type == "CNPJ":
        contractor_export = {
            "id_type": "CNPJ",
            "export": identity.fornecedor_cnpj,
            "name": (contractor or {}).get("name") if isinstance(contractor, dict) else None,
        }
    elif isinstance(contractor, dict):
        contractor_export = {"id_type": "UNKNOWN", "export": None, "name": contractor.get("name")}

    facts = _facts(projected)
    calculations = _calculations(projected, candidate.detectors)
    inferences = _inferences(candidate.detectors)
    unknowns = _unknowns(projected, candidate.detectors)
    timeline = _timeline(projected)
    documents = []
    locators = official_locator_refs(projected)
    for item in projected.record.get("documents") or ():
        if isinstance(item, dict):
            refs = _fact_refs(
                [
                    ref
                    for ref in (item.get("id"), item.get("ref"), item.get("sha256"), item.get("hash"), item.get("url"))
                    if ref
                ],
                locators,
            )
            if not refs:
                continue
            documents.append(
                {
                    "id": item.get("id") or item.get("ref"),
                    "type": item.get("type"),
                    "sha256": item.get("sha256") or item.get("hash"),
                    "url": item.get("url"),
                    "epistemic_class": "FACT",
                    "evidence_refs": refs,
                }
            )
    source_urls = []
    for item in projected.record.get("source_urls") or ():
        if isinstance(item, dict):
            source_urls.append(item.get("url"))
        else:
            source_urls.append(item)
    raw_refs = [
        {"ref": item.get("raw_uri") or item.get("raw_ref"), "sha256": item.get("sha256")}
        for item in projected.record.get("documents") or ()
        if isinstance(item, dict) and (item.get("raw_uri") or item.get("sha256"))
    ]
    limitations = sorted(
        {
            *sum((list(item.limitations) for item in candidate.detectors), []),
            *([code for code in candidate.reason_codes if code.startswith("missing_")]),
        }
    )
    document = {
        "schema": PACK_SCHEMA,
        "contract_version": candidate.contract_version,
        "producer_sha": producer_sha(),
        "policy_version": SCORE_FORMULA_VERSION,
        "analysis_candidate_id": candidate.analysis_candidate_id,
        "canonical_contract_ids": [candidate.canonical_contract_id] if candidate.canonical_contract_id else [],
        "process_ids": [text(projected.record.get("process_id") or projected.record.get("parent_procurement_id"))]
        if text(projected.record.get("process_id") or projected.record.get("parent_procurement_id"))
        else [],
        "organ": organ,
        "contractor": contractor_export,
        "object": fact_value(projected, "object"),
        "location": {
            "municipality": text(projected.record.get("municipio")),
            "uf": text(projected.record.get("uf")),
        },
        "values": _values(projected),
        "dates": {
            "signed_at": fact_value(projected, "signed_at"),
            "start_at": fact_value(projected, "start_at"),
            "end_at": fact_value(projected, "end_at"),
            "term": fact_value(projected, "term"),
        },
        "terms": fact_value(projected, "term"),
        "amendments": fact_value(projected, "amendments"),
        "apostilles": projected.record.get("apostilas") or projected.record.get("apostilles"),
        "documents": documents,
        "source_urls": [url for url in source_urls if url],
        "raw_refs": raw_refs,
        "facts": facts,
        "calculations": calculations,
        "inferences": inferences,
        "unknowns": unknowns,
        "timeline": timeline,
        "official_refs": [{"url": url} for url in source_urls if url] + [{"ref": ref} for ref in refs],
        "peer_group": _peer(projected),
        "score": candidate.publication_value_score.as_dict(),
        "components": {item.name: item.as_dict() for item in candidate.components},
        "reason_codes": list(candidate.reason_codes),
        "as_of": candidate.as_of,
        "coverage": _coverage(projected, unknowns),
        "freshness": {
            "generated_at": candidate.as_of,
            "source_as_of": candidate.as_of,
            "observed_at": candidate.observed_at,
            "age_hours": candidate.freshness_hours,
            "status": candidate.freshness_status,
            "max_age_hours": 48,
        },
        "missingness": list(candidate.missing),
        "limitations": limitations,
        "sensitivity_flags": list(candidate.sensitivity_flags),
        "candidate_state": candidate.candidate_state,
        "catalog_mode": candidate.catalog_mode,
        "material_fingerprint": candidate.material_fingerprint,
        "epistemic_classes": ["FACT", "CALCULATION", "INFERENCE", "UNKNOWN"],
    }
    cleaned, stripped = _sanitize(_jsonable(document))
    if not isinstance(cleaned, dict):
        raise TypeError("sanitized pack must be a mapping")
    if stripped:
        cleaned.setdefault("reason_codes", [])
        if "UNNECESSARY_PII_STRIPPED" not in cleaned["reason_codes"]:
            cleaned["reason_codes"] = [*cleaned["reason_codes"], "UNNECESSARY_PII_STRIPPED"]
    assert_every_fact_has_ref(cleaned)
    assert_inferences_not_facts(cleaned)
    assert_truth_plane_clean(cleaned)
    cleaned["content_hash"] = hash_without_content_hash(cleaned)
    return cleaned


def iter_epistemic_nodes(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        cls = node.get("epistemic_class") or node.get("class")
        if cls in {"FACT", "CALCULATION"}:
            found.append((path or "root", node))
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            found.extend(iter_epistemic_nodes(value, next_path))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(iter_epistemic_nodes(item, f"{path}[{index}]"))
    return found


def assert_every_fact_has_ref(document: dict[str, Any]) -> None:
    for path, item in iter_epistemic_nodes(document):
        if item.get("epistemic_class") in {"FACT", "CALCULATION"} or item.get("class") in {"FACT", "CALCULATION"}:
            if not item.get("evidence_refs"):
                raise ValueError(
                    f"missing_evidence_ref:{path}:{item.get('id') or item.get('name') or item.get('kind')}"
                )


def assert_inferences_not_facts(document: dict[str, Any]) -> None:
    for item in document.get("inferences") or ():
        if item.get("epistemic_class") == "FACT" or item.get("class") == "FACT":
            raise ValueError("inference_serialized_as_fact")
    for item in document.get("facts") or ():
        if item.get("epistemic_class") == "INFERENCE":
            raise ValueError("inference_serialized_as_fact")


def render_pack(document: dict[str, Any]) -> str:
    return canonical_dumps(document)
