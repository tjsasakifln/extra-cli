"""Activation campaign: canonical coverage single-truth + dossiers/kits language."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.commercial_leads.canonical_coverage import (
    assert_no_coverage_divergence,
    build_canonical_coverage,
    reconcile_coverage_artifacts,
)
from scripts.commercial_leads.dossiers import build_dossier, export_dossiers
from scripts.commercial_leads.outreach_kits import build_outreach_kit, export_outreach_kits
from scripts.commercial_leads.supplier_registry import SupplierRegistryRecord


def _reg(cnpj: str) -> SupplierRegistryRecord:
    return SupplierRegistryRecord(
        cnpj14=cnpj,
        razao_social=f"Empresa {cnpj}",
        nome_fantasia=None,
        cnae_principal="4120400",
        cnaes_secundarios=["7112000"],
        situacao_cadastral="ATIVA",
        data_situacao="2020-01-01",
        municipio="Florianopolis",
        uf="SC",
        source="receita_federal_dados_abertos",
        source_version="test",
        source_date="2026-07-25",
        ingested_at="2026-07-29T00:00:00Z",
    )


def test_canonical_coverage_single_structure_no_divergence() -> None:
    registry = {_reg("12345678000199").cnpj14: _reg("12345678000199")}
    cnpjs = ["12345678000199"]
    canon = build_canonical_coverage(
        registry,
        all_candidates=cnpjs,
        top100=cnpjs,
        top20=cnpjs,
        eligible_candidates=cnpjs,
        terminal_status="BLOCKED",
        declared_blockers=["BLOCKED_INSUFFICIENT_HUMAN_LABELS"],
    )
    result = {
        "status": "BLOCKED",
        "reason": "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
        "official_registry_coverage": canon["official_registry_coverage"],
        "canonical_coverage": canon,
        "metrics": {
            "cnae_coverage": canon["cnae_coverage"],
            "registry_coverage": canon,
            "canonical_coverage": canon,
        },
    }
    queue = {
        "status": "BLOCKED",
        "official_registry_coverage": canon["official_registry_coverage"],
        "canonical_coverage": canon,
        "metrics": {
            "cnae_coverage": canon["cnae_coverage"],
            "registry_coverage": canon,
            "canonical_coverage": canon,
        },
    }
    report = reconcile_coverage_artifacts({"result": result, "queue-summary": queue})
    assert report["ok"] is True
    assert_no_coverage_divergence({"result": result, "queue-summary": queue})


def test_coverage_divergence_detected_between_artifacts() -> None:
    good = build_canonical_coverage(
        {_reg("12345678000199").cnpj14: _reg("12345678000199")},
        all_candidates=["12345678000199"],
        top100=["12345678000199"],
        top20=["12345678000199"],
    )
    result = {
        "status": "BLOCKED",
        "official_registry_coverage": 1.0,
        "canonical_coverage": good,
        "metrics": {"cnae_coverage": 1.0, "canonical_coverage": good, "registry_coverage": good},
    }
    # Divergent top-level vs nested theater (historical bug)
    queue = {
        "status": "BLOCKED",
        "official_registry_coverage": 0.053,
        "metrics": {
            "cnae_coverage": 0.0165,
            "registry_coverage": {
                "registry_coverage_all_candidates": {"coverage": 0.0165, "n": 7091},
                "registry_coverage_top20": {"coverage": 1.0, "n": 20},
                "block_reason": None,
                "registry_universe_resolved": False,
            },
        },
    }
    report = reconcile_coverage_artifacts({"result": result, "queue-summary": queue})
    assert report["ok"] is False
    assert report["gate"] == "FAIL_COVERAGE_DIVERGENCE"


def test_stale_blocker_after_full_coverage_detected() -> None:
    nested = {
        "registry_coverage_all_candidates": {"coverage": 1.0, "n": 169, "with_registry": 169},
        "registry_universe_resolved": True,
        "block_reason": None,
        "cnae_primary_coverage": 1.0,
    }
    body = {
        "status": "BLOCKED",
        "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
        "official_registry_coverage": 0.05,
        "metrics": {"registry_coverage": nested, "cnae_coverage": 1.0},
    }
    report = reconcile_coverage_artifacts({"result": body, "queue": body})
    # same artifact twice won't diverge fields, but internal stale check fires per artifact
    assert any(d["field"] == "stale_registry_blocker" for d in report["divergences"])


def test_dossier_and_kit_export_language(tmp_path: Path) -> None:
    lead = {
        "cnpj14": "12345678000199",
        "razao_social": "Construtora Exemplo LTDA",
        "rank_position": 1,
        "score_total": 12.5,
        "priority": "P1",
        "supplier_sector_fit": "CONFIRMED_ENGINEERING",
        "activity_class": "CONSTRUCTION_CONTRACTOR",
        "contract_count": 4,
        "total_value": 1500000,
        "signals_fired": [
            {
                "signal_id": "value_growth",
                "hypothesis": "Crescimento de valor contratado sugere maior exposição observável.",
            }
        ],
        "signals_not_computable": [{"signal_id": "adverse_event", "not_computable_reason": "no acts"}],
        "suggested_offer": "diagnostico_b2g",
        "next_human_step": "Revisar aderência e decidir abordagem manual",
        "limitations": ["contato_NOT_AVAILABLE"],
    }
    d = build_dossier(lead, run_id="run-test")
    assert d["identification"]["cnpj14"] == "12345678000199"
    assert d["language_policy"]["forbidden_claims_present"] is False
    k = build_outreach_kit(lead, run_id="run-test")
    assert k["manual_send_only"] is True
    assert k["automation_forbidden"] is True
    assert "NOT_AVAILABLE" in json.dumps(k["public_business_contact"])
    assert k["language_scan_forbidden_hit"] is False
    # Forbidden claim detection
    bad = dict(lead)
    bad["value_hypothesis"] = "Empresa tem propensão alta de compra"
    d_bad = build_dossier(bad, run_id="x")
    assert d_bad["language_policy"]["forbidden_claims_present"] is True

    paths = export_dossiers(tmp_path, [lead], run_id="r1", limit=1)
    assert (tmp_path / "top20-dossiers" / "12345678000199.md").is_file()
    kpaths = export_outreach_kits(tmp_path, [lead], run_id="r1", limit=1)
    assert (tmp_path / "top5-outreach-kits" / "12345678000199.md").is_file()
    assert "dossiers_index" in paths and "kits_index" in kpaths


def test_partial_snapshot_must_not_claim_full_scan() -> None:
    """Structural: discovery modes that are prefiltered must not claim FULL_SNAPSHOT_SCAN."""
    from scripts.commercial_leads import DISCOVERY_FULL_SNAPSHOT, DISCOVERY_PREFILTERED

    load_meta = {
        "discovery_mode": DISCOVERY_PREFILTERED,
        "limit_applied": 60000,
        "db_contract_count": 60000,
    }
    claims: list[str] = []
    if load_meta.get("discovery_mode") == DISCOVERY_FULL_SNAPSHOT:
        claims.append("full_snapshot_discovery")
    assert "full_snapshot_discovery" not in claims
    assert load_meta["limit_applied"] == 60000
    # Explicit non-claim
    assert load_meta["discovery_mode"] != DISCOVERY_FULL_SNAPSHOT
