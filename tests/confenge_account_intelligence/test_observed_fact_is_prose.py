"""observed_fact becomes fact_to_mention verbatim in the outreach feed.

Shipping the raw "objeto: ...; órgão: ...; UF ...; R$ ..." record put a
database row inside a cold email.
"""

from scripts.confenge_account_intelligence.message_spine import extract_contract_hook


def _bag():
    return {
        "contracts": [
            {
                "id": "c-1",
                "objeto": "Obra de pavimentação asfáltica em vias urbanas do município",
                "orgao_nome": "Prefeitura Municipal de Brochier",
                "uf": "RS",
                "valor_total": 1398000,
            }
        ]
    }


def test_observed_fact_is_not_a_label_record():
    fact, evidence_ids = extract_contract_hook(_bag())
    assert fact
    assert evidence_ids == ["cf-contract-c-1"]
    assert "objeto:" not in fact.lower()
    assert "órgão:" not in fact.lower()
    # The agency still appears, as prose rather than as a field.
    assert "Brochier" in fact


def test_observed_fact_keeps_the_contract_subject():
    fact, _ = extract_contract_hook(_bag())
    assert "pavimenta" in fact.lower()
