"""Mailbox purpose (PRESS/social) + contact coverage closed sums + no ESR hard cap."""

from __future__ import annotations

import pytest

from scripts.confenge_contact_resolution.contact_coverage import (
    MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
    assert_no_send_ready_hard_cap,
    measure_contact_coverage,
)
from scripts.confenge_contact_resolution.mailbox_purpose import (
    PURPOSE_PRESS,
    PURPOSE_SOCIAL_PROGRAM,
    classify_mailbox_purpose,
    is_mailbox_send_allowed,
)


def test_imprensa_blocked_as_press() -> None:
    r = classify_mailbox_purpose("imprensa@matera.com")
    assert r.purpose == PURPOSE_PRESS
    assert r.send_blocked is True
    assert is_mailbox_send_allowed("imprensa@matera.com") is False


def test_programabem_blocked_as_social_program() -> None:
    r = classify_mailbox_purpose("programabem@martins.com.br")
    assert r.purpose == PURPOSE_SOCIAL_PROGRAM
    assert r.send_blocked is True


def test_eshop_and_sac_still_blocked() -> None:
    assert is_mailbox_send_allowed("eshop@barranova.com") is False
    assert is_mailbox_send_allowed("sac@empresa.com.br") is False
    assert is_mailbox_send_allowed("suporte@empresa.com.br") is False
    assert is_mailbox_send_allowed("rh@empresa.com.br") is False


def test_commercial_and_licitacoes_allowed() -> None:
    assert is_mailbox_send_allowed("comercial@tracado.com.br") is True
    assert is_mailbox_send_allowed("licitacoes@empresa.com.br") is True
    assert is_mailbox_send_allowed("engenharia@empresa.com.br") is True


def test_info_not_misclassified_as_financeiro_nf() -> None:
    """Regression: short alias 'nf' must not substring-match inside 'info'."""
    r = classify_mailbox_purpose("info@falk.com")
    assert r.purpose == "GENERIC_CONTACT"
    assert r.send_blocked is False


def test_contact_coverage_closed_sum() -> None:
    confirmed = [f"c{i}" for i in range(100)]
    attempted = [f"c{i}" for i in range(40)]
    real = [f"c{i}" for i in range(15)]
    owned = [f"c{i}" for i in range(12)]
    identity = [f"c{i}" for i in range(10)]
    esr = [f"c{i}" for i in range(8)]
    m = measure_contact_coverage(
        target_confirmed_keys=confirmed,
        attempted_keys=attempted,
        real_email_keys=real,
        company_owned_keys=owned,
        identity_safe_keys=identity,
        email_send_ready_keys=esr,
        rejection_reasons={"mailbox_purpose_rejected": 2, "identity_rejected": 3},
    )
    assert m["TARGET_CONFIRMED_total"] == 100
    assert m["contact_discovery_attempted"] == 40
    assert m["contact_discovery_not_attempted"] == 60
    assert m["closed_sum_check"]["confirmed_eq_attempted_plus_never"] is True
    assert m["email_send_ready"] == 8
    assert m["MINIMUM_PILOT_ACCEPTANCE_SAMPLE"] == 50
    assert m["pilot_sample_met"] is False
    # Honest rate: 8 of 40 attempted, not "8 of unknown"
    assert m["email_send_ready_of_attempted"] == 8 / 40


def test_minimum_pilot_is_not_capacity() -> None:
    assert MINIMUM_PILOT_ACCEPTANCE_SAMPLE == 50
    assert_no_send_ready_hard_cap(None)
    assert_no_send_ready_hard_cap(200, context="smoke batch")
    with pytest.raises(ValueError, match="Refusing operational hard cap"):
        assert_no_send_ready_hard_cap(50, context="EMAIL_SEND_READY reservoir")
