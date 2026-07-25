"""Identity and representation consistency checks."""

from __future__ import annotations

from typing import Any

from scripts.bid_readiness.extract import field_value
from scripts.bid_readiness.models import digits_only, names_equivalent


def evaluate_identity(
    *,
    metadata: dict[str, Any],
    expected_cnpj: str | None,
    expected_legal_name: str | None,
    expected_signatory: str | None = None,
    representation_powers_required: list[str] | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    findings: list[str] = []
    doc_cnpj = digits_only(str(field_value(metadata, "cnpj") or ""))
    exp_cnpj = digits_only(expected_cnpj or "")
    doc_name = field_value(metadata, "razao_social") or field_value(metadata, "titular")
    signatory = field_value(metadata, "signatario")
    powers = str(field_value(metadata, "poder_representacao") or "").lower()

    cnpj_status = "OK"
    if exp_cnpj and doc_cnpj:
        if doc_cnpj != exp_cnpj:
            cnpj_status = "CNPJ_MISMATCH"
            findings.append("CNPJ_MISMATCH")
    elif exp_cnpj and not doc_cnpj:
        cnpj_status = "CNPJ_NOT_FOUND"
        findings.append("POSSIBLE_STALE_DATA")

    name_status = "OK"
    if expected_legal_name and doc_name:
        if names_equivalent(str(doc_name), expected_legal_name):
            name_status = "OK_ABBREVIATION_TOLERANT"
        else:
            name_status = "LEGAL_NAME_MISMATCH"
            findings.append("LEGAL_NAME_MISMATCH")
    elif expected_legal_name and not doc_name:
        name_status = "NAME_NOT_FOUND"

    signatory_status = "OK"
    if expected_signatory:
        if not signatory:
            signatory_status = "SIGNATORY_NOT_FOUND"
            findings.append("SIGNATORY_NOT_FOUND")
        elif (
            names_equivalent(str(signatory), expected_signatory)
            or str(signatory).upper() in str(expected_signatory).upper()
            or str(expected_signatory).upper() in str(signatory).upper()
        ):
            signatory_status = "SIGNATORY_MATCH"
        else:
            signatory_status = "SIGNATORY_MISMATCH"
            findings.append("SIGNATORY_NOT_FOUND")

    power_status = "OK"
    required_powers = representation_powers_required or []
    if classification == "PROCURACAO" or required_powers:
        if not powers:
            power_status = "REPRESENTATION_POWER_UNPROVEN"
            findings.append("REPRESENTATION_POWER_UNPROVEN")
        else:
            missing = [p for p in required_powers if p.lower() not in powers]
            if missing:
                power_status = "REPRESENTATION_POWER_UNPROVEN"
                findings.append("REPRESENTATION_POWER_UNPROVEN")
            elif "licita" not in powers and "proposta" not in powers and required_powers:
                power_status = "REPRESENTATION_POWER_UNPROVEN"
                findings.append("REPRESENTATION_POWER_UNPROVEN")

    needs_human = any(
        x in findings
        for x in (
            "REPRESENTATION_POWER_UNPROVEN",
            "SIGNATORY_NOT_FOUND",
        )
    )
    if name_status == "NAME_NOT_FOUND":
        findings.append("NEEDS_HUMAN")
        needs_human = True

    return {
        "cnpj_status": cnpj_status,
        "name_status": name_status,
        "signatory_status": signatory_status,
        "power_status": power_status,
        "document_cnpj": doc_cnpj or None,
        "expected_cnpj": exp_cnpj or None,
        "document_name": doc_name,
        "expected_name": expected_legal_name,
        "findings": findings,
        "needs_human": needs_human,
    }
