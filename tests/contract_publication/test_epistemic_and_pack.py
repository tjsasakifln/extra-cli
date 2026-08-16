"""Epistemic classes, pack hashes and reputational flags."""

from __future__ import annotations

from pathlib import Path

from scripts.contract_publication.engine import build_packs, load_snapshot, rank_candidates
from scripts.contract_publication.pack import assert_every_fact_has_ref, iter_epistemic_nodes
from scripts.contract_publication.schema import PACK_SCHEMA, load_policy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def _run():
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    policy = load_policy()
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=mode, policy=policy)
    packs = build_packs(records, ranked, as_of=as_of, catalog_mode=mode, policy=policy)
    return ranked, packs


def test_every_fact_and_calculation_has_evidence_ref() -> None:
    _ranked, packs = _run()
    for pack in packs.values():
        assert_every_fact_has_ref(pack)
        labeled = iter_epistemic_nodes(pack)
        assert labeled
        for path, item in labeled:
            assert item.get("epistemic_class") in {"FACT", "CALCULATION"} or item.get("class") in {
                "FACT",
                "CALCULATION",
            }
            assert item.get("evidence_refs"), path
        for item in pack.get("values") or ():
            if item.get("epistemic_class") in {"FACT", "CALCULATION"}:
                assert item.get("evidence_refs")


def test_inference_never_serialized_as_fact() -> None:
    _ranked, packs = _run()
    for pack in packs.values():
        for item in pack["facts"]:
            assert item["epistemic_class"] != "INFERENCE"
            assert item.get("class") != "INFERENCE"
        for item in pack["inferences"]:
            assert item["epistemic_class"] == "INFERENCE"


def test_unknown_remains_visible() -> None:
    _ranked, packs = _run()
    absent = packs["CAND-ABSENT-01"]
    unknown_ids = {item["id"] for item in absent["unknowns"]}
    assert "value_changes" in unknown_ids or "material_value_change" in unknown_ids
    for item in absent["unknowns"]:
        assert item["value"] is None
        assert item["epistemic_class"] == "UNKNOWN"


def test_rebuild_pack_same_content_hash() -> None:
    first = _run()[1]
    second = _run()[1]
    assert set(first) == set(second)
    for key in first:
        assert first[key]["content_hash"] == second[key]["content_hash"]
        assert first[key]["schema"] == PACK_SCHEMA
        assert first[key]["producer_sha"]


def test_sensitive_record_requires_review_flag_and_masks_cpf() -> None:
    ranked, packs = _run()
    candidate = next(item for item in ranked if item.analysis_candidate_id == "CAND-SENSITIVE-01")
    assert "reputational_review_required" in candidate.sensitivity_flags
    pack = packs["CAND-SENSITIVE-01"]
    assert "reputational_review_required" in pack["sensitivity_flags"]
    blob = str(pack)
    assert "529.982.247-25" not in blob
    assert "52998224725" not in blob


def test_pack_omits_brand_seo_cta_and_accusation() -> None:
    _ranked, packs = _run()
    forbidden = (
        "seo_title",
        "cta",
        "noindex",
        "PUBLISHABLE_INDEX",
        "PUBLISHABLE_NOINDEX",
        "has_right",
        "should_adjust",
    )
    for pack in packs.values():
        blob = str(pack)
        for token in forbidden:
            assert token not in blob
        assert pack.get("candidate_state") in {"REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW"}
        assert "INDEX" not in (pack.get("reason_codes") or [])
