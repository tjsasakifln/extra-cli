"""Unit tests: AEC classification + pure snapshot reconciliation."""
from __future__ import annotations

from scripts.buyer_intel.ranking import is_aec
from scripts.lib.universe import reconcile_active_ids


def test_is_aec_positive() -> None:
    assert is_aec("Pavimentação asfáltica de vias urbanas") is True
    assert is_aec("Reforma e construção de edifício escolar") is True


def test_is_aec_negative() -> None:
    assert is_aec("Aquisição de material de expediente") is False
    assert is_aec(None) is False
    assert is_aec("") is False


def test_reconcile_fail_closed_on_partial() -> None:
    r = reconcile_active_ids(
        previously_active={"a", "b"},
        seen_in_snapshot={"a"},
        run_complete=False,
    )
    assert r["skipped"] is True
    assert r["inactivate"] == []


def test_reconcile_complete_inactivates_absent() -> None:
    r = reconcile_active_ids(
        previously_active={"a", "b"},
        seen_in_snapshot={"a", "c"},
        run_complete=True,
    )
    assert r["skipped"] is False
    assert r["inactivate"] == ["b"]
    assert r["reactivate"] == ["c"]
    assert "a" in r["remain_active"]
