"""Adversarial tests: Top10 gate requires official RFB cadastro (§8.1)."""

from __future__ import annotations

from pathlib import Path

from scripts.commercial_leads.exports import export_holdout_review
from scripts.commercial_leads.top10_gate import evaluate_top10_gate, official_registry_resolved


def _base_lead(**overrides: object) -> dict:
    lead: dict = {
        "cnpj14": "12345678000199",
        "razao_social": "Construtora Teste LTDA",
        "commercial_state": "NEW",
        "signals_fired": [{"signal_id": "value_growth"}],
        "evidence": [{"contract_id": "c1"}],
        "supplier_sector_fit": "CONFIRMED_ENGINEERING",
        "contract_relevance": "PASS",
        "commercial_signal_fit": "PASS",
        "geography_fit": "PASS",
        "cnae_principal": "4120400",
        "situacao_cadastral": "ATIVA",
        "municipio": "Florianopolis",
        "uf": "SC",
        "registry_source": "receita_federal_dados_abertos",
        "registry_resolution_status": "RESOLVED_OFFICIAL",
        "registry": {
            "cnae_principal": "4120400",
            "situacao_cadastral": "ATIVA",
            "municipio": "Florianopolis",
            "uf": "SC",
            "source": "receita_federal_dados_abertos",
            "source_date": "2026-07-01",
            "razao_social": "Construtora Teste LTDA",
        },
    }
    lead.update(overrides)
    return lead


def _ten_official() -> list[dict]:
    leads = []
    for i in range(10):
        cnpj = f"{i:08d}000199"[:14].ljust(14, "0")
        # valid 14-digit
        cnpj = f"{10000000 + i:08d}0001{i % 10}{i % 10}"
        assert len(cnpj) == 14
        leads.append(
            _base_lead(
                cnpj14=cnpj,
                razao_social=f"Empresa {i}",
            )
        )
    return leads


def test_top10_passes_with_official_registry() -> None:
    gate = evaluate_top10_gate(_ten_official())
    assert gate["ok"] is True
    assert gate["official_registry_failures"] == 0
    assert gate["n"] == 10


def test_top10_fails_when_only_sector_publishable_without_cadastro() -> None:
    """Historical bug: CONFIRMED_ENGINEERING alone must not pass §8.1."""
    leads = []
    for i in range(10):
        cnpj = f"{20000000 + i:08d}0001{i % 10}{i % 10}"
        leads.append(
            _base_lead(
                cnpj14=cnpj,
                cnae_principal=None,
                situacao_cadastral=None,
                municipio=None,
                uf=None,
                registry_source=None,
                registry_resolution_status="PENDING",
                registry={},
            )
        )
    gate = evaluate_top10_gate(leads)
    assert gate["ok"] is False
    assert gate["official_registry_failures"] == 10
    assert "top10_official_registry_unresolved" in gate["issues"]
    assert "top10_cnae_missing" in gate["issues"]


def test_top10_fails_on_fallback_registry_even_with_cnae() -> None:
    """BrasilAPI / MinhaReceita must not count as official RFB resolution."""
    leads = []
    for i in range(10):
        cnpj = f"{30000000 + i:08d}0001{i % 10}{i % 10}"
        leads.append(
            _base_lead(
                cnpj14=cnpj,
                registry_source="minhareceita_fallback",
                registry_resolution_status="RESOLVED_FALLBACK",
                registry={
                    "cnae_principal": "4120400",
                    "situacao_cadastral": "ATIVA",
                    "municipio": "SP",
                    "uf": "SP",
                    "source": "minhareceita_fallback",
                    "source_date": "2026-07-01",
                },
            )
        )
    gate = evaluate_top10_gate(leads)
    assert gate["ok"] is False
    assert gate["official_registry_failures"] == 10
    assert "top10_registry_source_not_official" in gate["issues"]
    assert official_registry_resolved(leads[0]) is False


def test_top10_fails_out_of_scope_sector() -> None:
    leads = _ten_official()
    leads[0]["supplier_sector_fit"] = "OUT_OF_SCOPE"
    gate = evaluate_top10_gate(leads)
    assert gate["ok"] is False
    assert gate["out_of_scope_in_top10"] == 1


def test_vps_style_dossier_missing_cadastro_would_fail_gate() -> None:
    """Mirror VPS package dossiers: CNAE/situacao/registry=NOT_AVAILABLE."""
    leads = []
    for i in range(10):
        cnpj = f"{40000000 + i:08d}0001{i % 10}{i % 10}"
        leads.append(
            {
                "cnpj14": cnpj,
                "razao_social": f"Empresa VPS {i}",
                "supplier_sector_fit": "CONFIRMED_ENGINEERING",
                "signals_fired": [{"signal_id": "win_recurrence"}],
                "evidence": [{"id": "x"}],
                "contract_relevance": "PASS",
                "commercial_signal_fit": "PASS",
                "geography_fit": "PASS",
                "cnae_principal": None,
                "situacao_cadastral": None,
                "registry_source": None,
                "registry": None,
            }
        )
    gate = evaluate_top10_gate(leads)
    assert gate["ok"] is False
    assert gate["all_confirmed_engineering"] is True  # sector alone is insufficient
    assert gate["official_registry_failures"] == 10


def test_holdout_export_writes_near_cut_and_excluded(tmp_path: Path) -> None:
    near = [
        {
            "cnpj14": f"{50000000 + i:08d}000199",
            "razao_social": f"Near {i}",
            "rank_position": 21 + i,
            "supplier_sector_fit": "CONFIRMED_ENGINEERING",
            "score_total": 10.0 - i,
            "holdout_role": "near_cut",
        }
        for i in range(12)
    ]
    excluded = [
        {
            "cnpj14": f"{60000000 + i:08d}000199",
            "razao_social": f"Neg {i}",
            "supplier_sector_fit": "OUT_OF_SCOPE",
            "holdout_role": "excluded_negative",
            "exclusion_reason": "sector:OUT_OF_SCOPE",
        }
        for i in range(12)
    ]
    run = {
        "run_id": "test-run",
        "campaign_id": "TEST",
        "near_cut_sample": near,
        "excluded_negative_sample": excluded,
    }
    paths = export_holdout_review(tmp_path, run)
    assert (tmp_path / "holdout-review.json").is_file()
    assert (tmp_path / "holdout-review.csv").is_file()
    assert (tmp_path / "holdout-review.md").is_file()
    import json

    payload = json.loads((tmp_path / "holdout-review.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["counts"]["near_cut"] >= 10
    assert payload["counts"]["excluded_negative"] >= 10
    assert "holdout-review.json" in paths
