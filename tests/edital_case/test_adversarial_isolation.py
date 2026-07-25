"""Adversarial checks that exercise shipped isolation and analysis failure modes."""

from __future__ import annotations

import subprocess

import pytest

from scripts.edital_case.analyze import check_consistency, detect_missing_documents
from scripts.edital_case.isolation import IsolationError, enforce_isolation, path_is_allowed


def test_primary_checkout_paths_denied() -> None:
    assert not path_is_allowed("DOD.md")
    assert not path_is_allowed("scripts/workspace/cli.py")
    assert not path_is_allowed("scripts/workspace/actions.py")
    assert not path_is_allowed("Makefile")
    assert not path_is_allowed("db/migrations/061_x.sql")
    assert not path_is_allowed("artifacts/campaigns/EXTRA-LIVE-CONSULTING-PACK-01/x.json")


def test_enforce_isolation_campaign_or_refuses_elsewhere() -> None:
    """On campaign worktree: isolation passes. On CI detached HEAD / other branch: refuses.

    Full suite in GitHub Actions checks out a detached SHA — enforce_isolation must
    fail closed there (not require campaign worktree for the whole repo suite).
    """
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
    ).strip()
    from pathlib import Path

    lock = (
        Path(__file__).resolve().parents[2]
        / "artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01/worktree-lock.json"
    )
    if branch and "edital-technical-triage" in branch and lock.is_file():
        ctx = enforce_isolation()
        assert "edital" in ctx.branch
        assert ctx.production_touched is False
        assert ctx.database_used is False
        return

    with pytest.raises(IsolationError):
        enforce_isolation()


def test_false_missing_annex_attack() -> None:
    """Attack: present TR/ETP must not be marked MISSING."""
    docs = [
        {
            "document_id": "doc-001",
            "original_name": "edital.pdf",
            "classification": {"result": "EDITAL"},
            "supported": True,
            "blocks": [
                {
                    "document_id": "doc-001",
                    "page": 2,
                    "text": "Anexos: Termo de Referência; ESTUDO TÉCNICO PRELIMINAR; Planilha Orçamentária",
                    "locator": "page:2",
                }
            ],
            "text": "Anexos: Termo de Referência; ESTUDO TÉCNICO PRELIMINAR; Planilha Orçamentária",
        },
        {
            "document_id": "doc-002",
            "original_name": "03_TR.pdf",
            "classification": {"result": "TERMO_DE_REFERENCIA"},
            "supported": True,
            "blocks": [
                {
                    "document_id": "doc-002",
                    "page": 1,
                    "text": "TERMO DE REFERÊNCIA",
                    "locator": "page:1",
                }
            ],
            "text": "TERMO DE REFERÊNCIA",
        },
        {
            "document_id": "doc-003",
            "original_name": "02_ETP.pdf",
            "classification": {"result": "ESTUDO_TECNICO_PRELIMINAR"},
            "supported": True,
            "blocks": [
                {
                    "document_id": "doc-003",
                    "page": 1,
                    "text": "ESTUDO TÉCNICO PRELIMINAR",
                    "locator": "page:1",
                }
            ],
            "text": "ESTUDO TÉCNICO PRELIMINAR",
        },
    ]
    out = detect_missing_documents({"documents": docs})
    for r in out["references"]:
        if r["expected_type"] in {"TERMO_DE_REFERENCIA", "ESTUDO_TECNICO_PRELIMINAR"}:
            assert r["status"] == "PRESENT", r
        if r["expected_type"] == "PLANILHA_ORCAMENTARIA":
            assert r["status"] == "MISSING"


def test_format_conflict_not_confirmed() -> None:
    docs = [
        {
            "document_id": "a",
            "original_name": "edital.pdf",
            "classification": {"result": "EDITAL"},
            "supported": True,
            "text": "Prefeitura Municipal de Laguna\nCritério de julgamento: MAIOR DESCONTO",
            "blocks": [],
        },
        {
            "document_id": "b",
            "original_name": "tr.pdf",
            "classification": {"result": "TERMO_DE_REFERENCIA"},
            "supported": True,
            "text": "Prefeitura Municipal de \nLaguna\nCritério: maior desconto",
            "blocks": [],
        },
    ]
    out = check_consistency({"documents": docs})
    assert out.get("confirmed_conflict_count", 0) == 0
    for inc in out["inconsistencies"]:
        assert inc["class"] in {"FORMAT_VARIATION", "NOT_COMPARABLE", "POSSIBLE_CONFLICT"}
