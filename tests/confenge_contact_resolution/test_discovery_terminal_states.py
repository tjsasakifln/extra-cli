"""Contact discovery terminal states — offline no-op is not exhausted."""

from __future__ import annotations

from scripts.confenge_contact_resolution.discovery_state import (
    CONTACT_EXHAUSTED,
    CONTACT_FOUND_NOT_SENDABLE,
    CONTACT_READY,
    CONTACT_RETRY_PENDING,
    DEFAULT_SOURCE_LADDER,
    classify_contact_terminal,
    measure_terminal_coverage,
    sources_cover_required_ladder,
)


def test_offline_noop_is_retry_pending_not_exhausted() -> None:
    st = classify_contact_terminal(
        cnpj_raiz="12345678",
        sources_attempted=[],
        network_discovery=False,
        ladder_complete=False,
    )
    assert st.terminal_state == CONTACT_RETRY_PENDING
    assert "noop" in (st.terminal_reason or "") or "offline" in (st.terminal_reason or "")


def test_process_only_not_exhausted_even_if_ladder_complete_flag() -> None:
    """Process harvest alone must never produce CONTACT_EXHAUSTED."""
    st = classify_contact_terminal(
        cnpj_raiz="12345678",
        sources_attempted=["process_administrative_docs", "pncp_annexes"],
        network_discovery=True,
        ladder_complete=True,
    )
    assert st.terminal_state == CONTACT_RETRY_PENDING
    assert st.ladder_complete is False
    assert "ladder" in (st.terminal_reason or "")


def test_full_required_ladder_no_contact_is_exhausted() -> None:
    st = classify_contact_terminal(
        cnpj_raiz="12345678",
        sources_attempted=list(DEFAULT_SOURCE_LADDER),
        network_discovery=True,
        ladder_complete=True,
    )
    assert st.terminal_state == CONTACT_EXHAUSTED
    assert st.sources_attempted
    assert sources_cover_required_ladder(st.sources_attempted)


def test_send_ready_is_contact_ready() -> None:
    st = classify_contact_terminal(
        cnpj_raiz="12345678",
        sources_attempted=["official_site"],
        network_discovery=True,
        email_candidates=2,
        email_send_ready=1,
    )
    assert st.terminal_state == CONTACT_READY


def test_found_not_sendable() -> None:
    st = classify_contact_terminal(
        cnpj_raiz="12345678",
        sources_attempted=["official_site"],
        network_discovery=True,
        email_candidates=1,
        email_send_ready=0,
    )
    assert st.terminal_state == CONTACT_FOUND_NOT_SENDABLE


def test_terminal_coverage_closed_sum() -> None:
    states = [
        classify_contact_terminal(
            cnpj_raiz="1",
            sources_attempted=["site"],
            network_discovery=True,
            email_send_ready=1,
        ),
        classify_contact_terminal(
            cnpj_raiz="2",
            sources_attempted=list(DEFAULT_SOURCE_LADDER),
            network_discovery=True,
            ladder_complete=True,
        ),
    ]
    cov = measure_terminal_coverage(states, population_total=5)
    assert cov["closed_sum"] is True
    assert cov["never_attempted"] == 3
    assert cov["terminal_counts"][CONTACT_READY] == 1
    assert cov["terminal_counts"][CONTACT_EXHAUSTED] == 1
