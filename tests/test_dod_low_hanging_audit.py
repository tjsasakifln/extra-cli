"""Harness tests for low-hanging DOD campaign — adversarial + positive."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.dod_low_hanging_audit import (
    adversarial_self_checks,
    classify_item,
    prove_coverage_item,
    run_campaign,
)

ROOT = Path(__file__).resolve().parents[1]


def _item(**kwargs):
    return {
        "id": kwargs.get("id", "DOD-test"),
        "text": kwargs.get("text", ""),
        "state": kwargs.get("state", "OPEN"),
        "dod_checked": kwargs.get("dod_checked", False),
        "section": kwargs.get("section", "sec"),
        "subsection": kwargs.get("subsection", ""),
        "location": {
            "start_line": kwargs.get("line", 100),
            "heading_path": kwargs.get("path", ["sec"]),
        },
        "needs_human_eval": kwargs.get("needs_human_eval", False),
        "needs_live_source": kwargs.get("needs_live_source", False),
    }


def test_adversarial_classification_fail_closed() -> None:
    cases = adversarial_self_checks()
    assert cases
    assert all(c["ok"] for c in cases), cases


def test_reject_already_closed() -> None:
    c = classify_item(_item(dod_checked=True, state="ACCEPTED", text="done"))
    assert c.decision == "REJECTED_NOT_LOW_HANGING"


def test_reject_human() -> None:
    c = classify_item(_item(text="validação manual registrada por Tiago."))
    assert c.decision == "REJECTED_HUMAN"


def test_reject_coverage_95() -> None:
    c = classify_item(_item(text="Cobertura operacional ≥95% (mínimo **1.039/1.093** entidades)."))
    assert c.decision == "REJECTED_NOT_LOW_HANGING"


def test_reject_commercial() -> None:
    c = classify_item(
        _item(text="A fila comercial CONFENGE deve produzir top 20 outcomes de prospecção.")
    )
    assert c.decision == "REJECTED_PARALLEL_CONFLICT"


def test_select_scope_diario() -> None:
    c = classify_item(
        _item(
            text="O projeto não contém módulo de diário de obra.",
            line=138,
            section="2.3 Escopo excluído",
            path=["2", "Escopo excluído"],
        )
    )
    assert c.decision == "SELECTED"
    assert c.family == "B_SCOPE_EXCLUDED"


def test_coverage_truth_no_average_helper() -> None:
    item = _item(
        id="DOD-rol-1-definition-of-done-5412da3ad7",
        text="A média entre as duas coberturas não é usada para mascarar uma delas.",
        line=546,
    )
    cand = classify_item(item)
    assert cand.decision == "SELECTED"
    proof = prove_coverage_item(item, cand)
    assert proof.status == "PROVEN"


def test_coverage_truth_data_presence_not_coverage() -> None:
    item = _item(
        id="DOD-rol-1-definition-of-done-0c828cadb4",
        text="`data_presence` nunca é chamada de cobertura.",
        line=558,
    )
    cand = classify_item(item)
    proof = prove_coverage_item(item, cand)
    assert proof.status == "PROVEN"


def test_campaign_run_does_not_mutate_dod(tmp_path: Path) -> None:
    out = tmp_path / "out"
    dod_before = (ROOT / "DOD.md").read_bytes()
    result = run_campaign(ROOT, out)
    dod_after = (ROOT / "DOD.md").read_bytes()
    assert dod_before == dod_after
    assert result.get("mutated_dod") is False
    assert result.get("called_accept") is False
    assert (out / "candidate-matrix.json").exists()
    assert (out / "result.json").exists()
    assert (out / "acceptance-matrix.json").exists()
    data = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert data["proven"] >= 1
    # no forbidden accepts
    matrix = json.loads((out / "candidate-matrix.json").read_text(encoding="utf-8"))
    for c in matrix["candidates"]:
        if c["decision"] == "SELECTED":
            assert "≥95%" not in c["text"]
            # commercial queue items must not be selected
            assert "top 20" not in c["text"].lower()
    # per-item proofs exist and item_ids unique
    proofs = list((out / "proofs").glob("*.json"))
    assert len(proofs) >= data["proven"]
    ids = []
    for p in proofs:
        pdata = json.loads(p.read_text(encoding="utf-8"))
        if pdata.get("status") == "PROVEN":
            ids.append(pdata["item_id"])
    assert len(ids) == len(set(ids))
    assert len(ids) == data["proven"]
