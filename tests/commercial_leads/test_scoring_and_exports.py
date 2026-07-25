"""Scoring, ranking, exports, language."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from scripts.commercial_leads.baseline import compare_to_baselines
from scripts.commercial_leads.exports import export_all, reconcile_exports
from scripts.commercial_leads.profile import load_profile
from scripts.commercial_leads.scoring import rank_leads, score_supplier
from scripts.commercial_leads.signals import ContractRow, compute_signals_for_supplier

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/commercial_profiles/confenge.yaml"
AS_OF = date(2026, 7, 25)


def _contracts_for_score():
    prior = [
        ContractRow(
            contrato_id=f"P{i}",
            orgao_cnpj="11111111000191",
            orgao_nome="ORGAO A",
            fornecedor_cnpj="11222333000181",
            fornecedor_nome="EMPRESA",
            objeto_contrato="obra de pavimentacao",
            valor_total=80_000,
            data_inicio=None,
            data_fim=None,
            data_publicacao=AS_OF - timedelta(days=400 + i),
            uf="SC",
            source="pncp",
            source_id=f"P{i}",
        )
        for i in range(4)
    ]
    recent = [
        ContractRow(
            contrato_id=f"R{i}",
            orgao_cnpj="22222222000191",
            orgao_nome="ORGAO B",
            fornecedor_cnpj="11222333000181",
            fornecedor_nome="EMPRESA",
            objeto_contrato="construcao de edificio",
            valor_total=900_000,
            data_inicio=AS_OF - timedelta(days=60),
            data_fim=AS_OF + timedelta(days=40),
            data_publicacao=AS_OF - timedelta(days=20 + i),
            uf="PR",
            source="pncp",
            source_id=f"R{i}",
        )
        for i in range(3)
    ]
    return prior + recent


def test_score_decomposable_and_rank():
    profile = load_profile(PROFILE)
    sigs = compute_signals_for_supplier(_contracts_for_score(), profile, as_of=AS_OF)
    lead = score_supplier(
        cnpj14="11222333000181",
        razao_social="EMPRESA",
        signal_results=sigs,
        profile=profile,
        total_value=3_000_000,
        contract_count=7,
        last_publication=AS_OF.isoformat(),
    )
    assert lead.score_total == sum(lead.decomposition.values())
    assert lead.signals_fired
    assert "propensão" not in json.dumps(lead.as_dict(), ensure_ascii=False).lower()
    ranked = rank_leads([lead], profile)
    assert ranked


def test_exports_reconcile(tmp_path):
    profile = load_profile(PROFILE)
    sigs = compute_signals_for_supplier(_contracts_for_score(), profile, as_of=AS_OF)
    lead = score_supplier(
        cnpj14="11222333000181",
        razao_social="EMPRESA X",
        signal_results=sigs,
        profile=profile,
        total_value=1_000_000,
        contract_count=5,
    )
    d = lead.as_dict()
    d["rank_position"] = 1
    d["commercial_state"] = "NEW"
    run = {
        "run_id": "test-run",
        "status": "PASS",
        "profile_id": "confenge",
        "profile_version": "1.0.0",
        "snapshot_hash": "abc",
        "eligible_companies": 1,
        "queue_limit": 20,
        "leads": [d],
        "signal_catalog": profile.catalog,
        "baseline_comparison": compare_to_baselines(
            [lead],
            [
                {
                    "cnpj14": "11222333000181",
                    "razao_social": "EMPRESA X",
                    "total_value": 1_000_000,
                    "contract_count": 5,
                    "last_publication": AS_OF.isoformat(),
                }
            ],
        ),
        "ledger": [
            {
                "cnpj14": "11222333000181",
                "event_type": "EXPORT",
                "author": "system",
                "payload": {},
                "created_at": "2026-07-25T00:00:00Z",
            }
        ],
        "non_claims": ["CONFENGE_COMMERCIAL_READY"],
    }
    paths = export_all(tmp_path, run)
    assert (tmp_path / "leads.csv").is_file()
    assert (tmp_path / "executive-summary.md").is_file()
    assert (tmp_path / "operational-report.html").is_file()
    recon = reconcile_exports(tmp_path, run)
    assert recon["ok"] is True
    assert "leads.json" in paths


def test_profile_rejects_forbidden_language(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "profile_id: x\nversion: '1'\nweights: {}\nthresholds: {}\nqueue: {limit: 20}\n"
        "services: []\nsegments: []\n"
        "note: propensão de compra\n",
        encoding="utf-8",
    )
    cat = tmp_path / "signal_catalog.yaml"
    # minimal 12 signals
    sigs = "\n".join(
        f"  - id: s{i}\n    hypothesis: h\n    formula: f\n    required_fields: [x]\n"
        f"    window_days: 1\n    threshold: t\n    direction: up\n    confidence: low\n"
        f"    offer: o\n    not_computable_when: n\n"
        for i in range(12)
    )
    cat.write_text(f"catalog_version: '1'\nsignals:\n{sigs}", encoding="utf-8")
    import pytest
    from scripts.commercial_leads.profile import load_profile

    with pytest.raises(ValueError, match="forbidden"):
        load_profile(bad, cat)
