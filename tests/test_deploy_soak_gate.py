"""Tests for the fail-closed deploy/soak gate (#248)."""

from __future__ import annotations

from scripts.ops.deploy_soak_gate import (
    FORBIDDEN_CLAIMS,
    PENDING_HUMAN,
    command_is_masked,
    decide_deploy,
    evaluate_preflight,
    sha_matches,
)


def _ok_kwargs(**overrides):
    kwargs = {
        "test_exit": 0,
        "crawl_exit": 0,
        "commands": ["pytest tests/ -q", "python -m scripts.crawl.monitor --source pncp --mode smoke"],
        "implanted_sha": "abc123def",
        "approved_sha": "abc123def",
        "pilot_proven": {"pagination", "dedup", "raw", "documents", "replay"},
        "leases_recovered": True,
        "jobs_recovered": True,
        "backup_restore": True,
        "freshness_ok": True,
        "soak_days": 7,
    }
    kwargs.update(overrides)
    return kwargs


def test_masked_pytest_or_true_aborts_deploy() -> None:
    assert command_is_masked("pytest tests/ || true") is True
    gate = evaluate_preflight(test_exit=0, crawl_exit=0, commands=["pytest || true"])
    assert gate.passed is False
    decision = decide_deploy(**_ok_kwargs(commands=["pytest tests/ || true"]))
    assert decision.abort is True
    assert any("masked_failure" in r for r in decision.reasons)


def test_failed_test_or_crawl_aborts() -> None:
    tests = decide_deploy(**_ok_kwargs(test_exit=1))
    assert tests.abort is True
    assert any("test_exit" in r for r in tests.reasons)
    crawl = decide_deploy(**_ok_kwargs(crawl_exit=2))
    assert crawl.abort is True


def test_sha_implanted_must_equal_ci_approved() -> None:
    assert sha_matches("ABC", "abc") is True
    mismatch = decide_deploy(**_ok_kwargs(implanted_sha="deadbeef", approved_sha="cafebabe"))
    assert mismatch.abort is True
    assert any("sha:" in r for r in mismatch.reasons)


def test_pilot_requires_pagination_dedup_raw_documents_replay() -> None:
    missing = decide_deploy(**_ok_kwargs(pilot_proven={"pagination", "dedup"}))
    assert missing.abort is True
    assert "documents" in missing.reasons[0] or any("pilot" in r for r in missing.reasons)


def test_reboot_and_soak_are_required() -> None:
    reboot = decide_deploy(**_ok_kwargs(leases_recovered=False))
    assert reboot.abort is True
    soak = decide_deploy(**_ok_kwargs(soak_days=3))
    assert soak.abort is True
    freshness = decide_deploy(**_ok_kwargs(freshness_ok=False))
    assert freshness.abort is True


def test_state_stays_pending_human_and_never_claims_vps_operational() -> None:
    decision = decide_deploy(**_ok_kwargs(), requested_claims=["VPS_OPERATIONAL"])
    assert decision.state == PENDING_HUMAN
    assert "VPS_OPERATIONAL" in FORBIDDEN_CLAIMS
    assert decision.abort is True
    assert any("forbidden_claim" in r for r in decision.reasons)
    clean = decide_deploy(**_ok_kwargs())
    assert clean.state == PENDING_HUMAN
    assert clean.abort is False
    assert clean.claims == []
    payload = clean.as_dict()
    assert payload["state"] == PENDING_HUMAN
    assert "VPS_OPERATIONAL" not in payload["claims"]
