"""Requirement × document matching and technical quantity logic."""

from __future__ import annotations

from typing import Any

from scripts.bid_readiness.extract import field_value
from scripts.bid_readiness.models import MatchStatus, TechnicalMatch

# Identity findings that block SATISFIED for eliminatory matching.
# Do not treat docs with these as "valid identity" evidence.
HARD_IDENTITY_FINDINGS = frozenset(
    {
        "CNPJ_MISMATCH",
        "LEGAL_NAME_MISMATCH",
        "REPRESENTATION_POWER_UNPROVEN",
        "SIGNATORY_NOT_FOUND",
    }
)


def _identity_hard_findings(ident: dict[str, Any]) -> list[str]:
    findings = list(ident.get("findings") or [])
    # Also derive from structured statuses when findings list is incomplete
    if ident.get("cnpj_status") == "CNPJ_MISMATCH" and "CNPJ_MISMATCH" not in findings:
        findings.append("CNPJ_MISMATCH")
    if ident.get("name_status") == "LEGAL_NAME_MISMATCH" and "LEGAL_NAME_MISMATCH" not in findings:
        findings.append("LEGAL_NAME_MISMATCH")
    if ident.get("power_status") == "REPRESENTATION_POWER_UNPROVEN":
        if "REPRESENTATION_POWER_UNPROVEN" not in findings:
            findings.append("REPRESENTATION_POWER_UNPROVEN")
    if ident.get("signatory_status") in {
        "SIGNATORY_NOT_FOUND",
        "SIGNATORY_MISMATCH",
    }:
        if "SIGNATORY_NOT_FOUND" not in findings:
            findings.append("SIGNATORY_NOT_FOUND")
    return [f for f in findings if f in HARD_IDENTITY_FINDINGS]


