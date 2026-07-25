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


def test_prose_mention_of_pass_is_not_status_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: describing the gate must not trip declared_pass_without_gates."""
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body=(
            "required_checks_present fail-closed when body declares PASS\n"
            "awaiting canonical CI\n"
        ),
        head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        required_checks_present=None,
    )
    assert not any(v["reason"] == "declared_pass_without_gates" for v in viol)


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


def test_extract_claimed_shas_markdown_bold_head_sha() -> None:
    """Regression: #136 body format **HEAD SHA:** `...` must be detected."""
    from scripts.ops.check_pr_reviewability import extract_claimed_head_shas

    body = (
        "## Exact HEAD under test\n\n"
        "- **HEAD SHA:** `5f5111885a3ff9fa205c3a39ee28fab039c2e67d`\n"
        "- **Base:** `main` @ `e985088dbbac8de88ddbdabbebf889e4e17c4764`\n"
    )
    claimed = extract_claimed_head_shas(body)
    assert claimed == ["5f5111885a3ff9fa205c3a39ee28fab039c2e67d"]


def test_body_sha_mismatch_markdown_format_like_pr136(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    body = (
        "## Exact HEAD under test\n\n"
        "- **HEAD SHA:** `5f5111885a3ff9fa205c3a39ee28fab039c2e67d`\n"
        "- **Base:** `main` @ `e985088dbbac8de88ddbdabbebf889e4e17c4764`\n\n"
        "## Validation\n\n"
        "- [x] local gates PASS\n"
    )
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/ops/check_pr_reviewability.py"],
        body=body,
        head_sha="e1ecc04b9245cd78dfd275c5e37e3c982c4e9d66",
        required_checks_present=True,
    )
    assert any(v["reason"] == "body_ci_sha_mismatch" for v in viol)
    mismatch = next(v for v in viol if v["reason"] == "body_ci_sha_mismatch")
    assert str(mismatch["claimed"]).startswith("5f51118")


def test_body_sha_match_markdown_when_head_correct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    head = "e1ecc04b9245cd78dfd275c5e37e3c982c4e9d66"
    body = f"- **HEAD SHA:** `{head}`\n"
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body=body,
        head_sha=head,
        required_checks_present=True,
    )
    assert not any(v["reason"] == "body_ci_sha_mismatch" for v in viol)


def test_declared_pass_fails_when_required_checks_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PASS claims are fail-closed unless required_checks_present is True."""
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body="Status: PASS — all green",
        head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        required_checks_present=None,  # unknown
    )
    assert any(v["reason"] == "declared_pass_without_gates" for v in viol)


def test_missing_required_check_names(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_pr_reviewability as mod

    monkeypatch.setattr(mod, "_load_exception", lambda: None)
    viol = evaluate(
        base="origin/main",
        draft=False,
        paths=["scripts/a.py"],
        body="CI_GREEN",
        head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        required_checks_present=True,
        required_check_names=["Lint (ruff)", "Security (bandit)"],
    )
    assert any(v["reason"] == "missing_required_checks" for v in viol)
