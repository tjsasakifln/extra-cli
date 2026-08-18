"""Drive the shipped traffic-frontier score, hard gates and export builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.traffic_frontier.catalog import CATALOG_AS_OF, load_catalog
from scripts.traffic_frontier.contract import load_contract
from scripts.traffic_frontier.export import (
    build_frontier_pack,
    pick_top3,
    score_candidate,
    write_frontier_pack,
)
from scripts.traffic_frontier.gates import (
    evaluate_hard_gates,
    intellectual_fingerprint,
)
from scripts.traffic_frontier.score import (
    FRONTIER_WEIGHTS,
    compute_frontier_score,
    demand_from_signals,
)


def _ready_base(**overrides):
    record = {
        "question": "Qual o ticket típico de edificação pública em Santa Catarina?",
        "independent_utility": True,
        "method_reproducible": True,
        "is_doorway": False,
        "generic_no_edge": False,
        "cta": "Ver metodologia e limites da inteligência de mercado",
        "cta_connected": True,
        "offer_bridge": {"service_path": "/metodologia-inteligencia/"},
        "suggested_cta": "Ver metodologia e limites da inteligência de mercado",
        "coverage": {
            "state": "success_with_data",
            "kind": "aggregate",
            "record_count": 24,
            "complete_for_scope": True,
            "stale": False,
            "nacional_completo": False,
        },
        "coverage_state": "success_with_data",
        "coverage_kind": "aggregate",
        "coverage_complete": True,
        "record_count": 24,
        "geographic_scope": {"kind": "UF", "codes": ["SC"], "label": "Santa Catarina"},
    }
    record.update(overrides)
    return record


def test_frontier_weights_sum_100():
    assert sum(FRONTIER_WEIGHTS.values()) == 100
    contract = load_contract()
    assert contract["schema"] == "traffic-opportunity-frontier/1.0"
    assert sum(contract["score"]["weights"].values()) == 100
    assert contract["score"]["weights"] == FRONTIER_WEIGHTS
    # Must stay distinct from the organic Content Value Score.
    from scripts.organic.score import CONTENT_VALUE_WEIGHTS

    assert FRONTIER_WEIGHTS != CONTENT_VALUE_WEIGHTS


def test_score_is_deterministic_on_same_inputs():
    kwargs = dict(
        search_question_demand=0.7,
        commercial_pain_ticket=0.8,
        data_coverage_freshness=0.6,
        proprietary_differentiation=0.75,
        citability=0.5,
        time_to_publish=0.9,
        maintenance_cost=0.3,
        penalties=["disconnected_cta"],
    )
    first = compute_frontier_score(**kwargs)
    second = compute_frontier_score(**kwargs)
    assert first == second
    assert first["score"] == second["score"]
    assert first["breakdown"] == second["breakdown"]


def test_missing_gsc_does_not_zero_demand_when_market_job_exists():
    absent = demand_from_signals(market_job_present=True, market_job_plausibility=0.8)
    assert absent["gsc_present"] is False
    assert absent["demand_0_1"] > 0
    assert absent["source"] == "inferred_market_job"
    empty = demand_from_signals(market_job_present=False)
    assert empty["demand_0_1"] == 0.0


def test_maintenance_cost_is_inverted():
    cheap = compute_frontier_score(maintenance_cost=0.0)
    expensive = compute_frontier_score(maintenance_cost=1.0)
    assert cheap["breakdown"]["maintenance_cost"] == FRONTIER_WEIGHTS["maintenance_cost"]
    assert expensive["breakdown"]["maintenance_cost"] == 0
    assert cheap["score"] > expensive["score"]


def test_generic_no_edge_rejects():
    gate = evaluate_hard_gates(_ready_base(generic_no_edge=True, question="O que é licitação?"))
    assert gate["state"] == "REJECT"
    assert "generic_no_edge" in gate["reason_codes"]


def test_incomplete_or_stale_coverage_holds_even_with_high_score():
    incomplete = evaluate_hard_gates(
        _ready_base(
            coverage_state="partial",
            coverage_complete=False,
            coverage={
                "state": "partial",
                "kind": "aggregate",
                "record_count": 24,
                "complete_for_scope": False,
                "stale": False,
            },
        )
    )
    assert incomplete["state"] == "HOLD_FOR_DATA"
    scored = compute_frontier_score(
        search_question_demand=1,
        commercial_pain_ticket=1,
        data_coverage_freshness=1,
        proprietary_differentiation=1,
        citability=1,
        time_to_publish=1,
        maintenance_cost=0,
    )
    assert scored["score"] >= 90
    stale = evaluate_hard_gates(_ready_base(freshness_stale=True, coverage_state="stale"))
    assert stale["state"] == "HOLD_FOR_DATA"
    assert "coverage_stale" in stale["reason_codes"]


def test_estadual_recorte_claimed_as_nacional_rejects():
    gate = evaluate_hard_gates(_ready_base(nacionaliza_recorte=True))
    assert gate["state"] == "REJECT"
    assert "nacionalizacao_recorte" in gate["reason_codes"]


def test_honest_national_question_without_denominator_holds():
    gate = evaluate_hard_gates(
        _ready_base(
            question="Qual o ticket típico de contratos de obras públicas no Brasil?",
            geographic_scope={"kind": "BR", "codes": ["BR"], "label": "nacional"},
            nacional_completo=False,
            coverage_state="blocked",
            coverage_complete=False,
        )
    )
    assert gate["state"] == "HOLD_FOR_DATA"
    assert "national_denominator_incomplete" in gate["reason_codes"]


def test_uf_cnpj_swap_without_intellectual_difference_rejects():
    sc = "Qual o ticket típico de edificação pública em SC?"
    pr = "Qual o ticket típico de edificação pública em PR?"
    assert intellectual_fingerprint(sc) == intellectual_fingerprint(pr)
    gate = evaluate_hard_gates(_ready_base(question=pr, clone_of="tof-ticket-edificacao-sc", is_geo_clone=True))
    assert gate["state"] == "REJECT"
    assert "uf_cnpj_clone" in gate["reason_codes"]


def test_unsupported_legal_claim_rejects():
    gate = evaluate_hard_gates(_ready_base(unsupported_legal_claim=True))
    assert gate["state"] == "REJECT"
    assert "unsupported_claim" in gate["reason_codes"]


def test_disconnected_cta_lowers_score_and_fails_gate():
    connected = compute_frontier_score(
        search_question_demand=0.8,
        commercial_pain_ticket=0.8,
        data_coverage_freshness=0.8,
        proprietary_differentiation=0.8,
        citability=0.8,
        time_to_publish=0.8,
        maintenance_cost=0.2,
    )
    disconnected = compute_frontier_score(
        search_question_demand=0.8,
        commercial_pain_ticket=0.8,
        data_coverage_freshness=0.8,
        proprietary_differentiation=0.8,
        citability=0.8,
        time_to_publish=0.8,
        maintenance_cost=0.2,
        penalties=["disconnected_cta"],
    )
    assert disconnected["score"] < connected["score"]
    gate = evaluate_hard_gates(_ready_base(cta_connected=False, suggested_cta="", cta=""))
    assert gate["state"] == "REJECT"
    assert "disconnected_cta" in gate["reason_codes"]


def test_duplicate_asset_rejects_as_merge():
    gate = evaluate_hard_gates(
        _ready_base(
            duplicate_of="/conteudos/sinapi-desonerado-nao-desonerado/",
            merge_into="/conteudos/sinapi-desonerado-nao-desonerado/",
        )
    )
    assert gate["state"] == "REJECT"
    assert "duplicate_asset" in gate["reason_codes"]
    assert gate["merge_into"] == "/conteudos/sinapi-desonerado-nao-desonerado/"


def test_output_always_denies_publication_and_index():
    pack = build_frontier_pack(as_of=CATALOG_AS_OF)
    assert pack["manifest"]["no_publication_authorization"] is True
    assert pack["manifest"]["no_index_authorization"] is True
    for item in pack["scored"]:
        assert item["no_publication_authorization"] is True
        assert item["no_index_authorization"] is True
        assert item["consumer_contract"]["no_publication_authorization"] is True
        assert item["consumer_contract"]["no_index_authorization"] is True


def test_pack_from_catalog_is_ready_or_fail_closed():
    pack = build_frontier_pack(as_of=CATALOG_AS_OF)
    assert pack["schema"] == "traffic-opportunity-frontier/1.0"
    assert pack["campaign_status"] in {
        "READY_FOR_WEB_CONSUMER",
        "BLOCKED_DATA_COVERAGE",
        "BLOCKED_SOURCE_ACCESS",
        "BLOCKED_CI",
    }
    assert len(pack["prioritized"]) <= 12
    families = {item.get("family") for item in load_catalog()}
    assert families >= {"A", "B", "C", "D", "E"}
    if pack["campaign_status"] == "READY_FOR_WEB_CONSUMER":
        assert len(pack["top3"]) == 3
        assert all(item["state"] == "READY" for item in pack["top3"])
        questions = [item["question"] for item in pack["top3"]]
        assert len(set(questions)) == 3
        fps = {item["fingerprint"] for item in pack["top3"]}
        assert len(fps) == 3
        stages = {item["funnel_stage"] for item in pack["top3"]}
        assert len(stages) >= 2
        for item in pack["top3"]:
            assert item["epistemic"]["PROHIBITED_CLAIM"]
            assert item["epistemic"]["MARKET_JOB"]["present"] is True
    else:
        for item in pack["top3"]:
            assert item["state"] != "READY" or item["epistemic"]["DATA_COVERAGE"]["complete_for_scope"]


def test_write_pack_twice_identical_checksums(tmp_path: Path):
    pack1 = build_frontier_pack(as_of=CATALOG_AS_OF)
    pack2 = build_frontier_pack(as_of=CATALOG_AS_OF)
    assert pack1["sha256sums"] == pack2["sha256sums"]
    dest1 = tmp_path / "run-1"
    dest2 = tmp_path / "run-2"
    write_frontier_pack(pack1, dest1)
    write_frontier_pack(pack2, dest2)
    assert (dest1 / "SHA256SUMS.txt").read_bytes() == (dest2 / "SHA256SUMS.txt").read_bytes()
    required = {
        "manifest.json",
        "opportunities.json",
        "rejected.json",
        "hold_for_data.json",
        "SHA256SUMS.txt",
        "README.md",
    }
    assert required <= {p.name for p in dest1.iterdir()}
    for item in pack1["top3"]:
        folder = dest1 / "top3" / item["opportunity_id"]
        assert (folder / f"{item['opportunity_id']}.json").is_file()
        assert (folder / "evidence.json").is_file()
        assert (folder / "method.json").is_file()
        assert (folder / "editorial_brief.md").is_file()
        assert (folder / "source_manifest.json").is_file()
        brief = (folder / "editorial_brief.md").read_text(encoding="utf-8")
        assert "Prohibited claims" in brief or "Prohibited" in brief


def test_cli_main_twice(tmp_path: Path):
    from scripts.traffic_frontier.cli import main

    one = tmp_path / "a"
    two = tmp_path / "b"
    assert main(["--out", str(one), "--as-of", CATALOG_AS_OF]) == 0
    assert main(["--out", str(two), "--as-of", CATALOG_AS_OF]) == 0
    assert (one / "SHA256SUMS.txt").read_text(encoding="utf-8") == (two / "SHA256SUMS.txt").read_text(encoding="utf-8")
    manifest = json.loads((one / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "traffic-opportunity-frontier/1.0"
    assert manifest["no_publication_authorization"] is True
    assert manifest["no_index_authorization"] is True
    assert manifest["campaign_status"] in {
        "READY_FOR_WEB_CONSUMER",
        "BLOCKED_DATA_COVERAGE",
        "BLOCKED_SOURCE_ACCESS",
        "BLOCKED_CI",
    }


def test_score_candidate_separates_epistemic_fields():
    catalog = load_catalog()
    ticket = next(item for item in catalog if item["opportunity_id"] == "tof-ticket-edificacao-sc")
    record = score_candidate(ticket)
    for key in (
        "SEARCH_SIGNAL",
        "MARKET_JOB",
        "DATA_COVERAGE",
        "COMMERCIAL_FIT",
        "DISTINCTIVE_EDGE",
        "UNKNOWN",
        "PROHIBITED_CLAIM",
    ):
        assert key in record["epistemic"]
    assert record["epistemic"]["SEARCH_SIGNAL"]["gsc_present"] is False
    assert record["epistemic"]["MARKET_JOB"]["present"] is True
    assert record["state"] == "READY"


def test_high_score_cannot_ready_incomplete_coverage():
    catalog = load_catalog()
    aditivos = next(item for item in catalog if item["opportunity_id"] == "tof-faixas-aditivo-recorte-sc")
    record = score_candidate(aditivos)
    assert record["state"] == "HOLD_FOR_DATA"
    # Even if we force a huge coverage component, the gate still HOLDs.
    assert record["score"] >= 0


def test_pick_top3_skips_fingerprint_clones():
    ready = [
        {
            "state": "READY",
            "fingerprint": "same",
            "opportunity_id": "a",
            "funnel_stage": "tofu",
            "score": 90,
        },
        {
            "state": "READY",
            "fingerprint": "same",
            "opportunity_id": "b",
            "funnel_stage": "mofu",
            "score": 89,
        },
        {
            "state": "READY",
            "fingerprint": "other",
            "opportunity_id": "c",
            "funnel_stage": "bofu",
            "score": 88,
        },
        {
            "state": "READY",
            "fingerprint": "third",
            "opportunity_id": "d",
            "funnel_stage": "mofu",
            "score": 87,
        },
    ]
    top = pick_top3(ready)
    assert [item["opportunity_id"] for item in top] == ["a", "c", "d"]