def match_requirement_to_documents(
    requirement: dict[str, Any],
    documents: list[dict[str, Any]],
    *,
    validity_by_doc: dict[str, dict[str, Any]],
    identity_by_doc: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Associate documents to a requirement and produce status + evidence."""
    req_type = (requirement.get("required_document_type") or "").upper()
    candidates = [
        d
        for d in documents
        if (d.get("classification") or "").upper() == req_type
        or req_type in (d.get("classification") or "").upper()
        or _title_type_hint(requirement, d)
    ]

    # Deduplicate by sha256
    seen_hash: set[str] = set()
    unique: list[dict[str, Any]] = []
    for d in candidates:
        h = d.get("sha256") or d.get("document_id")
        if not h or h in seen_hash:
            continue
        seen_hash.add(str(h))
        unique.append(d)
    candidates = unique

    if not candidates:
        if requirement.get("mandatory"):
            return _row(requirement, MatchStatus.MISSING, [], "no document of required type")
        return _row(requirement, MatchStatus.NOT_APPLICABLE, [], "optional and missing")

    # Identity / validity filters — hard identity findings never count as usable evidence
    usable: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    inconsistent: list[dict[str, Any]] = []
    identity_block_reasons: list[str] = []
    for d in candidates:
        did = d["document_id"]
        val = validity_by_doc.get(did, {})
        ident = identity_by_doc.get(did, {})
        hard = _identity_hard_findings(ident)
        if hard:
            inconsistent.append(d)
            identity_block_reasons.extend(hard)
            continue
        if val.get("status") in {"EXPIRED", "EXPIRES_BEFORE_SUBMISSION"}:
            expired.append(d)
            continue
        usable.append(d)

    if inconsistent and not usable:
        primary = identity_block_reasons[0] if identity_block_reasons else "IDENTITY_MISMATCH"
        return _row(
            requirement,
            MatchStatus.INCONSISTENT,
            [d["document_id"] for d in inconsistent],
            f"identity inconsistency: {', '.join(sorted(set(identity_block_reasons))) or primary}",
            identity_result=primary,
        )
    if expired and not usable:
        return _row(
            requirement,
            MatchStatus.EXPIRED,
            [d["document_id"] for d in expired],
            "document expired",
            validity_result=validity_by_doc.get(expired[0]["document_id"], {}).get("status"),
        )

    # Usable docs only — if mixed, prefer usable; still never SATISFY on blocked-only set
    if not usable:
        if requirement.get("mandatory"):
            return _row(requirement, MatchStatus.MISSING, [], "no usable document after identity/validity filters")
        return _row(requirement, MatchStatus.NOT_APPLICABLE, [], "optional and no usable document")

    if requirement.get("human_interpretation_required"):
        return _row(
            requirement,
            MatchStatus.NEEDS_HUMAN,
            [d["document_id"] for d in usable],
            "human interpretation required — engineer/legal review before any SATISFIED",
        )

    tech = requirement.get("technical_criteria") or {}
    if tech.get("min_quantity") is not None or tech.get("service"):
        tech_result = evaluate_technical_match(requirement, usable)
        status = _tech_to_match_status(tech_result)
        return _row(
            requirement,
            status,
            [d["document_id"] for d in usable],
            tech_result.get("reason", "technical match"),
            technical=tech_result,
            validity_result=validity_by_doc.get(usable[0]["document_id"], {}).get("status"),
            identity_result=identity_by_doc.get(usable[0]["document_id"], {}).get("cnpj_status"),
        )

    # Declaration / signature soft checks
    if requirement.get("signature_required"):
        signed = [
            d
            for d in usable
            if str(field_value(d.get("metadata") or {}, "signature_present") or "").upper()
            in {"PRESENT", "SIM", "YES", "ASSINADO", "SIGNATURE_PRESENT"}
        ]
        if not signed:
            return _row(
                requirement,
                MatchStatus.PARTIALLY_SATISFIED,
                [d["document_id"] for d in usable],
                "document present but signature missing",
            )

    # Final guard: never label SATISFIED if any selected doc still has hard identity findings
    for d in usable:
        hard = _identity_hard_findings(identity_by_doc.get(d["document_id"], {}))
        if hard:
            return _row(
                requirement,
                MatchStatus.INCONSISTENT,
                [d["document_id"]],
                f"identity inconsistency: {', '.join(hard)}",
                identity_result=hard[0],
            )

    # Default satisfied when type matched and identity/validity clean
    expiring = any(validity_by_doc.get(d["document_id"], {}).get("status") == "EXPIRING_SOON" for d in usable)
    if expiring:
        return _row(
            requirement,
            MatchStatus.EXPIRING,
            [d["document_id"] for d in usable],
            "document expiring soon",
        )

    return _row(
        requirement,
        MatchStatus.SATISFIED,
        [d["document_id"] for d in usable],
        "type match with valid identity",
        validity_result=validity_by_doc.get(usable[0]["document_id"], {}).get("status"),
        identity_result=identity_by_doc.get(usable[0]["document_id"], {}).get("cnpj_status"),
    )


def evaluate_technical_match(requirement: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Package-local CAT/atestado evidence + canonical EXTRA acervo enrichment.

    - Case vault documents (this bid package) → quantity/unit evidence for the dossier
    - ``scripts.technical_acervo`` → whether EXTRA's known portfolio supports the
      requirement (never a second acervo JSON; single ``data/extra_technical_acervo.json``)

    Duplication of portfolio matching is forbidden: acervo is always via integration.
    """
    tech = requirement.get("technical_criteria") or {}
    min_qty = tech.get("min_quantity")
    unit = (tech.get("unit") or "").lower().replace("m²", "m2")
    service = (tech.get("service") or tech.get("object") or "").lower()
    allow_sum = bool(tech.get("summable") or tech.get("somatório") or tech.get("somatorio"))
    holder = (tech.get("holder") or "company").lower()  # company|professional

    # Always query canonical EXTRA acervo when there is a technical criterion
    acervo_finding = None
    if min_qty is not None or service:
        from scripts.bid_readiness.integration import match_technical_via_acervo

        acervo_finding = match_technical_via_acervo(
            {
                "requirement_id": requirement.get("id") or requirement.get("requirement_id"),
                "service": tech.get("service") or tech.get("object") or requirement.get("text"),
                "quantity": min_qty,
                "unit": tech.get("unit") or "m2",
                "allow_sum": allow_sum,
                "mandatory": requirement.get("mandatory", True),
                "document_id": requirement.get("source_document_id"),
                "page": requirement.get("page"),
                "cell": requirement.get("cell"),
                "sheet": requirement.get("sheet"),
            }
        )

    case_result = _evaluate_technical_match_case_docs(
        requirement, documents, tech=tech, min_qty=min_qty, unit=unit, service=service, allow_sum=allow_sum, holder=holder
    )
    if acervo_finding is not None:
        case_result["source"] = "case_docs+scripts.technical_acervo.match"
        case_result["integration_finding"] = acervo_finding
        case_result["technical_acervo_evidence"] = acervo_finding.get("technical_acervo_evidence") or []
        case_result["acervo_match_status"] = acervo_finding.get("match_status")
        case_result["acervo_technical_match"] = acervo_finding.get("technical_match")
        lim = list(case_result.get("limitations") or [])
        lim.extend(acervo_finding.get("limitations") or [])
        case_result["limitations"] = lim
        if acervo_finding.get("human_action_required"):
            case_result["human_action_required"] = True
    else:
        case_result["source"] = "case_docs_only"
    return case_result


def _evaluate_technical_match_case_docs(
    requirement: dict[str, Any],
    documents: list[dict[str, Any]],
    *,
    tech: dict[str, Any],
    min_qty: Any,
    unit: str,
    service: str,
    allow_sum: bool,
    holder: str,
) -> dict[str, Any]:
    """Package-local technical evidence from bid vault documents (not EXTRA acervo store)."""

    evidence_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()  # prevent double count CAT/atestado overlap

    for d in documents:
        meta = d.get("metadata") or {}
        obj = str(field_value(meta, "obra_servico") or "").lower()
        qty = field_value(meta, "quantidade")
        doc_unit = str(field_value(meta, "unidade") or "").lower().replace("m²", "m2")
        company = str(field_value(meta, "contratada") or field_value(meta, "razao_social") or "")
        professional = str(field_value(meta, "responsavel_tecnico") or "")
        cat_n = str(field_value(meta, "cat_number") or "")
        str(field_value(meta, "art_number") or "")

        # Double-count key: prefer CAT number, else object+qty+unit
        key = cat_n or f"{obj}|{qty}|{doc_unit}|{d.get('sha256', '')[:8]}"
        if key in seen_keys:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.AMBIGUOUS.value,
                    "reason": "duplicate CAT/atestado overlap skipped",
                    "skipped_double_count": True,
                }
            )
            continue
        seen_keys.add(key)

        if holder == "professional" and not professional:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.PROFESSIONAL_MISMATCH.value,
                    "reason": "professional holder required",
                }
            )
            continue
        if holder == "company" and professional and not company and tech.get("strict_company"):
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.COMPANY_MISMATCH.value,
                    "reason": "company evidence required",
                }
            )
            continue

        if unit and doc_unit and unit != doc_unit:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.UNIT_MISMATCH.value,
                    "reason": f"unit {doc_unit} != {unit}",
                    "quantity": qty,
                    "unit": doc_unit,
                }
            )
            continue

        textual = bool(service and service in obj)
        exact_service = textual or (not service)

        try:
            qn = float(qty) if qty is not None else None
        except (TypeError, ValueError):
            qn = None

        if qn is None:
            if textual:
                evidence_items.append(
                    {
                        "document_id": d["document_id"],
                        "match": TechnicalMatch.TEXTUAL_CANDIDATE.value,
                        "reason": "textual similarity only — not proof of equivalence",
                        "quantity": None,
                        "unit": doc_unit,
                    }
                )
            else:
                evidence_items.append(
                    {
                        "document_id": d["document_id"],
                        "match": TechnicalMatch.NO_MATCH.value,
                        "reason": "no quantity/service match",
                    }
                )
            continue

        if min_qty is not None and qn + 1e-9 >= float(min_qty) and exact_service:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.EXACT_OBJECT_QUANTITY.value,
                    "reason": "quantity meets minimum",
                    "quantity": qn,
                    "unit": doc_unit or unit,
                }
            )
        elif exact_service:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.EXACT_SERVICE_PARTIAL_QUANTITY.value,
                    "reason": "service match partial quantity",
                    "quantity": qn,
                    "unit": doc_unit or unit,
                }
            )
        else:
            evidence_items.append(
                {
                    "document_id": d["document_id"],
                    "match": TechnicalMatch.TEXTUAL_CANDIDATE.value,
                    "reason": "weak textual candidate",
                    "quantity": qn,
                    "unit": doc_unit or unit,
                }
            )

    # Aggregate
    exact = [e for e in evidence_items if e["match"] == TechnicalMatch.EXACT_OBJECT_QUANTITY.value]
    if exact:
        return {
            "match_class": TechnicalMatch.EXACT_OBJECT_QUANTITY.value,
            "reason": "exact quantity satisfied",
            "evidence": evidence_items,
            "total_quantity": sum(float(e["quantity"]) for e in exact if e.get("quantity") is not None),
        }

    unit_mismatches = [e for e in evidence_items if e["match"] == TechnicalMatch.UNIT_MISMATCH.value]
    partials = [
        e
        for e in evidence_items
        if e["match"] == TechnicalMatch.EXACT_SERVICE_PARTIAL_QUANTITY.value and not e.get("skipped_double_count")
    ]

    if allow_sum and partials and not unit_mismatches:
        # only sum compatible units
        units = {e.get("unit") for e in partials}
        if len(units) == 1:
            total = sum(float(e["quantity"]) for e in partials if e.get("quantity") is not None)
            if min_qty is not None and total + 1e-9 >= float(min_qty):
                return {
                    "match_class": TechnicalMatch.COMPOSITE_SUMMABLE.value,
                    "reason": f"summed quantity {total} >= {min_qty}",
                    "evidence": evidence_items,
                    "total_quantity": total,
                }
            return {
                "match_class": TechnicalMatch.QUANTITY_INSUFFICIENT.value,
                "reason": f"summed quantity {total} < {min_qty}",
                "evidence": evidence_items,
                "total_quantity": total,
            }
        return {
            "match_class": TechnicalMatch.UNIT_MISMATCH.value,
            "reason": "cannot sum incompatible units",
            "evidence": evidence_items,
        }

    if unit_mismatches and not partials and not exact:
        return {
            "match_class": TechnicalMatch.UNIT_MISMATCH.value,
            "reason": "unit mismatch — not summed",
            "evidence": evidence_items,
        }

    if partials and min_qty is not None:
        total = sum(float(e.get("quantity") or 0) for e in partials)
        return {
            "match_class": TechnicalMatch.QUANTITY_INSUFFICIENT.value,
            "reason": f"quantity {total} < {min_qty}",
            "evidence": evidence_items,
            "total_quantity": total,
        }

    textual_only = all(
        e["match"] in {TechnicalMatch.TEXTUAL_CANDIDATE.value, TechnicalMatch.NO_MATCH.value} for e in evidence_items
    )
    if textual_only and evidence_items:
        return {
            "match_class": TechnicalMatch.TEXTUAL_CANDIDATE.value,
            "reason": "textual candidate only — NEEDS_ENGINEER_REVIEW; not technical proof",
            "evidence": evidence_items,
            "needs_engineer_review": True,
        }

    return {
        "match_class": TechnicalMatch.NEEDS_ENGINEER_REVIEW.value,
        "reason": "insufficient automatic technical proof",
        "evidence": evidence_items,
        "needs_engineer_review": True,
    }


