"""Score properties: ten components, visible weights, UNKNOWN is not zero."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.contract_publication.engine import load_snapshot, rank_candidates
from scripts.contract_publication.schema import COMPONENT_NAMES, SCORE_FORMULA_VERSION, declared_weights, load_policy
from scripts.contract_publication.score import aggregate_score

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def _ranked():
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    return rank_candidates(records, as_of=as_of, catalog_mode=mode, policy=load_policy())


def test_policy_declares_ten_visible_weights() -> None:
    weights = declared_weights()
    assert tuple(weights) == COMPONENT_NAMES
    assert len(COMPONENT_NAMES) == 10
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert SCORE_FORMULA_VERSION == "publication-value-score/1.0"


def test_each_candidate_emits_all_components_and_unknown_is_none() -> None:
    for candidate in _ranked():
        names = tuple(item.name for item in candidate.components)
        assert names == COMPONENT_NAMES
        for item in candidate.components:
            if item.status == "UNKNOWN":
                assert item.value is None
            else:
                assert item.value is not None
                assert 0.0 <= item.value <= 1.0


def test_aggregate_matches_geometric_mean_of_returned_known_components() -> None:
    import math

    policy = load_policy()
    for candidate in _ranked():
        recomputed = aggregate_score(candidate.components, policy=policy)
        assert recomputed.value == candidate.publication_value_score.value
        known = [item for item in candidate.components if item.status == "KNOWN" and item.value is not None]
        if not known:
            assert recomputed.value is None
            continue
        log_sum = sum(item.weight * math.log(min(1.0, max(0.05, float(item.value)))) for item in known)
        expected = math.exp(log_sum / sum(item.weight for item in known))
        assert abs(float(recomputed.value) - expected) < 1e-5


def test_same_snapshot_same_scores() -> None:
    first = {item.analysis_candidate_id: item.publication_value_score.as_dict() for item in _ranked()}
    second = {item.analysis_candidate_id: item.publication_value_score.as_dict() for item in _ranked()}
    assert first == second


def test_snapshot_fixture_never_declares_official_live() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blob = json.dumps(payload)
    assert "official_live" not in blob
    assert payload["catalog_mode"] == "fixture"
