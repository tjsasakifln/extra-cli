"""Organic Opportunity Engine — real entry path tests (no mocked score logic)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "scripts" / "organic" / "fixtures"

from scripts.organic.engine import build_opportunities, load_pseo_snapshot, run_engine
from scripts.organic.gates import indexability_quality_gate
from scripts.organic.score import CONTENT_VALUE_WEIGHTS, compute_content_value_score


def test_content_value_weights_sum_100():
    assert sum(CONTENT_VALUE_WEIGHTS.values()) == 100


def test_bofu_scores_higher_than_tofu_all_else_equal():
    bofu = compute_content_value_score(
        intent_stage="bofu",
        service_fit=0.9,
        data_moat=0.5,
        demand_evidence=0.5,
        topical_authority=0.5,
        freshness_trigger=0.5,
        competitive_opportunity=0.5,
    )
    tofu = compute_content_value_score(
        intent_stage="tofu",
        service_fit=0.9,
        data_moat=0.5,
        demand_evidence=0.5,
        topical_authority=0.5,
        freshness_trigger=0.5,
        competitive_opportunity=0.5,
    )
    assert bofu["score"] > tofu["score"]
    assert bofu["breakdown"]["commercial_intent"] > tofu["breakdown"]["commercial_intent"]


def test_penalties_reduce_score():
    clean = compute_content_value_score(
        intent_stage="bofu",
        service_fit=1.0,
        data_moat=1.0,
        demand_evidence=1.0,
        topical_authority=1.0,
        freshness_trigger=1.0,
        competitive_opportunity=1.0,
    )
    dirty = compute_content_value_score(
        intent_stage="bofu",
        service_fit=1.0,
        data_moat=1.0,
        demand_evidence=1.0,
        topical_authority=1.0,
        freshness_trigger=1.0,
        competitive_opportunity=1.0,
        penalties=["thin_content", "cannibalization"],
    )
    assert dirty["score"] < clean["score"]
    assert dirty["penalty_total"] >= 20


def test_indexability_gate_blocks_thin_without_provenance():
    gate = indexability_quality_gate(
        distinct_intent=True,
        own_information=False,
        sample_size=2,
        semantic_differentiation=0.1,
        independent_utility=False,
        data_confidence=0.2,
        non_redundant=True,
        no_cannibalization=True,
        has_context_interpretation=False,
        identifiable_update=False,
        useful_internal_links=False,
        contextual_cta=False,
        has_provenance=False,
        content_value_score=99,  # score cannot compensate
    )
    assert gate["indexable"] is False
    assert "no_own_information" in gate["fails"]
    assert "missing_provenance" in gate["fails"]
    assert gate["decision"] in {"noindex", "do_not_create", "merge_or_canonical"}


def test_indexability_gate_passes_rich_data_page():
    gate = indexability_quality_gate(
        distinct_intent=True,
        own_information=True,
        sample_size=24,
        semantic_differentiation=0.7,
        independent_utility=True,
        data_confidence=0.8,
        non_redundant=True,
        no_cannibalization=True,
        has_context_interpretation=True,
        identifiable_update=True,
        useful_internal_links=True,
        contextual_cta=True,
        has_provenance=True,
        content_value_score=70,
    )
    assert gate["indexable"] is True
    assert gate["decision"] == "indexable_candidate"


def test_engine_from_fixtures_produces_ranked_opportunities():
    snap = load_pseo_snapshot(FIXTURES)
    assert len(snap["markets"]) == 2
    doc = build_opportunities(
        snap,
        gsc_queries=[
            {
                "query": "desonerado e não desonerado",
                "impressions": 10,
                "clicks": 0,
                "position": 9.2,
            },
            {
                "query": "aditivos obra pública",
                "impressions": 5,
                "clicks": 0,
                "position": 66,
            },
        ],
        gsc_pages=[
            {
                "page": "https://confenge.com.br/conteudos/sinapi-desonerado-nao-desonerado/",
                "impressions": 88,
                "clicks": 0,
                "position": 7.75,
            }
        ],
        as_of="2026-08-01",
    )
    assert doc["schema_version"] == "seo-opportunities-v1"
    assert doc["counts"]["total"] >= 5
    assert doc["counts"]["bofu"] >= 1
    assert doc["counts"]["data_driven"] >= 1

    opps = doc["opportunities"]
    assert opps == sorted(opps, key=lambda x: (-x["score"], x["id"]))

    required = {
        "id",
        "topic",
        "cluster",
        "intent",
        "persona",
        "jtbd",
        "commercial_fit",
        "service_fit",
        "demand_signal",
        "search_console_evidence",
        "datalake_evidence",
        "unique_data_available",
        "action",
        "score",
        "rationale",
        "suggested_cta",
        "suggested_internal_links",
        "confidence",
        "publishability",
    }
    for o in opps:
        missing = required - set(o)
        assert not missing, f"{o['id']} missing {missing}"
        assert isinstance(o["score"], int)
        assert 0 <= o["score"] <= 100
        assert o["intent"] in {"bofu", "mofu", "tofu"}
        assert o["action"] in {
            "create",
            "improve",
            "merge",
            "noindex",
            "keep",
            "do_not_create",
        }

    # Thin market must not be indexable candidate
    thin = next(o for o in opps if "thin-demo" in o["id"] or o["id"].endswith("thin-demo-xx"))
    assert thin["unique_data_available"] is False or thin["publishability"] != "indexable_candidate"
    assert thin["action"] in {"noindex", "do_not_create"} or not thin["indexability_gate"]["indexable"]

    # Rich market should have data moat
    rich = next(o for o in opps if "edificacoes-publicas-sc" in o["id"])
    assert rich["unique_data_available"] is True
    assert rich["datalake_evidence"].get("record_count", 0) >= 8
    assert rich["datalake_evidence"].get("methodology")


def test_run_engine_writes_file(tmp_path: Path):
    out = tmp_path / "SEO_OPPORTUNITIES.json"
    doc = run_engine(pseo_dir=FIXTURES, out_path=out, as_of="2026-08-01")
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["counts"]["total"] == doc["counts"]["total"]
    assert "demand_map" in loaded
    assert loaded["demand_map"]["model"].startswith("persona")


def test_cli_main_fixture(tmp_path: Path):
    from scripts.organic.__main__ import main

    out = tmp_path / "out.json"
    code = main(["--pseo-dir", str(FIXTURES), "--out", str(out), "--as-of", "2026-08-01"])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["counts"]["total"] > 0
    assert any(o["intent"] == "bofu" for o in data["opportunities"])
    assert any(o.get("unique_data_available") for o in data["opportunities"])


def test_normative_editorial_problem_service_is_not_unique_data():
    """Normative/editorial evidence must NOT claim content moat / N contracts."""
    from scripts.organic.engine import (
        _is_contract_aggregate_evidence,
        opportunities_from_problem_service,
    )

    assert not _is_contract_aggregate_evidence(
        evidence_kind="normative_editorial",
        dataset="pncp_supplier_contracts,site-confenge-guides",
        sources=["pncp_supplier_contracts", "site-confenge-guides"],
    )
    # Pure site guides
    assert not _is_contract_aggregate_evidence(
        evidence_kind="normative_editorial",
        dataset="site-confenge-guides",
        sources=["site-confenge-guides"],
    )
    # Real market aggregate still true
    assert _is_contract_aggregate_evidence(
        evidence_kind="market_benchmark",
        dataset="pncp_supplier_contracts",
        sources=["pncp_supplier_contracts"],
    )

    rows = opportunities_from_problem_service(
        [
            {
                "id": "prob-fake-normative",
                "slug": "fake-normative",
                "problem_label": "Padrão editorial",
                "confenge_service_slug": "reequilibrio-obras-publicas",
                "theme": "reequilibrio",
                "evidence_count": 48,
                "evidence_kind": "normative_editorial",
                "observed_pattern": "Padrão qualitativo.",
                "sources": ["pncp_supplier_contracts", "site-confenge-guides"],
                "technical_guide_paths": ["/conteudos/x/"],
                "limitations": ["Não é contagem de contratos."],
            }
        ],
        as_of="2026-08-01",
    )
    assert len(rows) == 1
    opp = rows[0]
    assert opp["unique_data_available"] is False
    assert (opp.get("datalake_evidence") or {}).get("public_label") == "editorial_pattern"
    assert (opp.get("datalake_evidence") or {}).get("is_contract_aggregate") is False
    # data moat must be low for editorial (not 0.55+ from fake contract signal)
    assert float(opp.get("data_moat_score") or 0) < 0.4


def test_radar_methodology_is_portuguese_client_facing():
    from scripts.organic.engine import opportunities_from_radar

    rows = opportunities_from_radar(
        [
            {
                "id": "radar-edificacoes-publicas-pr",
                "historical_count": 10,
                "items": [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}],
                "freshness": {"age_hours": 12},
            }
        ],
        as_of="2026-08-01",
    )
    meth = (rows[0].get("datalake_evidence") or {}).get("methodology") or ""
    assert "Open-status" not in meth
    assert "never treat" not in meth.lower()
    assert "Filtro de status aberto" in meth or "status aberto" in meth.lower()
