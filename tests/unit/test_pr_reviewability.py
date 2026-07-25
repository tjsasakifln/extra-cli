"""Tests for PR reviewability gate (real shipped entrypoint)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.check_pr_reviewability import (
    MAX_FILES_READY,
    classify_path,
    evaluate,
    main,
)


def test_limits_match_policy() -> None:
    assert MAX_FILES_READY == 60


def test_classify_buckets() -> None:
    assert "migration" in classify_path("db/migrations/060_x.sql")
    assert "ci" in classify_path(".github/workflows/ci.yml")
    assert "runtime" in classify_path("scripts/national_intel/cli.py")
    assert "commercial" in classify_path(
        "scripts/ops/client_ready_consulting_cycle.py"
    )


def test_ready_too_many_files(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    paths = [f"scripts/f{i}.py" for i in range(65)]
    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(base="origin/main", draft=False, paths=paths)
    assert any(v["reason"] == "too_many_files" for v in viol)


def test_draft_allows_size(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    paths = [f"scripts/f{i}.py" for i in range(65)]
    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(base="origin/main", draft=True, paths=paths)
    assert not any(v["reason"] == "too_many_files" for v in viol)


def test_binary_blocked_even_in_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=True,
        paths=["artifacts/campaigns/X/report.pdf", "scripts/ok.py"],
    )
    assert any(v["reason"] == "binary_or_generated_in_diff" for v in viol)


def test_multi_capability_mix(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=[
            "db/migrations/060_x.sql",
            ".github/workflows/ci.yml",
            "scripts/national_intel/cli.py",
            "scripts/ops/client_ready_consulting_cycle.py",
        ],
    )
    assert any(v["reason"] == "multi_capability_mix" for v in viol)


def test_body_sha_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body="CI SHA: abcdef1234567890\nStatus PASS",
        head_sha="ffffffffffffffffffffffffffffffffffffffff",
        required_checks_present=True,
    )
    assert any(v["reason"] == "body_ci_sha_mismatch" for v in viol)


def test_declared_pass_without_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body="Status: PASS — all green",
        head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        required_checks_present=False,
    )
    assert any(v["reason"] == "declared_pass_without_gates" for v in viol)


def test_main_with_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    rc = main(["--paths", "scripts/a.py", "--draft"])
    assert rc == 0


def test_exception_waives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    exc = {
        "active": {
            "reason": "coordinated migration wave",
            "owner": "tiago",
            "deadline": "2026-08-01",
            "approved_by": "tiago",
            "waives": ["too_many_files"],
        }
    }
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "pr-reviewability-exceptions.json").write_text(
        json.dumps(exc), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    paths = [f"scripts/f{i}.py" for i in range(65)]
    viol = evaluate(base="origin/main", draft=False, paths=paths)
    assert not any(v["reason"] == "too_many_files" for v in viol)
