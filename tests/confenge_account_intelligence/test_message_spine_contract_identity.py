"""The message spine must cite contracts by their official identity.

`normalize_record` resolves the official PNCP identity (`contrato_id`,
`numero_controle_pncp`, `contract_id`) into the bag's `id` field. Anything
downstream that re-derives identity from the official field *names* misses on a
normalized contract and silently falls back to a positional surrogate, so the
evidence id no longer points at a real public contract.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.confenge_account_intelligence.message_spine import extract_contract_hook
from scripts.confenge_account_intelligence.normalize import normalize_record

TODAY = date.today()
OBJECT = (
    "Execução de obra de pavimentação asfáltica em CBUQ, drenagem pluvial e "
    "sinalização viária nas vias urbanas do município"
)


def _bag(contract: dict[str, object]) -> dict[str, object]:
    return normalize_record(
        {
            "cnpj14": "02810894000100",
            "razao_social": "ACME CONSTRUTORA LTDA",
            "contracts": [contract],
        },
        as_of=TODAY.isoformat(),
    )


def _contract(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "object": OBJECT,
        "orgao": "DNIT",
        "uf": "SC",
        "value_brl": 4_800_000,
        "start_date": (TODAY - timedelta(days=900)).isoformat(),
        "end_date": (TODAY - timedelta(days=200)).isoformat(),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("field", "official_id"),
    [
        ("contrato_id", "CT-2024-000123"),
        ("numero_controle_pncp", "07854402000186-1-000123/2024"),
        ("contract_id", "CT-ALT-77"),
    ],
)
def test_evidence_id_carries_the_official_contract_identity(field: str, official_id: str) -> None:
    bag = _bag(_contract(**{field: official_id}))

    assert bag["contracts"][0]["id"] == official_id

    _, evidence_ids = extract_contract_hook(bag)

    assert evidence_ids == [f"cf-contract-{official_id}"]


def test_evidence_id_never_degrades_an_identified_contract_to_a_positional_surrogate() -> None:
    """Regression: the surrogate is for contracts with no identity, not for all."""
    bag = _bag(_contract(contrato_id="CT-2024-000123"))

    _, evidence_ids = extract_contract_hook(bag)

    assert not any(eid.startswith("cf-contract-contract-") for eid in evidence_ids), (
        f"official identity was replaced by a positional surrogate: {evidence_ids}"
    )


def test_a_contract_with_no_official_identity_still_gets_a_stable_surrogate() -> None:
    """No identity is a real case and must not crash or emit an empty id."""
    bag = _bag(_contract())

    _, evidence_ids = extract_contract_hook(bag)

    assert evidence_ids and all(eid.startswith("cf-contract-") for eid in evidence_ids)
    assert not any(eid == "cf-contract-" for eid in evidence_ids)


def _multi_bag(contracts: list[dict[str, object]]) -> dict[str, object]:
    return normalize_record(
        {
            "cnpj14": "02810894000100",
            "razao_social": "ACME CONSTRUTORA LTDA",
            "contracts": contracts,
        },
        as_of=TODAY.isoformat(),
    )


def test_mixed_batch_preserves_identity_only_for_identified_contracts() -> None:
    """A batch mixing identified and unidentified contracts must not cross-contaminate ids."""
    identified = _contract(contrato_id="CT-2024-000123", object=OBJECT + " lote A")
    unidentified = _contract(object=OBJECT + " lote B, sem identidade oficial no cadastro")
    bag = _multi_bag([identified, unidentified])

    ids = [str(c["id"]) for c in bag["contracts"]]
    assert ids[0] == "CT-2024-000123"
    assert ids[1] != "CT-2024-000123"

    # extract_contract_hook only surfaces one evidence id (the strongest contract),
    # but whichever one it picks must not blend the two identities.
    _, evidence_ids = extract_contract_hook(bag)
    assert evidence_ids
    for eid in evidence_ids:
        assert eid in (f"cf-contract-{ids[0]}", f"cf-contract-{ids[1]}")


def test_reordering_contracts_does_not_change_the_identified_contracts_identity() -> None:
    """Identity of an identified contract must be stable regardless of its position."""
    a = _contract(contrato_id="CT-2024-000123", object=OBJECT + " lote A")
    b = _contract(numero_controle_pncp="07854402000186-1-000123/2024", object=OBJECT + " lote B")

    forward = _multi_bag([a, b])
    backward = _multi_bag([b, a])

    forward_ids = {str(c["id"]) for c in forward["contracts"]}
    backward_ids = {str(c["id"]) for c in backward["contracts"]}

    assert forward_ids == backward_ids == {
        "CT-2024-000123",
        "07854402000186-1-000123/2024",
    }
