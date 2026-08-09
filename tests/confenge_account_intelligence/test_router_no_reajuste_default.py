"""Router: reajuste never default; stronger signals win; diagnóstico fallback."""

from __future__ import annotations

from scripts.confenge_account_intelligence.catalog import load_catalog
from scripts.confenge_account_intelligence.router import build_service_candidates, select_services


def _sel(bag, structure=None, why=None):
    cat = load_catalog()
    structure = structure or {"structure_class": "unknown", "lean_signals": []}
    why = why or {"trigger": ""}
    return select_services(bag, structure=structure, why=why, catalog=cat)


def test_insufficient_facts_diagnostico_not_reajuste() -> None:
    r = _sel({"contracts": [], "facts": []}, why={"trigger": "insufficient_facts"})
    assert r["primary_service"]["service_id"] == "diagnostico_contratual_b2g"
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"


def test_addendum_beats_mature_no_reajuste() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "obra",
                "start_date": "2023-01-01",
                "age_days": 800,
                "has_addendum": True,
                "addendum_count": 2,
                "has_reajuste": False,
            }
        ],
        "facts": [],
    }
    r = _sel(bag, why={"trigger": "addendum"})
    assert r["primary_service"]["service_id"] == "aditivos_extracontratuais"


def test_glosa_beats_mature_no_reajuste() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "start_date": "2023-01-01",
                "age_days": 800,
                "glosa_signals": True,
                "has_reajuste": False,
            }
        ],
        "facts": [],
    }
    r = _sel(bag, why={"trigger": "glosa_medicao"})
    assert r["primary_service"]["service_id"] == "medicoes_glosas_memoria"


def test_mature_no_reajuste_only_when_no_stronger() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "pavimentação",
                "start_date": "2023-01-01",
                "age_days": 800,
                "has_reajuste": False,
                "has_addendum": False,
            }
        ],
        "facts": [{"text": "maduro", "epistemic_class": "confirmed"}],
    }
    r = _sel(bag, why={"trigger": "mature_no_reajuste"})
    assert r["primary_service"]["service_id"] == "estruturacao_pleito_reajuste"
    cands = r["service_candidates"]
    assert any(c["service_id"] == "estruturacao_pleito_reajuste" for c in cands)


def test_multi_contract_gestao_not_reajuste() -> None:
    bag = {
        "contracts": [
            {"id": f"c{i}", "object": f"contrato {i}", "has_addendum": False} for i in range(4)
        ],
        "facts": [],
        "signals": {},
    }
    r = _sel(bag, structure={"structure_class": "mixed", "lean_signals": []}, why={"trigger": ""})
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"
    assert r["primary_service"]["service_id"] in {
        "gestao_monitoramento_contratual",
        "diagnostico_contratual_b2g",
        "auditoria_orcamento_bdi",
    }


def test_candidates_include_why_fields() -> None:
    cat = load_catalog()
    bag = {
        "contracts": [{"id": "c1", "has_addendum": True, "addendum_count": 1}],
        "facts": [],
    }
    cands = build_service_candidates(
        bag,
        structure={"structure_class": "unknown", "lean_signals": []},
        why={"trigger": "addendum"},
        catalog=cat,
    )
    assert cands
    top = cands[0]
    assert "why_this_service" in top
    assert "why_not_other_services" in top
    assert "evidence_ids" in top
