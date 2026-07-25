"""Commercial state transitions and review validation."""

from __future__ import annotations

import pytest

from scripts.commercial_leads.review import validate_transition


def test_valid_new_to_reviewed():
    validate_transition("NEW", "REVIEWED")


def test_valid_new_to_do_not_contact():
    validate_transition("NEW", "DO_NOT_CONTACT")


def test_invalid_do_not_contact_exit():
    with pytest.raises(ValueError, match="do_not_contact"):
        validate_transition("DO_NOT_CONTACT", "QUALIFIED")


def test_invalid_won_to_new():
    with pytest.raises(ValueError, match="invalid_transition"):
        validate_transition("WON", "NEW")


def test_disqualified_can_return_to_reviewed():
    validate_transition("DISQUALIFIED", "REVIEWED")


def test_proposal_to_won():
    validate_transition("PROPOSAL", "WON")
