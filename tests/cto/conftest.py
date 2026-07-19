"""Shared fixtures for CTO Autopilot tests."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def cto_repo(tmp_path: Path) -> Path:
    """Minimal repo layout with CTO assets copied from project."""
    root = tmp_path / "repo"
    root.mkdir()
    # package path: import from real project
    proj = Path(__file__).resolve().parents[2]
    # copy .cto
    shutil.copytree(proj / ".cto", root / ".cto")
    (root / "config").mkdir()
    (root / "scripts" / "cto").mkdir(parents=True)
    (root / "output" / "cto" / "current").mkdir(parents=True)
    (root / "output" / "cto" / "cycles").mkdir(parents=True)
    (root / "DOD.md").write_text(
        "# DoD\n\n- [x] done item\n- [ ] open item one\n- [ ] open item two BLOCKED external\n",
        encoding="utf-8",
    )
    (root / "extra-consultoria-plano-executivo.html").write_text(
        "<!doctype html><html><body><h1>Exec</h1></body></html>\n",
        encoding="utf-8",
    )
    # git init for branch/diff checks
    import subprocess

    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "add", "DOD.md", ".cto", "extra-consultoria-plano-executivo.html"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "feat/test"], cwd=root, check=True, capture_output=True)
    return root


@pytest.fixture
def sample_decision() -> dict:
    return {
        "schema_version": "1.0",
        "decision_id": "dec-test-1",
        "cycle_id": "cyc-test-1",
        "decision": "EXECUTE",
        "objective": "Implement unit test scaffolding for CTO",
        "issue_number": 1,
        "work_id": "cto-autopilot-infra",
        "candidate_id": None,
        "strategic_reason": "Critical path infrastructure",
        "acceptance_criteria": ["tests pass", "doctor ok"],
        "required_evidence": ["pytest log"],
        "allowed_paths": ["scripts/cto/**", "tests/cto/**", "docs/ops/cto-autopilot/**"],
        "forbidden_paths": [".env"],
        "test_commands": [],
        "forbidden_actions": ["merge", "deploy", "git push"],
        "allowed_claims": [],
        "forbidden_claims": ["LOCAL_READY", "PROJECT_DONE"],
        "max_repair_attempts": 2,
        "estimated_risk": "LOW",
        "confidence": 0.9,
        "human_gate": {"required": False, "reason": None},
    }
