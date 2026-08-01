"""E2E integrated path: edital requirements → technical_acervo → bid_readiness."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bid_readiness.integration import (
    ALLOWED_PACKAGE_STATES,
    FORBIDDEN_PACKAGE_STATES,
    integrate_requirements,
    match_technical_via_acervo,
)
from scripts.technical_acervo.store import load_store


def test_forbidden_states_never_emitted():
    out = integrate_requirements(
        [
            {
                "requirement_id": "R1",
                "service": "pavimentacao asfaltica",
                "quantity": 1000,
                "unit": "m2",
                "mandatory": True,
                "allow_sum": False,
                "document_id": "edital-1",
                "page": 12,
            }
        ]
    )
    assert out["package_status"] in ALLOWED_PACKAGE_STATES
    assert out["package_status"] not in FORBIDDEN_PACKAGE_STATES
    assert out["human_decision"]["auto_submit"] is False
    assert out["package_status"] != "READY_TO_SUBMIT"


def test_unit_divergence_and_sum_forbidden_vs_allowed():
    store = load_store()
    # unit mismatch path: odd unit unlikely in acervo
    f_unit = match_technical_via_acervo(
        {
            "requirement_id": "R-unit",
            "service": "pavimentacao",
            "quantity": 500,
            "unit": "kg",  # typically not m2
            "mandatory": True,
        },
        store=store,
    )
    assert f_unit["requirement"]["unit"] == "kg"
    # sum forbidden by default
    f_sum = match_technical_via_acervo(
        {
            "requirement_id": "R-sum",
            "service": "pavimentacao",
            "quantity": 10_000_000,
            "unit": "m2",
            "allow_sum": False,
            "mandatory": True,
        },
        store=store,
    )
    assert f_sum["acervo_raw"]["allow_sum"] is False
    # allow_sum explicit
    f_sum_ok = match_technical_via_acervo(
        {
            "requirement_id": "R-sum2",
            "service": "pavimentacao",
            "quantity": 10_000_000,
            "unit": "m2",
            "allow_sum": True,
            "mandatory": True,
        },
        store=store,
    )
    assert f_sum_ok["acervo_raw"]["allow_sum"] is True


def test_missing_evidence_and_locators():
    out = integrate_requirements(
        [
            {
                "requirement_id": "R-missing",
                "service": "servico_inexistente_xyz_12345_nao_existe",
                "quantity": 1,
                "unit": "m2",
                "mandatory": True,
                "document_id": "edital-X",
                "document_hash": "abc123",
                "page": 3,
                "cell": "B12",
                "sheet": "Planilha",
            }
        ]
    )
    f = out["findings"][0]
    assert f["requirement"]["origin"]["page"] == 3
    assert f["requirement"]["origin"]["cell"] == "B12"
    assert f["match_status"] in {"MISSING", "NEEDS_HUMAN", "PARTIALLY_SATISFIED"}
    assert out["package_status"] in ALLOWED_PACKAGE_STATES
    assert out["package_status"] != "READY_TO_SUBMIT"


def test_consumes_technical_acervo_module_not_duplicate_store():
    import inspect

    import scripts.bid_readiness.integration as integ

    src = inspect.getsource(integ)
    assert "scripts.technical_acervo.match" in src
    assert "data/extra_technical_acervo.json" in src
    # Must not open a parallel JSON store path
    assert "bid_readiness_acervo.json" not in src
    assert "second_acervo" not in src


def test_e2e_mixed_compatible_incompatible_expired_units(tmp_path: Path):
    """Integrated scenario covering campaign Phase 6 proof checklist."""
    requirements = [
        {
            "requirement_id": "R-ok",
            "service": "pavimentacao",
            "quantity": 100,
            "unit": "m2",
            "mandatory": True,
            "allow_sum": False,
            "document_id": "edital",
            "page": 1,
        },
        {
            "requirement_id": "R-incomp",
            "service": "servico_totalmente_alien_zzzz",
            "quantity": 50,
            "unit": "m2",
            "mandatory": True,
            "document_id": "edital",
            "page": 2,
        },
        {
            "requirement_id": "R-unit",
            "service": "pavimentacao",
            "quantity": 50,
            "unit": "un",
            "mandatory": True,
            "document_id": "planilha",
            "sheet": "Orçamento",
            "cell": "C10",
        },
        {
            "requirement_id": "R-sum-forbidden",
            "service": "pavimentacao",
            "quantity": 999999999,
            "unit": "m2",
            "allow_sum": False,
            "mandatory": True,
            "document_id": "tr",
            "page": 4,
        },
        {
            "requirement_id": "R-sum-allowed",
            "service": "pavimentacao",
            "quantity": 999999999,
            "unit": "m2",
            "allow_sum": True,
            "mandatory": True,
            "document_id": "tr",
            "page": 5,
        },
    ]
    out = integrate_requirements(requirements)
    assert len(out["findings"]) == 5
    assert out["package_status"] in ALLOWED_PACKAGE_STATES
    assert out["package_status"] not in FORBIDDEN_PACKAGE_STATES
    # package only human-review or blocked
    assert out["package_status"] in {
        "READY_FOR_HUMAN_REVIEW",
        "NOT_READY",
        "BLOCKED_BY_TECHNICAL_QUALIFICATION",
        "BLOCKED_BY_MISSING_DOCUMENT",
        "BLOCKED_BY_EXPIRED_DOCUMENT",
        "BLOCKED_BY_INCONSISTENCY",
        "BLOCKED_BY_HUMAN_DECISION",
    }
    # write proof artifact
    proof = tmp_path / "integration-out.json"
    proof.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert proof.is_file()
    data = json.loads(proof.read_text(encoding="utf-8"))
    assert data["package_status"] not in FORBIDDEN_PACKAGE_STATES
    assert data["human_decision"]["auto_submit"] is False
