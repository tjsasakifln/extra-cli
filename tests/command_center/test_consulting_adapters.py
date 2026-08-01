"""Allowlisted consulting adapters for edital/budget/acervo/bid readiness."""

from pathlib import Path

from scripts.command_center.adapters import get_adapter, list_adapter_workflow_ids
from scripts.command_center.capabilities.definitions import all_capabilities


def test_consulting_adapters_registered():
    ids = set(list_adapter_workflow_ids())
    for wid in (
        "workflow.edital_case",
        "workflow.budget_audit",
        "workflow.technical_acervo",
        "workflow.bid_readiness",
    ):
        assert wid in ids
        assert get_adapter(wid) is not None


def test_consulting_capabilities_registered():
    caps = {c.id for c in all_capabilities()}
    for cid in (
        "consulting.edital_case.run",
        "consulting.budget_audit.run",
        "consulting.technical_acervo.match",
        "consulting.bid_readiness.run",
        "extra.weekly.run",
    ):
        assert cid in caps


def test_acervo_match_argv_allowlisted():
    ad = get_adapter("workflow.technical_acervo")
    argv = ad.build_argv({"service": "pavimentacao", "quantity": 10, "unit": "m2"}, out_dir=Path("."))
    assert argv[0].endswith("python") or "python" in argv[0]
    assert "-m" in argv
    assert "scripts.technical_acervo" in argv
    assert "--service" in argv
    assert "pavimentacao" in argv
    # no shell metacharacters
    joined = " ".join(argv)
    assert ";" not in joined and "|" not in joined


def test_bid_readiness_preflight_mentions_no_ready_to_submit():
    ad = get_adapter("workflow.bid_readiness")
    pf = ad.preflight({}, out_dir=Path("."))
    blob = " ".join(pf.limitations)
    assert "READY_TO_SUBMIT" in blob or "Nunca" in blob or "nunca" in blob.lower()
