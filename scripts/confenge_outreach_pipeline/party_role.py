"""Fail-closed projection of public-contract party roles for outbound."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CONTRACTOR_ROLE_CONFIRMED = "CONTRACTOR_ROLE_CONFIRMED"
PARTY_ROLE_CONFLICT = "PARTY_ROLE_CONFLICT"
PARTY_ROLE_UNKNOWN = "UNKNOWN"
PARTY_ROLE_POLICY_V1 = "contract-party-role.v1"


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _cnpj14(value: Any) -> str:
    value = _digits(value)
    return value if len(value) == 14 else ""


def project_contractor_role(
    lead_cnpj: Any,
    contracts: list[dict[str, Any]],
    *,
    source_run_id: str = "",
    observed_at: str = "",
) -> dict[str, Any]:
    """Prove that the lead is supplier, never merely present in a contract."""
    lead = _cnpj14(lead_cnpj)
    valid: list[dict[str, str]] = []
    root_only: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        supplier = _cnpj14(
            contract.get("supplier_cnpj14") or contract.get("fornecedor_cnpj") or contract.get("supplier_cnpj")
        )
        buyer = _cnpj14(contract.get("buyer_cnpj14") or contract.get("orgao_cnpj") or contract.get("buyer_cnpj"))
        contract_id = str(contract.get("id") or contract.get("contrato_id") or "").strip()
        supplier_role = str(contract.get("supplier_role") or "").upper().strip()
        buyer_role = str(contract.get("buyer_role") or "").upper().strip()
        fact = {
            "contract_id": contract_id,
            "supplier_cnpj14": supplier,
            "buyer_cnpj14": buyer,
            "supplier_role": supplier_role,
            "buyer_role": buyer_role,
        }
        if lead and buyer and (lead == buyer or lead[:8] == buyer[:8]):
            conflicts.append(fact)
            continue
        supplier_semantic = supplier_role in {
            "CONTRATADA",
            "FORNECEDORA",
            "EXECUTORA",
            "ADJUDICATARIA_CONTRATADA",
            "ADJUDICATARIA",
            "ADJUDICATÁRIA",
            "ADJUDICATÁRIA/CONTRATADA",
        }
        buyer_semantic = buyer_role in {
            "CONTRATANTE",
            "ORGAO_CONTRATANTE",
            "ÓRGÃO CONTRATANTE",
            "ENTIDADE_PUBLICA_COMPRADORA",
            "ENTIDADE PÚBLICA COMPRADORA",
            "UNIDADE_GESTORA",
            "UNIDADE GESTORA",
            "ADMINISTRACAO_PUBLICA",
            "ADMINISTRAÇÃO PÚBLICA",
        }
        if lead and supplier and buyer and supplier_semantic and buyer_semantic:
            if lead == supplier and not (lead == buyer or lead[:8] == buyer[:8]):
                valid.append(fact)
            elif lead[:8] == supplier[:8] and not (lead == buyer or lead[:8] == buyer[:8]):
                # A shared CNPJ root does not prove that a recipient or public
                # contract of one establishment belongs to another. Keep the
                # typed evidence for audit, but require a branch-specific link
                # before delegated approval.
                root_only.append(fact)

    status = PARTY_ROLE_UNKNOWN
    target_party_role = "UNKNOWN"
    match_method = "NONE"
    confidence = "UNKNOWN"
    reason_codes = ["party_role_evidence_missing"]
    facts: list[dict[str, str]] = []
    if conflicts:
        status = PARTY_ROLE_CONFLICT
        target_party_role = "BUYER_CONFLICT"
        match_method = (
            "BUYER_EXACT_CNPJ14"
            if any(lead == fact["buyer_cnpj14"] for fact in conflicts)
            else "BUYER_CNPJ_ROOT"
        )
        confidence = "CONFLICT"
        reason_codes = ["lead_matches_contracting_authority"]
        facts = conflicts
    elif valid:
        status = CONTRACTOR_ROLE_CONFIRMED
        target_party_role = "SUPPLIER"
        match_method = "SUPPLIER_EXACT_CNPJ14"
        confidence = "HIGH"
        reason_codes = ["lead_matches_supplier", "lead_differs_from_buyer"]
        facts = valid
    elif root_only:
        match_method = "SUPPLIER_CNPJ_ROOT"
        confidence = "MEDIUM"
        reason_codes = ["supplier_root_only_requires_specific_branch_evidence"]
        facts = root_only

    canonical = {
        "lead_cnpj14": lead,
        "status": status,
        "target_party_role": target_party_role,
        "role_match_method": match_method,
        "confidence": confidence,
        "policy_version": PARTY_ROLE_POLICY_V1,
        "source_run_id": source_run_id,
        "observed_at": observed_at,
        "facts": sorted(facts, key=lambda item: json.dumps(item, sort_keys=True)),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    supplier_cnpj14 = facts[0]["supplier_cnpj14"] if facts else ""
    buyer_cnpj14 = facts[0]["buyer_cnpj14"] if facts else ""
    return {
        "status": status,
        "target_party_role": target_party_role,
        "policy_version": PARTY_ROLE_POLICY_V1,
        "source": "extra-cli:v_contracts_canonical_v2",
        "source_run_id": source_run_id,
        "observed_at": observed_at,
        "evidence_hash": digest,
        "evidence_reference": f"extra-cli:v_contracts_canonical_v2:sha256:{digest}",
        "evidence_ids": [fact["contract_id"] for fact in facts if fact["contract_id"]],
        "reason_codes": reason_codes,
        "supplier_cnpj14": supplier_cnpj14,
        "supplier_identity_ref": f"cnpj:{supplier_cnpj14}" if supplier_cnpj14 else "",
        "buyer_cnpj14": buyer_cnpj14,
        "buyer_identity_ref": f"cnpj:{buyer_cnpj14}" if buyer_cnpj14 else "",
        "role_match_method": match_method,
        "confidence": confidence,
    }
