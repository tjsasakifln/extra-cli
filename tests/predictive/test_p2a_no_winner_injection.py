"""P2A must not inject true winner into pre-result candidate set."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.predictive.dataset import build_competitive_winner_dataset


def test_cold_start_winner_not_injected_and_outcome_dropped():
    """New supplier who never won before must not appear via force-include."""
    base = datetime(2021, 1, 1, tzinfo=UTC)
    contracts = []
    # Build history with suppliers 0-2 only
    for i in range(30):
        contracts.append(
            {
                "orgao_cnpj": "12345678000199",
                "objeto_contrato": "Obra de reforma predial municipal",
                "data_assinatura": base + timedelta(days=20 * i),
                "valor_total": 200000,
                "fornecedor_cnpj": f"{(i % 3):014d}",
                "contrato_id": f"h{i}",
            }
        )
    # Cold-start winner never seen before
    contracts.append(
        {
            "orgao_cnpj": "12345678000199",
            "objeto_contrato": "Obra de reforma predial municipal",
            "data_assinatura": base + timedelta(days=20 * 30),
            "valor_total": 200000,
            "fornecedor_cnpj": "99999999999999",
            "contrato_id": "cold",
        }
    )
    ds = build_competitive_winner_dataset(contracts, min_history_days=60)
    cold_examples = [e for e in ds.examples if e["procurement_id"] == "cold"]
    assert cold_examples == [], (
        "Cold-start winner outcome must be dropped when winner not in pre-result set"
    )
    # No example may list the cold winner as supplier if they only appear as cold-start
    for e in ds.examples:
        if e["supplier_id"] == "99999999999999":
            # Only allowed if they had prior history (they don't)
            assert False, "cold-start supplier must never appear in features via injection"


def test_known_winner_in_history_still_labeled():
    base = datetime(2021, 1, 1, tzinfo=UTC)
    contracts = []
    for i in range(40):
        contracts.append(
            {
                "orgao_cnpj": "12345678000199",
                "objeto_contrato": "Obra de reforma predial",
                "data_assinatura": base + timedelta(days=15 * i),
                "valor_total": 100000,
                "fornecedor_cnpj": f"{(i % 4):014d}",
                "contrato_id": f"w{i}",
            }
        )
    ds = build_competitive_winner_dataset(contracts, min_history_days=60)
    assert ds.examples
    assert any(e["label_value"] == 1 for e in ds.examples)
    assert any(e["label_value"] == 0 for e in ds.examples)
    # days_since for known suppliers should not be 0 solely from as_of default
    for e in ds.examples:
        dsince = e["features_json"].get("days_since_supplier_win")
        assert dsince is not None
        # never-seen would be 9999; known should be finite non-negative
        assert dsince >= 0
