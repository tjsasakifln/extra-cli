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
    """Production shape: multi-contract mature books must NOT primary reajuste.

    Real PNCP vigência often has start_date + age_days>=365 without reajuste
    proof. FASE7: operational need (gestão) > reajuste verification window.
    """
    bag = {
        "contracts": [
            {
                "id": f"c{i}",
                "object": f"execução de obra de pavimentação trecho {i}",
                "has_addendum": False,
                "has_reajuste": False,
                "start_date": "2023-01-01",
                "age_days": 800 + i,
            }
            for i in range(4)
        ],
        "facts": [],
        "signals": {},
    }
    r = _sel(bag, structure={"structure_class": "mixed", "lean_signals": []}, why={"trigger": ""})
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"
    assert r["primary_service"]["service_id"] == "gestao_monitoramento_contratual"
    # Reajuste may appear as a lower-ranked candidate, never primary here.
    cands = r.get("service_candidates") or []
    reaj = next((c for c in cands if c["service_id"] == "estruturacao_pleito_reajuste"), None)
    gest = next((c for c in cands if c["service_id"] == "gestao_monitoramento_contratual"), None)
    assert gest is not None and reaj is not None
    assert float(gest["score"]) > float(reaj["score"])


def test_mature_single_contract_can_be_reajuste_verification() -> None:
    """Single mature contract without stronger signals → reajuste verification OK."""
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "pavimentação asfáltica etapa única",
                "start_date": "2023-06-01",
                "age_days": 800,
                "has_reajuste": False,
                "has_addendum": False,
            }
        ],
        "facts": [{"text": "maduro", "epistemic_class": "confirmed"}],
    }
    r = _sel(bag, why={"trigger": "mature_no_reajuste"})
    assert r["primary_service"]["service_id"] == "estruturacao_pleito_reajuste"


def test_robust_multi_beats_mature_reajuste() -> None:
    """Robust multi-contract without BDI/planilha signals → gestão, not invented specialty."""
    bag = {
        "contracts": [
            {
                "id": f"c{i}",
                "object": f"obra de infraestrutura rodoviária trecho {i} com extensão relevante",
                "start_date": "2022-01-01",
                "age_days": 1200,
                "has_reajuste": False,
            }
            for i in range(6)
        ],
        "facts": [],
        "signals": {},
    }
    r = _sel(bag, structure={"structure_class": "robust", "lean_signals": []}, why={"trigger": ""})
    assert r["primary_service"]["service_id"] == "gestao_monitoramento_contratual"
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"
    assert r["primary_service"]["service_id"] != "auditoria_orcamento_bdi"
    # specialty BDI only when budget signals present
    signals = r["primary_service"].get("supporting_signal_ids") or []
    assert "multi_contract" in signals or "structure_robust" in signals


def test_robust_multi_no_bdi_never_invents_planilha() -> None:
    bag = {
        "contracts": [
            {
                "id": f"c{i}",
                "object": f"construção de edifício escolar bloco {i} com fundações",
                "start_date": "2021-06-01",
                "age_days": 1500,
                "has_reajuste": False,
            }
            for i in range(5)
        ],
        "facts": [],
        "signals": {},
    }
    r = _sel(bag, structure={"structure_class": "robust", "lean_signals": []}, why={"trigger": ""})
    assert r["primary_service"]["service_id"] in {
        "gestao_monitoramento_contratual",
        "diagnostico_contratual_b2g",
    }
    ids = {c["service_id"] for c in r.get("service_candidates") or []}
    # May appear only if _has_budget_bdi; structure proxy alone must not inject it as winner
    if "auditoria_orcamento_bdi" in ids:
        bdi = next(c for c in r["service_candidates"] if c["service_id"] == "auditoria_orcamento_bdi")
        assert "budget_bdi" in (bdi.get("supporting_signal_ids") or [])


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
