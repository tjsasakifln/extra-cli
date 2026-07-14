"""Tests for coverage state machine — Story 1.5.

Tests cover:
    - All 9 states exist and have correct string values
    - All valid transitions
    - Invalid transitions rejected
    - determine_initial_state for various scenarios
    - determine_run_result_state with pagination proof
    - evaluate_freshness with SLA windows
    - map_monitor_state_to_evidence
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.coverage.states import (
    COVERED_STATES,
    CoverageState,
    determine_initial_state,
    determine_run_result_state,
    evaluate_freshness,
    is_valid_transition,
    map_monitor_state_to_evidence,
)

# ---------------------------------------------------------------------------
# CoverageState enum
# ---------------------------------------------------------------------------


class TestCoverageState:
    def test_all_9_states_exist(self):
        """All 9 coverage states must be defined."""
        expected = {
            "not_applicable",
            "pending",
            "running",
            "success_with_data",
            "success_zero",
            "partial",
            "error",
            "blocked",
            "stale",
        }
        actual = {s.value for s in CoverageState}
        assert actual == expected, f"Missing or extra states: {actual ^ expected}"

    def test_covered_states(self):
        """success_with_data and success_zero count as covered."""
        assert CoverageState.SUCCESS_WITH_DATA in COVERED_STATES
        assert CoverageState.SUCCESS_ZERO in COVERED_STATES
        assert len(COVERED_STATES) == 2


# ---------------------------------------------------------------------------
# Transition validation
# ---------------------------------------------------------------------------


class TestValidTransitions:
    def test_pending_to_running(self):
        assert is_valid_transition("pending", "running")

    def test_pending_to_blocked(self):
        assert is_valid_transition("pending", "blocked")

    def test_running_to_success_with_data(self):
        assert is_valid_transition("running", "success_with_data")

    def test_running_to_success_zero(self):
        assert is_valid_transition("running", "success_zero")

    def test_running_to_partial(self):
        assert is_valid_transition("running", "partial")

    def test_running_to_error(self):
        assert is_valid_transition("running", "error")

    def test_running_to_blocked(self):
        assert is_valid_transition("running", "blocked")

    def test_not_applicable_is_terminal(self):
        """not_applicable has no valid transitions."""
        for state in CoverageState:
            if state.value != "not_applicable":
                assert not is_valid_transition("not_applicable", state.value), (
                    f"not_applicable should not transition to {state.value}"
                )

    def test_success_with_data_to_stale(self):
        assert is_valid_transition("success_with_data", "stale")

    def test_success_with_data_to_running(self):
        assert is_valid_transition("success_with_data", "running")

    def test_stale_to_running(self):
        assert is_valid_transition("stale", "running")

    def test_error_to_blocked(self):
        assert is_valid_transition("error", "blocked")

    def test_blocked_to_pending(self):
        assert is_valid_transition("blocked", "pending")

    def test_blocked_to_not_applicable(self):
        assert is_valid_transition("blocked", "not_applicable")


class TestInvalidTransitions:
    def test_not_applicable_to_anything(self):
        assert not is_valid_transition("not_applicable", "success_with_data")
        assert not is_valid_transition("not_applicable", "running")

    def test_success_zero_to_not_applicable(self):
        assert not is_valid_transition("success_zero", "not_applicable")

    def test_stale_to_success_with_data(self):
        """stale must go through running first."""
        assert not is_valid_transition("stale", "success_with_data")

    def test_invalid_state_string(self):
        assert not is_valid_transition("invalid_state", "running")
        assert not is_valid_transition("pending", "invalid_target")

    def test_pending_to_success_with_data(self):
        """pending must go through running first."""
        assert not is_valid_transition("pending", "success_with_data")


# ---------------------------------------------------------------------------
# determine_initial_state
# ---------------------------------------------------------------------------


class TestDetermineInitialState:
    def test_not_applicable(self):
        result = determine_initial_state({}, applicability="not_applicable")
        assert result == CoverageState.NOT_APPLICABLE

    def test_pending_when_unknown(self):
        result = determine_initial_state({}, applicability="unknown")
        assert result == CoverageState.PENDING

    def test_blocked_when_source_blocked(self):
        result = determine_initial_state({"is_blocked": True}, applicability="applicable")
        assert result == CoverageState.BLOCKED

    def test_pending_when_applicable(self):
        result = determine_initial_state({"is_blocked": False}, applicability="applicable")
        assert result == CoverageState.PENDING

    def test_pending_when_applicable_no_block(self):
        result = determine_initial_state({}, applicability="applicable")
        assert result == CoverageState.PENDING


# ---------------------------------------------------------------------------
# determine_run_result_state
# ---------------------------------------------------------------------------


class TestDetermineRunResultState:
    def test_success_with_data_when_fetched(self):
        result = determine_run_result_state(fetched=10, transformed=10, persisted=10, fetch_complete=True)
        assert result == CoverageState.SUCCESS_WITH_DATA

    def test_success_zero_with_pagination_proof(self):
        """success_zero requires pagination proof."""
        result = determine_run_result_state(
            fetched=0,
            transformed=0,
            persisted=0,
            fetch_complete=True,
            supports_zero_proof=True,
            pages_expected=5,
            pages_processed=5,
        )
        assert result == CoverageState.SUCCESS_ZERO, f"Expected success_zero, got {result}"

    def test_partial_when_pagination_incomplete(self):
        """Without pagination proof, zero records = partial."""
        result = determine_run_result_state(
            fetched=0,
            transformed=0,
            persisted=0,
            fetch_complete=True,
            supports_zero_proof=False,
        )
        assert result == CoverageState.PARTIAL, f"Expected partial, got {result}"

    def test_partial_when_fetch_incomplete(self):
        result = determine_run_result_state(
            fetched=0,
            transformed=0,
            persisted=0,
            fetch_complete=False,
        )
        assert result == CoverageState.PARTIAL

    def test_success_zero_with_records_expected_zero(self):
        """When records_expected=0 and fetch complete, success_zero is valid."""
        result = determine_run_result_state(
            fetched=0,
            transformed=0,
            persisted=0,
            fetch_complete=True,
            records_expected=0,
        )
        assert result == CoverageState.SUCCESS_ZERO

    def test_partial_when_pages_missing(self):
        """Partial pagination even with fetch_complete."""
        result = determine_run_result_state(
            fetched=0,
            transformed=0,
            persisted=0,
            fetch_complete=True,
            supports_zero_proof=True,
            pages_expected=10,
            pages_processed=3,
        )
        assert result == CoverageState.PARTIAL


# ---------------------------------------------------------------------------
# evaluate_freshness
# ---------------------------------------------------------------------------


class TestEvaluateFreshness:
    def test_fresh_within_sla(self):
        checked = datetime.now(UTC) - timedelta(hours=2)
        state, freshness = evaluate_freshness(CoverageState.SUCCESS_WITH_DATA, checked, freshness_sla_hours=24)
        assert state == CoverageState.SUCCESS_WITH_DATA
        assert freshness == "fresh"

    def test_stale_beyond_sla(self):
        checked = datetime.now(UTC) - timedelta(hours=30)
        state, freshness = evaluate_freshness(CoverageState.SUCCESS_WITH_DATA, checked, freshness_sla_hours=24)
        assert state == CoverageState.SUCCESS_WITH_DATA  # State unchanged, freshness flagged
        assert freshness == "stale"

    def test_overdue_double_sla(self):
        checked = datetime.now(UTC) - timedelta(hours=72)
        state, freshness = evaluate_freshness(CoverageState.SUCCESS_WITH_DATA, checked, freshness_sla_hours=24)
        assert state == CoverageState.STALE
        assert freshness == "overdue"

    def test_not_applicable_returns_unknown(self):
        state, freshness = evaluate_freshness(CoverageState.NOT_APPLICABLE, None, freshness_sla_hours=24)
        assert freshness == "unknown"

    def test_no_checked_at_returns_unknown(self):
        state, freshness = evaluate_freshness(CoverageState.PENDING, None, freshness_sla_hours=24)
        assert freshness == "unknown"

    def test_naive_datetime_conversion(self):
        """Handle naive datetimes by converting to timezone-aware."""
        checked = datetime.now() - timedelta(hours=2)  # naive
        state, freshness = evaluate_freshness(CoverageState.SUCCESS_WITH_DATA, checked, freshness_sla_hours=24)
        assert freshness == "fresh"


# ---------------------------------------------------------------------------
# map_monitor_state_to_evidence
# ---------------------------------------------------------------------------


class TestMapMonitorStateToEvidence:
    def test_success_with_data(self):
        state, code = map_monitor_state_to_evidence("success", "", fetched=10)
        assert state == CoverageState.SUCCESS_WITH_DATA
        assert code == ""

    def test_success_zero(self):
        state, code = map_monitor_state_to_evidence("success", "", fetched=0)
        assert state == CoverageState.SUCCESS_ZERO

    def test_failed(self):
        state, code = map_monitor_state_to_evidence("failed", "fetch_failed")
        assert state == CoverageState.ERROR
        assert code == "fetch_failed"

    def test_missing_credentials_to_blocked(self):
        state, code = map_monitor_state_to_evidence("skipped", "missing_credentials")
        assert state == CoverageState.BLOCKED, f"Expected BLOCKED, got {state}"
        assert code == "missing_credentials"

    def test_degraded_to_partial(self):
        state, code = map_monitor_state_to_evidence("degraded", "")
        assert state == CoverageState.PARTIAL

    def test_skipped_to_pending(self):
        state, code = map_monitor_state_to_evidence("skipped", "")
        assert state == CoverageState.PENDING

    def test_crawler_not_implemented_to_not_applicable(self):
        state, code = map_monitor_state_to_evidence("failed", "crawler_not_implemented")
        assert state == CoverageState.NOT_APPLICABLE
