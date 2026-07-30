"""Tests for EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01 core modules."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.ops.extra_actionable import (
    EXPIRED,
    INSUFFICIENT_SOURCE_EVIDENCE,
    NO_VERIFIABLE_FUTURE_DEADLINE,
    PROFILE_BLOCKED,
    REVIEW_REQUIRED,
    classify_batch,
    classify_opportunity,
)
from scripts.ops.extra_decision_review import (
    PASS_ACCEPTED,
    READY_FOR_HUMAN,
    accept_empty,
    decide,
    finalize,
    list_items,
)
from scripts.ops.extra_profile import (
    critical_pending,
    is_absent,
    stamp,
    validate_profile,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config" / "client_profiles" / "extra.yaml"


def test_profile_validate_canonical() -> None:
    result = validate_profile(PROFILE)
    assert result["ok"] is True
    assert result["stamp"]["profile_hash"]
    assert result["stamp"]["version"] is not None


def test_profile_stamp_stable() -> None:
    a = stamp(PROFILE)
    b = stamp(PROFILE)
    assert a["profile_hash"] == b["profile_hash"]
    assert a["profile_id"]


def test_absence_not_capacity() -> None:
    assert is_absent(None)
    assert is_absent("PENDING")
    assert is_absent("NOT_PROVIDED")
    assert is_absent([])
    assert not is_absent(100000.0)
    pending = critical_pending(
        {
            "capital_giro": None,
            "capacidade_garantia": None,
            "capacidade_simultanea": None,
            "cats_atestados": [],
            "margem_minima": None,
            "capacity": {"status": "PENDING"},
        }
    )
    assert "capital_giro" in pending


def _future_row(**over: object) -> dict:
    future = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    row = {
        "numero_controle_pncp": "12345678000199-1-000001/2026",
        "objeto": "pavimentacao asfaltica e drenagem urbana",
        "orgao_nome": "Prefeitura Teste",
        "status_canonico": "open",
        "data_encerramento": future,
        "source": "pncp",
        "link_edital": "https://pncp.gov.br/app/editais/12345678000199/2026/1",
        "ingested_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "valor_estimado": 500000,
    }
    row.update(over)
    return row


def test_actionable_requires_future_deadline() -> None:
    past = (datetime.now(UTC) - timedelta(days=3)).date().isoformat()
    r = classify_opportunity(_future_row(data_encerramento=past), profile_path=str(PROFILE))
    assert r.state == EXPIRED
    assert r.actionable is False


def test_actionable_missing_deadline() -> None:
    r = classify_opportunity(_future_row(data_encerramento=None), profile_path=str(PROFILE))
    assert r.state == NO_VERIFIABLE_FUTURE_DEADLINE
    assert r.actionable is False


def test_actionable_insufficient_source() -> None:
    r = classify_opportunity(
        _future_row(
            link_edital="https://pncp.gov.br/app/editais?",
            source_updated_at=None,
            ingested_at=None,
        ),
        profile_path=str(PROFILE),
    )
    assert r.actionable is False
    assert r.state in {INSUFFICIENT_SOURCE_EVIDENCE, REVIEW_REQUIRED}


def test_negative_object_profile_blocked() -> None:
    r = classify_opportunity(
        _future_row(objeto="fornecimento de medicamentos hospitalares"),
        profile_path=str(PROFILE),
    )
    assert r.actionable is False
    assert r.state in {PROFILE_BLOCKED, REVIEW_REQUIRED}


def test_batch_no_actionable_tender() -> None:
    past = (datetime.now(UTC) - timedelta(days=10)).date().isoformat()
    rows = [
        _future_row(numero_controle_pncp=f"x-{i}", data_encerramento=past) for i in range(3)
    ]
    summary = classify_batch(rows, profile_path=str(PROFILE), max_shortlist=5)
    assert summary["result"] == "NO_ACTIONABLE_TENDER"
    assert summary["shortlist_count"] == 0
    assert summary["expired"] == 3


def test_batch_shortlist_max_five() -> None:
    rows = [
        _future_row(numero_controle_pncp=f"12345678000199-1-00000{i}/2026") for i in range(8)
    ]
    summary = classify_batch(rows, profile_path=str(PROFILE), max_shortlist=5)
    # May be REVIEW_REQUIRED due to capacity pending — not false ACTIONABLE flood
    assert summary["shortlist_count"] <= 5
    assert "profile_stamp" in summary
    assert summary["profile_stamp"]["profile_hash"]


def test_review_accept_empty_and_finalize(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "shortlist.json").write_text(
        json.dumps(
            {
                "result": "NO_ACTIONABLE_TENDER",
                "shortlist": [],
                "shortlist_count": 0,
                "schema": "test",
                "profile_stamp": {"version": 3, "profile_hash": "abc"},
            }
        ),
        encoding="utf-8",
    )
    listed = list_items(run)
    assert listed["n_items"] == 0
    accept_empty(run, reason="Nenhum edital vigente no recorte", actor="tiago")
    # Without package_decision → READY_FOR_HUMAN_ACCEPTANCE (never silent PASS)
    st = finalize(run, actor="tiago", package_decision=None)
    assert st["terminal_state"] == READY_FOR_HUMAN
    st2 = finalize(run, actor="tiago", package_decision="ACCEPTED", notes="ok")
    assert st2["terminal_state"] == PASS_ACCEPTED


def test_review_decide_unknown_id_fails(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "shortlist.json").write_text(
        json.dumps(
            {
                "result": "SHORTLIST_READY",
                "shortlist": [{"opportunity_id": "only-1", "recommendation": "REVIEW"}],
                "shortlist_count": 1,
                "profile_stamp": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not in shortlist"):
        decide(run, opportunity_id="missing", decision="ACCEPT", reason="x", actor="tiago")
    decide(run, opportunity_id="only-1", decision="REJECT", reason="fora de escopo", actor="tiago")
    st = finalize(run, actor="tiago", package_decision="ACCEPTED_WITH_LIMITATIONS")
    assert st["terminal_state"] == PASS_ACCEPTED
    assert st["n_decisions"] == 1


def test_never_auto_pass_on_classify() -> None:
    rows = [_future_row()]
    summary = classify_batch(rows, profile_path=str(PROFILE))
    # classification never emits human pass states
    assert "PASS_EXTRA" not in json.dumps(summary)
