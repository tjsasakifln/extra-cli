"""Tests for generated artifacts policy gate (real shipped entrypoint)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.check_generated_artifacts_policy import (
    ALWAYS_ALLOW_NAMES,
    classify_violation,
    evaluate,
    main,
)


def test_always_allow_names_include_acceptance_freeze() -> None:
    assert "user-acceptance.json" in ALWAYS_ALLOW_NAMES
    assert "checksums.json" in ALWAYS_ALLOW_NAMES


def test_banned_pdf_under_campaign() -> None:
    reason = classify_violation(
        "artifacts/campaigns/FOO/pack/report.pdf",
        size=12_000,
        exceptions={},
    )
    assert reason is not None
    assert "banned_suffix" in reason


def test_small_manifest_allowed() -> None:
    reason = classify_violation(
        "artifacts/campaigns/FOO/manifest.json",
        size=2048,
        exceptions={},
    )
    assert reason is None


def test_large_campaign_json_blocked() -> None:
    reason = classify_violation(
        "artifacts/campaigns/FOO/monthly/monthly-monitor-live.json",
        size=5_000_000,
        exceptions={},
    )
    assert reason is not None


def test_pack_rc_tree_banned() -> None:
    reason = classify_violation(
        "artifacts/campaigns/FOO/pack-rc/deliverable_a.json",
        size=1000,
        exceptions={},
    )
    assert reason is not None


def test_evaluate_finds_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # drive evaluate() with explicit paths; size via monkeypatch of _file_size
    import scripts.ops.check_generated_artifacts_policy as mod

    monkeypatch.setattr(mod, "_file_size", lambda p: 900_000 if p.endswith(".pdf") else 100)
    viol = evaluate(
        [
            "artifacts/campaigns/X/pack/out.pdf",
            "artifacts/campaigns/X/manifest.json",
        ]
    )
    assert any(v["path"].endswith(".pdf") for v in viol)
    assert not any(str(v["path"]).endswith("manifest.json") for v in viol)


def test_main_fails_on_prohibited_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_generated_artifacts_policy as mod

    monkeypatch.setattr(mod, "_git_diff_names", lambda base: ["artifacts/campaigns/X/a.pdf"])
    monkeypatch.setattr(mod, "_file_size", lambda p: 50_000)
    rc = main([])
    assert rc == 1


def test_main_passes_on_small_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.ops.check_generated_artifacts_policy as mod

    monkeypatch.setattr(
        mod,
        "_git_diff_names",
        lambda base: ["artifacts/campaigns/X/user-acceptance.json"],
    )
    monkeypatch.setattr(mod, "_file_size", lambda p: 1500)
    rc = main([])
    assert rc == 0


def test_main_json_report(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import scripts.ops.check_generated_artifacts_policy as mod

    monkeypatch.setattr(mod, "_git_diff_names", lambda base: ["docs/generated-artifacts-policy.md"])
    monkeypatch.setattr(mod, "_file_size", lambda p: 100)
    rc = main(["--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
