"""Tests for #381 versioned ICP / reachability denominator."""

from __future__ import annotations

import pytest

from scripts.market_penetration.icp_denominator import (
    AccountFact,
    PenetrationError,
    snapshot_penetration,
)


def _fact(account_id: str, **overrides: object) -> AccountFact:
    base: dict[str, object] = {
        "account_id": account_id,
        "uf": "SC",
        "has_public_portfolio": True,
        "decision_unit_known": True,
        "actionable_route": True,
        "warmbly_stage": None,
        "evidence": ("seed",),
    }
    base.update(overrides)
    return AccountFact(**base)  # type: ignore[arg-type]


def test_snapshot_is_reproducible_and_does_not_invent_tam() -> None:
    facts = (
        _fact("a1"),
        _fact("a2", decision_unit_known=False, actionable_route=False),
        _fact("a3", warmbly_stage="CONTACTED"),
        _fact("a4", warmbly_stage="PROPOSAL"),
        _fact("a5", uf="PR", evidence=("out_of_icp",)),
    )
    first = snapshot_penetration(facts, as_of="2026-08-14")
    second = snapshot_penetration(facts, as_of="2026-08-14")
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert first["denominator"]["invented_tam"] is False
    assert first["counts"]["X_icp"] == 4
    assert first["counts"]["Y_reachable"] == 3  # a1 route + a3 contacted + a4 proposal
    assert first["counts"]["Z_contacted"] == 1
    assert first["counts"]["P_proposals"] == 1
    assert first["counts"]["UNKNOWN"] == 1
    assert "a5" in first["uncaptured_account_ids"]
    assert first["as_of"] == "2026-08-14"
    assert first["rules_version"]


def test_unknown_stays_visible_without_evidence() -> None:
    snap = snapshot_penetration(
        (_fact("ghost", evidence=()),),
        as_of="2026-08-14",
    )
    assert snap["by_stage"]["UNKNOWN"] == 1
    assert snap["counts"]["X_icp"] == 0
    assert "ghost" in snap["uncaptured_account_ids"]


def test_warmbly_stage_is_consumed_not_rederived() -> None:
    # extra-cli would only know ACTIONABLE_ROUTE; Warmbly says CLIENT.
    snap = snapshot_penetration(
        (_fact("c1", actionable_route=True, warmbly_stage="CLIENT"),),
        as_of="2026-08-14",
    )
    assert snap["by_stage"]["CLIENT"] == 1
    assert snap["by_stage"]["ACTIONABLE_ROUTE"] == 0
    assert snap["warmbly_authoritative_from"] == "CONTACTED"


def test_duplicate_account_and_missing_as_of_fail_closed() -> None:
    with pytest.raises(PenetrationError, match="duplicate_account"):
        snapshot_penetration((_fact("x"), _fact("x")), as_of="2026-08-14")
    with pytest.raises(PenetrationError, match="as_of"):
        snapshot_penetration((_fact("x"),), as_of="")