def _tech_to_match_status(tech_result: dict[str, Any]) -> MatchStatus:
    mc = tech_result.get("match_class")
    if mc == TechnicalMatch.EXACT_OBJECT_QUANTITY.value:
        return MatchStatus.SATISFIED
    if mc == TechnicalMatch.COMPOSITE_SUMMABLE.value:
        return MatchStatus.SATISFIED
    if mc == TechnicalMatch.QUANTITY_INSUFFICIENT.value:
        return MatchStatus.PARTIALLY_SATISFIED
    if mc == TechnicalMatch.UNIT_MISMATCH.value:
        return MatchStatus.INCONSISTENT
    if mc == TechnicalMatch.TEXTUAL_CANDIDATE.value:
        return MatchStatus.NEEDS_HUMAN  # never SATISFIED on text alone
    if mc in {
        TechnicalMatch.NEEDS_ENGINEER_REVIEW.value,
        TechnicalMatch.AMBIGUOUS.value,
    }:
        return MatchStatus.NEEDS_HUMAN
    if mc == TechnicalMatch.NO_MATCH.value:
        return MatchStatus.MISSING
    return MatchStatus.NEEDS_HUMAN


def _title_type_hint(requirement: dict[str, Any], doc: dict[str, Any]) -> bool:
    (requirement.get("title") or "").lower()
    (doc.get("original_name") or "").lower()
    return False  # do not match on filename alone


def _row(
    requirement: dict[str, Any],
    status: MatchStatus,
    document_ids: list[str],
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement["requirement_id"],
        "status": status.value,
        "document_ids": document_ids,
        "source_locators": [requirement.get("source_locator")],
        "evidence": reason,
        "validation_rules": {
            "mandatory": requirement.get("mandatory"),
            "required_document_type": requirement.get("required_document_type"),
        },
        "validity_result": extra.get("validity_result"),
        "identity_result": extra.get("identity_result"),
        "technical": extra.get("technical"),
        "limitations": [
            "Automated match is operational support only; not legal habilitation.",
            "Semantic similarity alone never proves technical equivalence.",
        ],
        "human_action": (
            "Review technical evidence" if status in {MatchStatus.NEEDS_HUMAN, MatchStatus.AMBIGUOUS} else None
        ),
        "mandatory": bool(requirement.get("mandatory")),
        "category": requirement.get("category"),
        "title": requirement.get("title"),
    }
