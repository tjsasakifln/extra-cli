"""Tests for the golden-dataset registry (#138). Drives shipped functions."""

from __future__ import annotations

import pytest

from scripts.quality.golden_dataset import (
    CRITICAL_STAGES,
    STAGE_GOLDEN,
    GoldenRegistry,
    assign_split,
    evaluate_benchmark,
    ingest_candidate,
    promotion_blocked,
    register_miss,
    replay,
    tokenize_pii,
)


def _candidate(**overrides):
    kwargs = {
        "case_id": "gd-001",
        "public_stage": "source_miss",
        "origin": "alerta_only:#35",
        "snapshot_at": "2026-07-15T00:00:00Z",
        "published_at": "2026-07-01",
        "payload": {"identity": "PNCP-1", "objeto": "obra"},
        "expected": {"captured": False, "miss_reason": "source_gap"},
        "split_cutoff": "2026-07-10",
        "version": "2026.08.1",
    }
    kwargs.update(overrides)
    return ingest_candidate(**kwargs)


def test_registry_lists_version_hash_origin_adjudicator_restriction() -> None:
    registry = GoldenRegistry(version="2026.08.1")
    case = register_miss(
        registry,
        case_id="gd-001",
        public_stage="source_miss",
        origin="alerta_only:#35",
        snapshot_at="2026-07-15T00:00:00Z",
        published_at="2026-07-01",
        payload={"identity": "PNCP-1"},
        expected={"captured": True},
        split_cutoff="2026-07-10",
        adjudicator="qa-human",
    )
    assert case.stage == STAGE_GOLDEN
    listed = registry.list_cases()
    assert listed[0]["version"] == "2026.08.1"
    assert listed[0]["hash"] == case.content_hash
    assert listed[0]["origin"] == "alerta_only:#35"
    assert listed[0]["adjudicator"] == "qa-human"
    assert listed[0]["restriction"] == "public-authorized"


def test_corpus_covers_critical_public_stages_including_negatives() -> None:
    assert "negative_zero" in CRITICAL_STAGES
    assert "negative_revoked" in CRITICAL_STAGES
    assert "factual_extraction" in CRITICAL_STAGES
    registry = GoldenRegistry(version="v1")
    for idx, stage in enumerate(CRITICAL_STAGES):
        register_miss(
            registry,
            case_id=f"st-{idx}",
            public_stage=stage,
            origin="audit",
            snapshot_at="2026-07-15T00:00:00Z",
            published_at="2026-06-01",
            payload={"k": stage},
            expected={"ok": True},
            split_cutoff="2026-07-01",
            adjudicator="qa",
        )
    stages = {c["public_stage"] for c in registry.list_cases()}
    assert stages == set(CRITICAL_STAGES)


def test_client_action_outcome_cannot_be_authority() -> None:
    with pytest.raises(ValueError, match="not authority"):
        _candidate(payload={"identity": "x", "client": "CONFENGE"})
    with pytest.raises(ValueError, match="not authority"):
        replay(_candidate(), {"captured": False, "outcome": "won"})


def test_temporal_split_prevents_leakage() -> None:
    assert assign_split("2026-06-30", cutoff="2026-07-10") == "train"
    assert assign_split("2026-07-10", cutoff="2026-07-10") == "eval"
    assert assign_split("2026-07-11", cutoff="2026-07-10") == "holdout"
    case = _candidate(published_at="2026-07-20")
    assert case.split == "holdout"


def test_pii_is_tokenized() -> None:
    token = tokenize_pii("123.456.789-00")
    assert token.startswith("pii_")
    assert "123" not in token
    assert tokenize_pii("123.456.789-00") == token


def test_replay_and_material_regression_blocks_promotion() -> None:
    registry = GoldenRegistry(version="v1")
    golden = register_miss(
        registry,
        case_id="gd-reg",
        public_stage="pagination_miss",
        origin="pncp",
        snapshot_at="2026-07-15T00:00:00Z",
        published_at="2026-06-01",
        payload={"pages_expected": 3},
        expected={"pages_fetched": 3, "captured": True},
        split_cutoff="2026-07-01",
        adjudicator="qa",
    )
    ok = replay(golden, {"pages_fetched": 3, "captured": True})
    assert ok["ok"] is True
    bench = evaluate_benchmark(
        [golden],
        {"gd-reg": {"pages_fetched": 2, "captured": False}},
        baseline_rate=1.0,
    )
    assert bench["regressions"] == ["gd-reg"]
    assert bench["delta"] == -1.0
    assert promotion_blocked(bench) is True
    good = evaluate_benchmark(
        [golden],
        {"gd-reg": {"pages_fetched": 3, "captured": True}},
        baseline_rate=1.0,
    )
    assert promotion_blocked(good) is False
    assert good["overall_rate"] == 1.0
