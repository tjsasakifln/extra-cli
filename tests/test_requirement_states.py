"""Tests for DoD requirement states (aplicabilidade e bloqueio)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.requirement_states import (
    RequirementRecord,
    RequirementStateError,
    coerce_absence_to_zero_forbidden,
    field_absence_status,
    gate_counts,
    is_unchecked_non_accepted,
    make_blocked,
    make_not_applicable,
    make_partial,
    parse_dod_checkbox_items,
    reconstruct,
    seed_canonical_examples,
    validate_not_applicable,
    validate_record,
)


def test_unchecked_partial_is_not_accepted() -> None:
    rec = make_partial("x", "item", "half done")
    assert rec.state == "PARTIAL"
    assert rec.dod_checkbox == "[ ]"
    assert is_unchecked_non_accepted(rec) is True
    assert rec.is_gate_accepted() is False


def test_partial_cannot_be_checked() -> None:
    rec = RequirementRecord(
        item_id="y",
        title="t",
        state="PARTIAL",
        dod_checkbox="[x]",
    )
    errs = validate_record(rec)
    assert any("PARTIAL" in e for e in errs)


def test_blocked_requires_owner_cause_next_test() -> None:
    with pytest.raises(RequirementStateError):
        make_blocked("b", "t", owner="", cause="c", next_test="n")
    rec = make_blocked(
        "b",
        "t",
        owner="Tiago",
        cause="external",
        next_test="retry later",
    )
    assert rec.state == "BLOCKED"
    assert rec.is_gate_accepted() is False


def test_not_applicable_requires_basis_justification_date_evidence() -> None:
    with pytest.raises(RequirementStateError):
        make_not_applicable(
            "na",
            "t",
            basis="invalid",
            justification="j",
            date="2026-07-18",
            evidence=["e"],
        )
    with pytest.raises(RequirementStateError):
        make_not_applicable(
            "na",
            "t",
            basis="scope_decision_tiago",
            justification="",
            date="2026-07-18",
            evidence=["e"],
        )
    rec = make_not_applicable(
        "na",
        "t",
        basis="conditional_wording",
        justification="Redação condicional permite NA neste caso de teste.",
        date="2026-07-18",
        evidence=["docs/ops/session-test"],
    )
    assert validate_not_applicable(rec) == []
    assert rec.is_gate_accepted() is True


def test_field_absence_never_zero_or_done() -> None:
    assert field_absence_status(
        field_name="valor", source_consulted=True, value_present=False
    ) == "SOURCE_UNAVAILABLE"
    assert field_absence_status(
        field_name="valor", source_consulted=False, value_present=False
    ) == "NOT_READY"
    with pytest.raises(RequirementStateError):
        coerce_absence_to_zero_forbidden(0)


def test_gates_only_done_and_legitimate_na() -> None:
    records = [
        make_partial("p", "partial", "note"),
        make_blocked("b", "blocked", owner="o", cause="c", next_test="n"),
        make_not_applicable(
            "na",
            "na",
            basis="scope_decision_tiago",
            justification="out of scope demo",
            date="2026-07-18",
            evidence=["e"],
        ),
        RequirementRecord(
            item_id="d",
            title="done",
            state="DONE",
            dod_checkbox="[x]",
            evidence=["pytest"],
        ),
        RequirementRecord(
            item_id="bad-na",
            title="bad",
            state="NOT_APPLICABLE",
            dod_checkbox="[ ]",
            # missing justification/date/evidence/basis
        ),
        RequirementRecord(
            item_id="bad-done",
            title="unchecked done",
            state="DONE",
            dod_checkbox="[ ]",
            evidence=["pytest"],
        ),
    ]
    g = gate_counts(records)
    # DONE + legitimate NA = 2; bad NA and unchecked DONE not accepted
    assert g["gate_accepted"] == 2
    assert g["illegitimate_not_applicable"] == 1
    assert g["illegitimate_done"] == 1
    assert g["by_state"]["PARTIAL"] == 1
    assert g["by_state"]["BLOCKED"] == 1


def test_is_gate_accepted_rejects_illegitimate_na() -> None:
    bad = RequirementRecord(
        item_id="bad-na2",
        title="bad",
        state="NOT_APPLICABLE",
        dod_checkbox="[ ]",
    )
    assert bad.is_gate_accepted() is False
    good = make_not_applicable(
        "na2",
        "ok",
        basis="conditional_wording",
        justification="wording allows",
        date="2026-07-18",
        evidence=["e"],
    )
    assert good.is_gate_accepted() is True


def test_coerce_rejects_string_zero_and_none() -> None:
    with pytest.raises(RequirementStateError):
        coerce_absence_to_zero_forbidden("0")
    with pytest.raises(RequirementStateError):
        coerce_absence_to_zero_forbidden(None)


def test_parse_dod_and_reconstruct(tmp_path: Path) -> None:
    dod = tmp_path / "DOD.md"
    dod.write_text(
        "# X\n\n### Estados\n\n- [ ] aberto\n- [x] fechado com evidência: pytest\n",
        encoding="utf-8",
    )
    items = parse_dod_checkbox_items(dod.read_text(encoding="utf-8"))
    assert len(items) == 2
    assert items[0]["checked"] is False
    assert items[1]["checked"] is True

    ledger = tmp_path / "ledger.json"
    seed_canonical_examples(ledger)
    report = reconstruct(ledger_path=ledger, dod_path=dod)
    assert report["ok"] is True
    assert report["policy"]["reconstructable_without_chat"] is True
    assert report["ledger_records"] >= 5
    assert (ledger).exists()
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert data["version"] == "1.0.0"


def test_blocked_remains_visible_in_gate_non_accepted() -> None:
    rec = make_blocked(
        "blk",
        "external",
        owner="ops",
        cause="no creds",
        next_test="wait",
    )
    g = gate_counts([rec])
    assert g["gate_non_accepted"] == 1
    assert g["gate_accepted"] == 0
