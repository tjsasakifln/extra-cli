"""COMMERCIAL_AUTHORITY/2.0 producer contract.

The canonical rule: a CONFENGE lead is qualified by evidence that it was the
CONTRACTED SUPPLIER on a public engineering work or service inside a rolling
three-year window. Source/crawler freshness is acquisition health and must
never revoke that fact.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from scripts.confenge_activation.commercial_authority_v2 import (
    CONTRACT_VERSION,
    POLICY_VERSION,
    QUALIFICATION_WINDOW_YEARS,
    REASON_NO_QUALIFYING_CONTRACT,
    REASON_ROLE_INVALID,
    STATE_QUALIFIED,
    STATE_REVOKED,
    add_years_go,
    build_population_authority,
    contracting_date,
    corpus_hash,
    evidence_hash,
    qualified_until,
    qualify_root,
    validate_root_qualification,
    window_floor,
)

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "commercial_authority_v2" / "golden.json").read_text())

NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def _contract(contract_id: str, **dates) -> dict:
    return {"contrato_id": contract_id, **dates}


def test_cross_language_golden_vector_matches_warmbly():
    """Warmbly pins the same vector. A drift makes the runtime fail closed."""
    from scripts.confenge_activation.commercial_authority_v2 import RootQualification

    spec = GOLDEN["qualification"]
    q = RootQualification(
        cnpj_root8=spec["cnpj_root8"],
        target_fit_class="TARGET_CONFIRMED",
        party_role=spec["party_role"],
        qualifying_contract_id=spec["qualifying_contract_id"],
        qualifying_contract_date=spec["qualifying_contract_date"],
        qualifying_date_field=spec["qualifying_date_field"],
        qualifying_contract_count=1,
        qualified_until=spec["qualified_until"],
        qualification_evidence_reference=spec["qualification_evidence_reference"],
        provenance="extra-cli:v_contracts_canonical_v2",
    )
    assert evidence_hash(q) == GOLDEN["expected_evidence_hash"]
    signed = RootQualification(**{**q.__dict__, "qualification_evidence_hash": evidence_hash(q)})
    assert corpus_hash([signed]) == GOLDEN["expected_corpus_hash"]


def test_leap_day_normalization_matches_go_add_date():
    leap = GOLDEN["leap_normalization"]
    got = qualified_until(date.fromisoformat(leap["contract_date"]))
    assert got.isoformat() == leap["qualified_until"]
    assert add_years_go(date(2024, 2, 29), 3) == date(2027, 3, 1)


def test_qualifying_date_precedence_is_the_contracting_act():
    """assinatura wins, then inicio, then publicacao. data_fim is never used."""
    resolved, field = contracting_date(
        _contract(
            "c1",
            data_assinatura="2025-03-01",
            data_inicio="2025-04-01",
            data_publicacao="2025-05-01",
            data_fim="2030-01-01",
        )
    )
    assert (resolved, field) == (date(2025, 3, 1), "data_assinatura")

    resolved, field = contracting_date(_contract("c2", data_inicio="2025-04-01", data_fim="2030-01-01"))
    assert (resolved, field) == (date(2025, 4, 1), "data_inicio")

    resolved, field = contracting_date(_contract("c3", data_publicacao="2025-05-01"))
    assert (resolved, field) == (date(2025, 5, 1), "data_publicacao")

    # data_fim alone never qualifies: it is an execution-end estimate.
    assert contracting_date(_contract("c4", data_fim="2027-01-01")) == (None, "")


def test_contract_inside_window_qualifies_and_outside_does_not():
    inside, reasons = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c1", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert inside is not None and inside.qualifying_contract_id == "c1"
    assert inside.qualified_until == "2028-05-10"

    outside, reasons = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c1", data_assinatura="2020-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert outside is None
    assert REASON_NO_QUALIFYING_CONTRACT in reasons


def test_company_stays_qualified_while_any_contract_is_in_window():
    """Several contracts: the most recent contracting act carries the fact."""
    q, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[
            _contract("old", data_assinatura="2019-01-01"),
            _contract("recent", data_assinatura="2025-06-01"),
            _contract("middle", data_assinatura="2024-02-02"),
        ],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert q.qualifying_contract_id == "recent"
    # Only the in-window contracts are counted.
    assert q.qualifying_contract_count == 2


def test_boundary_expires_at_the_start_of_qualified_until_day():
    floor = window_floor(NOW)
    assert floor == date(2023, 8, 28)
    on_floor, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura=floor.isoformat())],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert on_floor is None
    day_before, reasons = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura=date(2023, 8, 27).isoformat())],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert day_before is None and REASON_NO_QUALIFYING_CONTRACT in reasons


def test_a_contracting_body_never_qualifies():
    q, reasons = qualify_root(
        lead_cnpj14="99888777000166",
        contracts=[_contract("c", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="BUYER",
    )
    assert q is None and REASON_ROLE_INVALID in reasons


def test_future_dated_contract_is_refused():
    q, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura="2030-01-01")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert q is None


def test_invalid_revoked_and_expired_v2_qualifications_fail_closed():
    valid, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert valid is not None
    assert validate_root_qualification(valid, as_of=NOW.date()) == []
    assert "commercial_qualification_evidence_drift" in validate_root_qualification(
        replace(valid, qualification_evidence_hash="0" * 64), as_of=NOW.date()
    )
    assert "commercial_qualification_revoked" in validate_root_qualification(
        replace(valid, deactivated=True, deactivation_reason="manual_revocation"), as_of=NOW.date()
    )
    expired = replace(
        valid,
        qualifying_contract_date="2023-08-28",
        qualified_until="2026-08-28",
        qualification_evidence_hash="",
    )
    expired = replace(expired, qualification_evidence_hash=evidence_hash(expired))
    assert "commercial_qualification_expired" in validate_root_qualification(expired, as_of=NOW.date())


def test_population_authority_carries_evidence_not_a_ttl():
    q, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    payload = build_population_authority(
        roots=[q],
        basis_source_run_id="run-abc",
        basis_snapshot_hash="snap-abc",
        basis_membership_hash="a" * 64,
        basis_publication_semantic_hash="s" * 64,
        producer_identity="p" * 64,
        now=NOW,
    )
    assert payload["schema"] == CONTRACT_VERSION
    assert payload["policy_version"] == POLICY_VERSION
    assert payload["qualification_window_years"] == QUALIFICATION_WINDOW_YEARS
    assert payload["state"] == STATE_QUALIFIED
    assert payload["qualification_evidence_hash"] == corpus_hash([q])
    # No age band, no TTL, no validity window keyed to the crawler.
    for forbidden in ("valid_until", "age_hours", "windows_hours", "current_max_hours"):
        assert forbidden not in payload

    revoked = build_population_authority(
        roots=[q],
        basis_source_run_id="run-abc",
        basis_snapshot_hash="snap-abc",
        basis_membership_hash="a" * 64,
        basis_publication_semantic_hash="s" * 64,
        producer_identity="p" * 64,
        now=NOW,
        explicit_revoked=True,
    )
    assert revoked["state"] == STATE_REVOKED
    assert "EXPLICIT_REVOCATION" in revoked["reason_codes"]


def test_corpus_hash_is_order_independent_and_change_sensitive():
    a, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("a", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    b, _ = qualify_root(
        lead_cnpj14="99888777000166",
        contracts=[_contract("b", data_assinatura="2024-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    assert corpus_hash([a, b]) == corpus_hash([b, a])
    assert corpus_hash([a, b]) != corpus_hash([a])


@pytest.mark.parametrize(
    "mutation",
    [
        {"qualifying_contract_id": "forged"},
        {"qualifying_contract_date": "2024-01-01"},
        {"qualifying_date_field": "data_inicio"},
        {"cnpj_root8": "00000000"},
        {"qualification_evidence_reference": "forged"},
        {"qualified_until": "2099-01-01"},
    ],
)
def test_any_material_mutation_changes_the_evidence_hash(mutation):
    from scripts.confenge_activation.commercial_authority_v2 import RootQualification

    q, _ = qualify_root(
        lead_cnpj14="11222333000144",
        contracts=[_contract("c", data_assinatura="2025-05-10")],
        now=NOW,
        target_fit_class="TARGET_CONFIRMED",
        party_role="SUPPLIER",
    )
    tampered = RootQualification(**{**q.__dict__, **mutation})
    assert evidence_hash(tampered) != q.qualification_evidence_hash
