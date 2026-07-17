from __future__ import annotations

from scripts.coverage.recall_benchmark import REQUIRED_STRATA, evaluate_sample


def _sample(items: list[dict]) -> dict:
    return {
        "methodology": {"required_strata": REQUIRED_STRATA},
        "portal_items": items,
    }


def test_unlabeled_items_do_not_disappear_from_denominator() -> None:
    result = evaluate_sample(
        _sample(
            [
                {"sample_id": "REAL-1", "strata": REQUIRED_STRATA, "captured_by_system": True, "capture_evidence": "id=1"},
                {"sample_id": "REAL-2", "strata": [], "captured_by_system": None},
            ]
        )
    )
    assert result["status"] == "PARTIAL"
    assert result["published_in_sample"] == 2
    assert result["pct"] is None


def test_capture_requires_evidence() -> None:
    result = evaluate_sample(
        _sample([{"sample_id": "REAL-1", "strata": REQUIRED_STRATA, "captured_by_system": True}])
    )
    assert result["status"] == "PARTIAL"
    assert "captured_without_evidence=1" in result["notes"]


def test_miss_requires_classified_reason() -> None:
    result = evaluate_sample(
        _sample([{"sample_id": "REAL-1", "strata": REQUIRED_STRATA, "captured_by_system": False}])
    )
    assert result["status"] == "PARTIAL"
    assert "misses_without_reason=1" in result["notes"]
