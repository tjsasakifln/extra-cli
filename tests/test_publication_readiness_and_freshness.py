"""Regressions for outreach publication acceptance, population freshness and diagnostics.

Three distinct defects are covered here:

1. RECONCILE_ACCEPTABLE (>= 0.995) was conflated with the acceptance level a
   commercial feed needs (== 1.0). A PARTIAL population must never reach the
   outreach feed just because it clears the reconcile threshold.
2. ``population_as_of`` was max(target_fit_computed_at). Target-fit is
   content-addressed, so an unchanged-but-verified national population aged past
   the 24h staleness gate and deadlocked publication.
3. ``feed-cycle`` reported ``pipeline failed with exit 1:`` with an empty cause
   whenever the child pipeline reported its failure on stdout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.confenge_activation.publish import _assert_publication_ready_population
from scripts.confenge_target_fit.coverage import (
    PUBLICATION_COVERAGE_THRESHOLD,
    TARGET_FIT_COVERAGE_THRESHOLD,
    build_coverage_snapshot,
    publication_ready,
    reconcile_acceptable,
)
from scripts.decision_unit_intelligence.batch_population import _population_freshness
from scripts.ops.confenge_feed_cycle import _pipeline_failure_message

VERIFIED_AT = "2026-08-27T11:10:28+00:00"


def _snapshot(*, canonical: int, materialized: int, exclusions: int = 0) -> dict:
    gap = {"DNC": exclusions} if exclusions else None
    return build_coverage_snapshot(
        canonical_company_count=canonical,
        materialized_company_count=materialized,
        expected_company_roots=canonical,
        visited_company_roots=canonical,
        unexplained_missing=0,
        pagination_exhausted_normally=True,
        explicit_exclusions=exclusions,
        exclusion_reason_counts=gap,
        gap_breakdown=gap,
        last_full_reconcile_completed_at=VERIFIED_AT,
    )


# --- 1. the two acceptance levels are distinct -----------------------------


def test_publication_threshold_is_stricter_than_reconcile_threshold():
    assert PUBLICATION_COVERAGE_THRESHOLD == 1.0
    assert TARGET_FIT_COVERAGE_THRESHOLD < PUBLICATION_COVERAGE_THRESHOLD


def test_complete_coverage_is_both_reconcile_acceptable_and_publication_ready():
    snap = _snapshot(canonical=1000, materialized=1000)
    assert snap["coverage_ratio"] == 1.0
    assert snap["RECONCILE_ACCEPTABLE"] is True
    assert snap["PUBLICATION_READY"] is True
    assert reconcile_acceptable(snap) is True
    assert publication_ready(snap) is True


def test_partial_above_reconcile_threshold_is_never_publication_ready():
    snap = _snapshot(canonical=1000, materialized=997, exclusions=3)
    assert snap["coverage_ratio"] == pytest.approx(0.997)
    assert snap["coverage_ratio"] > TARGET_FIT_COVERAGE_THRESHOLD
    assert snap["RECONCILE_ACCEPTABLE"] is True, "0.997 stays usable operational state"
    assert snap["PUBLICATION_READY"] is False, "0.997 must never back a commercial feed"
    assert publication_ready(snap) is False


def test_unexplained_gaps_are_neither_acceptable_nor_publishable():
    snap = _snapshot(canonical=1000, materialized=997)
    assert snap["coverage_mode"] == "PARTIAL"
    assert snap["RECONCILE_ACCEPTABLE"] is False
    assert snap["PUBLICATION_READY"] is False


def test_legacy_snapshot_without_the_field_is_recomputed_not_assumed():
    legacy = _snapshot(canonical=1000, materialized=997, exclusions=3)
    legacy.pop("PUBLICATION_READY")
    legacy.pop("RECONCILE_ACCEPTABLE")
    assert publication_ready(legacy) is False
    assert reconcile_acceptable(legacy) is True


# --- publisher refuses a population that is not publication ready ----------


def test_publisher_refuses_sub_complete_coverage():
    with pytest.raises(ValueError, match="not publication ready"):
        _assert_publication_ready_population(
            {"population_coverage_ratio": 0.997, "population_publication_ready": True}
        )


def test_publisher_refuses_explicitly_unready_population():
    with pytest.raises(ValueError, match="not publication ready"):
        _assert_publication_ready_population({"population_publication_ready": False})


def test_publisher_accepts_complete_population():
    _assert_publication_ready_population(
        {"population_coverage_ratio": 1.0, "population_publication_ready": True}
    )


def test_publisher_refuses_a_legacy_projection_without_publication_attestation():
    with pytest.raises(ValueError, match="missing or invalid"):
        _assert_publication_ready_population({})


@pytest.mark.parametrize("ratio", [True, "1.0"])
def test_publisher_refuses_non_numeric_coverage_attestations(ratio: object):
    with pytest.raises(ValueError, match="missing or invalid"):
        _assert_publication_ready_population(
            {"population_coverage_ratio": ratio, "population_publication_ready": True}
        )


@pytest.mark.parametrize("ratio", [float("nan"), float("inf"), 1.001])
def test_publisher_refuses_non_finite_or_overcomplete_coverage(ratio: float):
    with pytest.raises(ValueError, match="not publication ready"):
        _assert_publication_ready_population(
            {"population_coverage_ratio": ratio, "population_publication_ready": True}
        )


# --- 2. freshness follows the verified reconcile, not row churn ------------


def test_unchanged_but_verified_population_is_fresh_from_the_reconcile():
    stale_rows = ["2026-08-26T03:37:53+00:00"]
    out = _population_freshness(stale_rows, _snapshot(canonical=1000, materialized=1000))
    assert out["population_as_of"] == VERIFIED_AT
    assert out["population_as_of_source"] == "target_fit_full_reconcile"
    assert out["population_verified_at"] == VERIFIED_AT
    assert out["population_publication_ready"] is True


def test_partial_attestation_cannot_refresh_the_population_clock():
    stale_rows = ["2026-08-26T03:37:53+00:00"]
    out = _population_freshness(stale_rows, _snapshot(canonical=1000, materialized=997, exclusions=3))
    assert out["population_as_of"] == stale_rows[-1], "falls back and stays fail-closed"
    assert out["population_as_of_source"] == "target_fit_computed_at_max"
    assert out["population_verified_at"] is None
    assert out["population_publication_ready"] is False


def test_missing_attestation_preserves_the_previous_fail_closed_behaviour():
    rows = ["2026-08-26T03:37:53+00:00"]
    out = _population_freshness(rows, None)
    assert out["population_as_of"] == rows[-1]
    assert out["population_as_of_source"] == "target_fit_computed_at_max"


def test_fresh_row_does_not_refresh_an_older_full_population_attestation():
    newer_rows = ["2026-08-27T20:00:00+00:00"]
    out = _population_freshness(newer_rows, _snapshot(canonical=1000, materialized=1000))
    assert out["population_as_of"] == VERIFIED_AT
    assert out["population_as_of_source"] == "target_fit_full_reconcile"


def test_timestamp_comparison_uses_instants_not_rfc3339_string_order():
    rows = ["2026-08-27T09:30:00-03:00", "2026-08-27T12:00:00+00:00"]
    out = _population_freshness(rows, None)
    assert out["population_as_of"] == rows[0], "12:30Z is newer than 12:00Z"


# --- 3. the operator always gets the factual cause -------------------------


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["pipeline"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_structured_stdout_failure_is_reported():
    message = _pipeline_failure_message(
        _completed(1, stdout='{"ok": false, "error": "authoritative contact population is stale"}'),
        Path("/var/run/cycle"),
    )
    assert "authoritative contact population is stale" in message
    assert message.rstrip().endswith("cycle-command.json")


def test_structured_errors_list_is_reported():
    message = _pipeline_failure_message(
        _completed(1, stdout='{"ok": false, "errors": ["gap_detected", "coverage_incomplete"]}'),
        Path("/var/run/cycle"),
    )
    assert "gap_detected" in message and "coverage_incomplete" in message


def test_stderr_failure_is_still_reported():
    message = _pipeline_failure_message(_completed(2, stderr="Traceback: boom"), Path("/var/run/cycle"))
    assert "Traceback: boom" in message
    assert "exit 2" in message


def test_silent_failure_says_so_instead_of_trailing_an_empty_colon():
    message = _pipeline_failure_message(_completed(1), Path("/var/run/cycle"))
    assert "no diagnostic output" in message
    assert not message.rstrip().endswith(":")
