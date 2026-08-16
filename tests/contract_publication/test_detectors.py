"""Detectors: absence is not an event; atypical is not irregular."""

from __future__ import annotations

from pathlib import Path

from scripts.contract_publication.detectors import build_cohort, run_detectors
from scripts.contract_publication.engine import load_snapshot, rank_candidates
from scripts.contract_publication.facts import project_record
from scripts.contract_publication.schema import load_policy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def _by_id():
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    return as_of, {item["canonical_contract_id"]: item for item in records}, mode


def test_null_fields_do_not_fire_events() -> None:
    as_of, by_id, _mode = _by_id()
    projected = project_record(by_id["CAND-ABSENT-01"], as_of=as_of)
    detectors = run_detectors(projected, build_cohort([by_id["CAND-ABSENT-01"]]), as_of=as_of)
    fired_insight = [
        item
        for item in detectors
        if item.fired
        and item.detector_id
        in {
            "material_value_change",
            "material_term_change",
            "documented_amendment",
            "documented_price_index",
            "peer_difference",
        }
    ]
    assert fired_insight == []
    value_change = next(item for item in detectors if item.detector_id == "material_value_change")
    assert value_change.status == "UNKNOWN"
    assert value_change.result is None
    assert "irregular" not in value_change.reason_code


def test_material_value_and_term_fire_only_with_source() -> None:
    as_of, by_id, _mode = _by_id()
    projected = project_record(by_id["CAND-VALUE-TERM-01"], as_of=as_of)
    detectors = {
        item.detector_id: item
        for item in run_detectors(projected, build_cohort([by_id["CAND-VALUE-TERM-01"]]), as_of=as_of)
    }
    assert detectors["material_value_change"].fired
    assert detectors["material_term_change"].fired
    assert detectors["material_value_change"].evidence_refs
    assert detectors["material_value_change"].epistemic_class == "CALCULATION"
    assert "irregular" not in detectors["material_value_change"].reason_code


def test_reajuste_requires_instrument() -> None:
    as_of, by_id, _mode = _by_id()
    projected = project_record(by_id["CAND-REAJUSTE-01"], as_of=as_of)
    detectors = {
        item.detector_id: item
        for item in run_detectors(projected, build_cohort([by_id["CAND-REAJUSTE-01"]]), as_of=as_of)
    }
    assert detectors["adjustment_anniversary"].fired
    assert detectors["adjustment_anniversary"].epistemic_class == "FACT"
    assert "doc:reajuste-clausula" in detectors["adjustment_anniversary"].evidence_refs


def test_price_index_without_document_is_unknown() -> None:
    as_of, by_id, _mode = _by_id()
    record = dict(by_id["CAND-BDI-01"])
    record.pop("index_document_id")
    projected = project_record(record, as_of=as_of)
    detectors = {item.detector_id: item for item in run_detectors(projected, build_cohort([record]), as_of=as_of)}
    assert detectors["documented_price_index"].status == "UNKNOWN"
    assert not detectors["documented_price_index"].fired


def test_peer_unversioned_interface_is_refused() -> None:
    as_of, by_id, _mode = _by_id()
    record = dict(by_id["CAND-PEER-01"])
    record["peer_group"] = {"status": "COMPARABLE", "sample_size": 12, "median_value": 1}
    projected = project_record(record, as_of=as_of)
    detectors = {item.detector_id: item for item in run_detectors(projected, build_cohort([record]), as_of=as_of)}
    assert detectors["peer_difference"].status == "UNKNOWN"
    assert detectors["peer_difference"].reason_code == "peer_interface_unversioned"


def test_not_comparable_is_honest_hold() -> None:
    as_of, by_id, _mode = _by_id()
    projected = project_record(by_id["CAND-NOT-COMPARABLE-01"], as_of=as_of)
    detectors = {
        item.detector_id: item
        for item in run_detectors(projected, build_cohort([by_id["CAND-NOT-COMPARABLE-01"]]), as_of=as_of)
    }
    assert detectors["peer_difference"].reason_code == "NOT_COMPARABLE"
    assert detectors["peer_difference"].status == "HOLD"
    assert not detectors["peer_difference"].fired


def test_identity_swap_is_inference_not_fact() -> None:
    as_of, by_id, _mode = _by_id()
    projected = project_record(by_id["CAND-ABSENT-01"], as_of=as_of)
    detectors = {
        item.detector_id: item
        for item in run_detectors(projected, build_cohort([by_id["CAND-ABSENT-01"]]), as_of=as_of)
    }
    item = detectors["identity_swap_is_not_insight"]
    assert item.epistemic_class == "INFERENCE"
    assert not item.fired


def test_ranking_states_are_only_allowed_public_states() -> None:
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=mode, policy=load_policy())
    assert {item.candidate_state for item in ranked} <= {"REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW"}
    assert any(item.candidate_state == "EDITORIAL_REVIEW" for item in ranked)
    assert any(item.analysis_candidate_id == "CAND-REJECT-01" and item.candidate_state == "REJECT" for item in ranked)
    hold = next(item for item in ranked if item.analysis_candidate_id == "CAND-HOLD-01")
    assert hold.candidate_state == "HOLD_FOR_DATA"
