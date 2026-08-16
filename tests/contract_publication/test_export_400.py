"""Goal 03 consumer contract compatibility."""

from __future__ import annotations

from pathlib import Path

from scripts.contract_publication.engine import build_packs, load_snapshot, rank_candidates
from scripts.contract_publication.export_400 import export_analysis, export_bundle
from scripts.contract_publication.schema import CONSUMER_SCHEMA, PACK_SCHEMA, SCHEMA, SCORE_FORMULA_VERSION, load_policy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"

REQUIRED_FIELDS = {
    "analysis_candidate_id",
    "canonical_contract_ids",
    "candidate_score",
    "reason_summary",
    "evidence_pack_version",
    "evidence_pack_hash",
    "peer_group",
    "timeline",
    "official_refs",
    "calculations",
    "epistemic_classes",
    "as_of",
    "freshness",
    "coverage",
    "limitations",
    "safety_flags",
    "data_state",
    "data_state_facts",
    "reason_codes",
}


def _run_bundle():
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    policy = load_policy()
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=mode, policy=policy)
    packs = build_packs(records, ranked, as_of=as_of, catalog_mode=mode, policy=policy)
    return ranked, packs, export_bundle(ranked, packs)


def test_export_has_authorized_fields_and_versions() -> None:
    _ranked, _packs, bundle = _run_bundle()
    assert bundle["schema"] == CONSUMER_SCHEMA
    assert bundle["catalog_mode"] == "fixture"
    for analysis in bundle["analyses"]:
        assert REQUIRED_FIELDS <= set(analysis)
        assert analysis["candidate_score"]["schema"] == SCHEMA
        assert analysis["candidate_score"]["formula_version"] == SCORE_FORMULA_VERSION
        assert analysis["evidence_pack_schema"] in {PACK_SCHEMA, "contract_evidence_pack/1.0"}
        assert analysis["data_state"] in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}
        assert "INDEX" not in analysis["data_state"]
        assert "PUBLISHABLE" not in analysis["data_state"]
        assert analysis["catalog_mode"] == "fixture"


def test_not_comparable_does_not_alone_reject_defensible_pack() -> None:
    ranked, packs, _exported = _run_bundle()
    candidate = next(item for item in ranked if item.analysis_candidate_id == "CAND-NOT-COMPARABLE-01")
    analysis = export_analysis(candidate, packs[candidate.analysis_candidate_id])
    assert analysis["peer_group"]["status"] == "NOT_COMPARABLE"
    if candidate.candidate_state == "EDITORIAL_REVIEW":
        assert analysis["data_state"] != "DATA_REJECT"
        assert "NOT_COMPARABLE" in analysis["reason_codes"]


def test_claimed_live_fixture_is_rejected() -> None:
    ranked, packs, _ = _run_bundle()
    candidate = ranked[0]
    analysis = export_analysis(candidate, packs[candidate.analysis_candidate_id], claimed_live=True)
    assert analysis["data_state"] == "DATA_REJECT"
    assert "fixture_as_live" in analysis["reason_codes"]


def test_rejected_candidate_is_data_reject() -> None:
    ranked, packs, _ = _run_bundle()
    candidate = next(item for item in ranked if item.analysis_candidate_id == "CAND-REJECT-01")
    analysis = export_analysis(candidate, packs[candidate.analysis_candidate_id])
    assert analysis["data_state"] == "DATA_REJECT"
    assert "candidate_rejected_after_refresh" in analysis["reason_codes"]
