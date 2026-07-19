"""Sealed canary package integrity checks."""
from __future__ import annotations

import json

from scripts.cto.canary_integrity import (
    FORBIDDEN_META_SOURCES,
    decision_content_sha256,
    validate_sealed_canary_package,
)
from scripts.cto.paths import cycles_dir


def test_decision_sha256_stable_ignores_meta():
    d1 = {
        "decision": "EXECUTE",
        "test_commands": ["grep -qi canary docs/ops/cto-autopilot/canary-proof.md"],
        "required_evidence": ["docs/ops/cto-autopilot/canary-proof.md"],
        "_meta": {"source": "cli canary-live", "noise": 1},
    }
    d2 = {
        **{k: v for k, v in d1.items() if k != "_meta"},
        "_meta": {"source": "cli canary-live", "noise": 999},
    }
    assert decision_content_sha256(d1) == decision_content_sha256(d2)
    d3 = {**d1, "test_commands": ["other"]}
    assert decision_content_sha256(d1) != decision_content_sha256(d3)


def test_integrity_rejects_reconcile_meta(cto_repo, tmp_path):
    root = cto_repo
    cycle_id = "canary-live-test-bad"
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True)
    decision = {
        "schema_version": "1.0",
        "decision_id": "dec-x",
        "cycle_id": cycle_id,
        "decision": "EXECUTE",
        "test_commands": ["grep -qi canary docs/ops/cto-autopilot/canary-proof.md"],
        "required_evidence": ["docs/ops/cto-autopilot/canary-proof.md"],
        "allowed_paths": ["docs/ops/cto-autopilot/canary-proof.md"],
        "_meta": {"source": "reconcile-single-decision", "reconciled_at_utc": "now"},
    }
    sha = decision_content_sha256(decision)
    (cdir / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
    (cdir / "execution.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "mock": False,
                "dry_run": False,
                "decision_sha256": sha,
                "grok_auth": {"source": "XAI_API_KEY", "staged_auth_file": False},
                "isolated_home": str(tmp_path / "home"),
                "base_commit": "abc",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "home").mkdir()
    (cdir / "execute_prompt.md").write_text(
        "grep -qi canary docs/ops/cto-autopilot/canary-proof.md\n"
        "docs/ops/cto-autopilot/canary-proof.md\n",
        encoding="utf-8",
    )
    out = validate_sealed_canary_package(cycle_id, root=root)
    assert out["ok"] is False
    assert any("no_reconcile_meta" in e for e in out["errors"])
    assert "reconcile-single-decision" in FORBIDDEN_META_SOURCES
