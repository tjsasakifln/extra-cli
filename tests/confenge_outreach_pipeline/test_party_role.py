from __future__ import annotations

from scripts.confenge_outreach_pipeline.party_role import (
    CONTRACTOR_ROLE_CONFIRMED,
    PARTY_ROLE_CONFLICT,
    PARTY_ROLE_UNKNOWN,
    project_contractor_role,
)


def _contract(*, supplier: str, buyer: str) -> dict[str, str]:
    return {
        "id": "contract-1",
        "supplier_cnpj14": supplier,
        "supplier_role": "CONTRATADA",
        "buyer_cnpj14": buyer,
        "buyer_role": "CONTRATANTE",
    }


def test_supplier_root_without_branch_specific_evidence_stays_unknown() -> None:
    result = project_contractor_role(
        "11222333000225",
        [_contract(supplier="11222333000144", buyer="99888777000166")],
        source_run_id="run-1",
        observed_at="2026-08-25T12:00:00Z",
    )
    assert result["status"] == PARTY_ROLE_UNKNOWN
    assert result["target_party_role"] == "UNKNOWN"
    assert result["role_match_method"] == "SUPPLIER_CNPJ_ROOT"
    assert result["confidence"] == "MEDIUM"
    assert result["reason_codes"] == ["supplier_root_only_requires_specific_branch_evidence"]
    assert result["supplier_cnpj14"] == "11222333000144"
    assert result["supplier_identity_ref"] == "cnpj:11222333000144"
    assert result["buyer_cnpj14"] == "99888777000166"
    assert result["buyer_identity_ref"] == "cnpj:99888777000166"
    assert result["evidence_ids"] == ["contract-1"]
    assert result["evidence_reference"].endswith(result["evidence_hash"])


def test_contracting_authority_match_is_conflict_even_if_supplier_is_present() -> None:
    result = project_contractor_role(
        "11222333000144",
        [_contract(supplier="99888777000166", buyer="11222333000144")],
    )
    assert result["status"] == PARTY_ROLE_CONFLICT
    assert result["target_party_role"] == "BUYER_CONFLICT"
    assert result["role_match_method"] == "BUYER_EXACT_CNPJ14"
    assert result["confidence"] == "CONFLICT"
    assert result["reason_codes"] == ["lead_matches_contracting_authority"]


def test_unknown_is_never_promoted_to_contractor() -> None:
    result = project_contractor_role(
        "11222333000144",
        [{"id": "contract-1", "supplier_role": "UNKNOWN", "buyer_role": "CONTRATANTE"}],
    )
    assert result["status"] == PARTY_ROLE_UNKNOWN
    assert result["target_party_role"] == "UNKNOWN"
    assert result["role_match_method"] == "NONE"


def test_missing_role_labels_are_not_defaulted_to_contractor() -> None:
    result = project_contractor_role(
        "11222333000144",
        [{"id": "contract-1", "supplier_cnpj14": "11222333000144", "buyer_cnpj14": "99888777000166"}],
    )
    assert result["status"] == PARTY_ROLE_UNKNOWN


def test_exact_supplier_match_is_high_confidence() -> None:
    result = project_contractor_role(
        "11222333000144",
        [_contract(supplier="11222333000144", buyer="99888777000166")],
    )
    assert result["status"] == CONTRACTOR_ROLE_CONFIRMED
    assert result["role_match_method"] == "SUPPLIER_EXACT_CNPJ14"
    assert result["confidence"] == "HIGH"


def test_correct_contract_plus_conflicting_buyer_link_fails_closed() -> None:
    correct = _contract(supplier="11222333000144", buyer="99888777000166")
    conflict = {**_contract(supplier="88777666000155", buyer="11222333000144"), "id": "contract-2"}
    result = project_contractor_role("11222333000144", [correct, conflict])
    assert result["status"] == PARTY_ROLE_CONFLICT
    assert result["target_party_role"] == "BUYER_CONFLICT"
    assert result["evidence_ids"] == ["contract-2"]


def test_same_cnpj_on_both_sides_is_conflict_not_supplier() -> None:
    result = project_contractor_role(
        "11222333000144",
        [_contract(supplier="11222333000144", buyer="11222333000144")],
    )
    assert result["status"] == PARTY_ROLE_CONFLICT


def test_role_labels_must_be_semantically_typed() -> None:
    row = _contract(supplier="11222333000144", buyer="99888777000166")
    row["supplier_role"] = "BUYER"
    assert project_contractor_role("11222333000144", [row])["status"] == PARTY_ROLE_UNKNOWN


def test_evidence_hash_is_deterministic() -> None:
    contracts = [_contract(supplier="11222333000144", buyer="99888777000166")]
    first = project_contractor_role("11222333000144", contracts, source_run_id="run-1")
    second = project_contractor_role("11222333000144", list(reversed(contracts)), source_run_id="run-1")
    assert first["evidence_hash"] == second["evidence_hash"]
