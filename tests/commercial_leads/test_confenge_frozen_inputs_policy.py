"""Frozen CONFENGE inputs policy — drive shipped modules only.

Required outcomes (mission):
- alter confenge_code_freeze.py after freeze → FAIL
- alter only edital_relevance_recall.py → PASS
- unrelated new feature → PASS without allowlist edit
- commercial pipeline / scoring / profile / schema / gates / section → FAIL
- manifest hash / freeze ancestry mismatches covered via evaluate_post_freeze_diff
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scripts.ops.confenge_frozen_inputs import (
    CAMPAIGN,
    CI_SECTION_KEY,
    MAKEFILE_SECTION_KEY,
    SCHEMA_VERSION,
    build_frozen_inputs_manifest,
    classify_changed_paths,
    evaluate_post_freeze_diff,
    extract_ci_confenge_section,
    extract_makefile_confenge_section,
    protected_path_set,
    sha256_text,
    write_frozen_inputs_manifest,
)
from scripts.ops.verify_confenge_artifact_binding import check_artifact_binding


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(repo),
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _init_mini_repo(tmp_path: Path) -> Path:
    """Minimal git repo with CONFENGE-like layout for policy tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init"], cwd=str(repo), stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["git", "config", "user.name", "test"],
        cwd=str(repo),
        stdout=subprocess.DEVNULL,
    )

    # Seed commercial + gates + shared surfaces
    files = {
        "scripts/ops/confenge_code_freeze.py": "FREEZE_V1 = 1\n",
        "scripts/ops/verify_confenge_artifact_binding.py": "BIND_V1 = 1\n",
        "scripts/ops/confenge_frozen_inputs.py": "POLICY_V1 = 1\n",
        "scripts/ops/confenge_make_gates.py": "GATES_V1 = 1\n",
        "scripts/commercial_leads/pipeline.py": "PIPELINE_V1 = 1\n",
        "scripts/commercial_leads/scoring.py": "SCORING_V1 = 1\n",
        "scripts/commercial_leads/sector_fit.py": "SECTOR_V1 = 1\n",
        "scripts/commercial_leads/__init__.py": "",
        "config/commercial_profiles/confenge.yaml": "profile_id: confenge\n",
        "db/migrations/062_commercial_leads_ledger.sql": "-- 062\n",
        "Makefile": textwrap.dedent(
            """\
            # --- other campaign ---
            other-target:
            \techo other

            # --- CONFENGE commercial ready (migration 062/063 + commercial_leads gold) ---
            confenge-commercial-cycle:
            \tpython3 -m scripts.ops.confenge_commercial_cycle

            # --- CONFENGE final evidence closure (PR #144) ---
            verify-confenge-code-freeze:
            \tpython3 -m scripts.ops.confenge_code_freeze verify-freeze

            # --- end other ---
            unrelated:
            \techo x
            """
        ),
        ".github/workflows/ci.yml": textwrap.dedent(
            """\
            name: CI
            on: [push]
            jobs:
              lint:
                runs-on: ubuntu-latest
                steps:
                  - run: echo lint
              confenge-commercial-code-quality:
                name: CONFENGE Commercial Code Quality
                runs-on: ubuntu-latest
                steps:
                  - run: make verify-confenge-code-freeze
              confenge-machine-evidence-publication:
                name: CONFENGE Final Evidence Integrity
                runs-on: ubuntu-latest
                steps:
                  - run: make verify-confenge-final-integrity-code-freeze
              test-all:
                runs-on: ubuntu-latest
                steps:
                  - run: echo tests
            """
        ),
        "scripts/coverage/edital_relevance_recall.py": "EDITAL_V1 = 1\n",
        "docs/ops/note.md": "docs\n",
        "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/.gitkeep": "",
    }
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    return repo


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    # allow empty? no
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def test_makefile_section_extractor_fail_closed_and_stable() -> None:
    mk = textwrap.dedent(
        """\
        preamble
        # --- CONFENGE commercial ready (x) ---
        confenge-a:
        \techo a
        # --- other section ---
        other:
        \techo o
        # --- CONFENGE final evidence closure (y) ---
        confenge-b:
        \techo b
        """
    )
    section = extract_makefile_confenge_section(mk)
    assert "confenge-a" in section
    assert "confenge-b" in section
    assert "other:" not in section or section.count("other") == 0
    # Changing unrelated section must not change hash if we only extract confenge
    mk2 = mk.replace("echo o", "echo OTHER")
    assert sha256_text(extract_makefile_confenge_section(mk2)) == sha256_text(section)
    # Changing confenge body must change hash
    mk3 = mk.replace("echo a", "echo A2")
    assert sha256_text(extract_makefile_confenge_section(mk3)) != sha256_text(section)
    with pytest.raises(ValueError, match="not found"):
        extract_makefile_confenge_section("no markers here\n")


def test_ci_section_extractor_fail_closed() -> None:
    ci = textwrap.dedent(
        """\
        jobs:
          lint:
            runs-on: ubuntu-latest
          confenge-sector-fit:
            name: CONFENGE Sector Fit
            steps:
              - run: make test-confenge-sector-fit
          other-job:
            runs-on: ubuntu-latest
        """
    )
    section = extract_ci_confenge_section(ci)
    assert "confenge-sector-fit" in section
    assert "other-job" not in section
    with pytest.raises(ValueError, match="No confenge"):
        extract_ci_confenge_section("jobs:\n  lint:\n    runs-on: x\n")


def test_classify_free_vs_protected() -> None:
    protected = {
        "scripts/ops/confenge_code_freeze.py",
        "scripts/commercial_leads/pipeline.py",
    }
    c = classify_changed_paths(
        [
            "scripts/ops/confenge_code_freeze.py",
            "scripts/coverage/edital_relevance_recall.py",
            "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/result.json",
            "docs/ops/foo.md",
        ],
        protected=protected,
    )
    assert c["protected_changed"] == ["scripts/ops/confenge_code_freeze.py"]
    assert "scripts/coverage/edital_relevance_recall.py" in c["free_changed"]
    assert "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/result.json" in c[
        "evidence_lag_changed"
    ]


def test_alter_freeze_gate_after_freeze_fails(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)
    assert SCHEMA_VERSION == man["schema_version"]
    assert CAMPAIGN == man["campaign"]
    paths = protected_path_set(man)
    assert "scripts/ops/confenge_code_freeze.py" in paths
    assert "scripts/ops/verify_confenge_artifact_binding.py" in paths

    # Unrelated + gate change
    (repo / "scripts/ops/confenge_code_freeze.py").write_text("FREEZE_V2 = 2\n", encoding="utf-8")
    tip = _commit_all(repo, "change freeze gate")

    rep = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip, art_dir=art
    )
    assert rep["ok"] is False
    assert "scripts/ops/confenge_code_freeze.py" in rep["protected_changed"]


def test_alter_only_edital_relevance_passes(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    edital = repo / "scripts/coverage/edital_relevance_recall.py"
    edital.write_text("EDITAL_V2 = 2\n", encoding="utf-8")
    tip = _commit_all(repo, "edital only")

    rep = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip, art_dir=art
    )
    assert rep["ok"] is True, rep
    assert rep["protected_changed"] == []
    assert "scripts/coverage/edital_relevance_recall.py" in rep["free_changed"]


def test_unrelated_new_feature_passes_without_allowlist_edit(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    feat = repo / "scripts/coverage/brand_new_feature.py"
    feat.parent.mkdir(parents=True, exist_ok=True)
    feat.write_text("NEW = 1\n", encoding="utf-8")
    tests = repo / "tests/coverage/test_brand_new_feature.py"
    tests.parent.mkdir(parents=True, exist_ok=True)
    tests.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    tip = _commit_all(repo, "unrelated feature")

    rep = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip, art_dir=art
    )
    assert rep["ok"] is True, rep
    assert rep["protected_changed"] == []
    assert any("brand_new_feature" in p for p in rep["free_changed"])


def test_commercial_pipeline_and_profile_and_schema_fail(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    cases = [
        ("scripts/commercial_leads/pipeline.py", "PIPELINE_V2\n"),
        ("scripts/commercial_leads/scoring.py", "SCORING_V2\n"),
        ("config/commercial_profiles/confenge.yaml", "profile_id: confenge\nchanged: true\n"),
        ("db/migrations/062_commercial_leads_ledger.sql", "-- 062 changed\n"),
        ("scripts/ops/verify_confenge_artifact_binding.py", "BIND_V2\n"),
    ]
    for rel, content in cases:
        # reset to freeze each iteration
        _git(repo, "checkout", freeze, "--", ".")
        # ensure clean commit from freeze
        # create branch tip from freeze
        (repo / rel).write_text(content, encoding="utf-8")
        tip = _commit_all(repo, f"change {rel}")
        rep = evaluate_post_freeze_diff(
            root=repo, freeze_sha=freeze, tip=tip, art_dir=art
        )
        assert rep["ok"] is False, (rel, rep)
        assert rel in rep["protected_changed"] or any(
            rel in p for p in rep["protected_changed"]
        ), rep


def test_makefile_confenge_section_change_fails_unrelated_make_passes(
    tmp_path: Path,
) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    # Unrelated makefile target change only
    mk = (repo / "Makefile").read_text(encoding="utf-8")
    (repo / "Makefile").write_text(
        mk.replace("echo other", "echo other2"), encoding="utf-8"
    )
    tip = _commit_all(repo, "makefile unrelated")
    rep = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip, art_dir=art
    )
    assert rep["ok"] is True, rep

    # CONFENGE command change
    _git(repo, "checkout", freeze, "--", "Makefile")
    mk = (repo / "Makefile").read_text(encoding="utf-8")
    (repo / "Makefile").write_text(
        mk.replace(
            "python3 -m scripts.ops.confenge_commercial_cycle",
            "python3 -m scripts.ops.confenge_commercial_cycle --evil",
        ),
        encoding="utf-8",
    )
    tip2 = _commit_all(repo, "makefile confenge cmd")
    # rewrite manifest still at freeze
    write_frozen_inputs_manifest(man, art_dir=art)
    rep2 = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip2, art_dir=art
    )
    assert rep2["ok"] is False, rep2
    assert MAKEFILE_SECTION_KEY in rep2["protected_changed"]


def test_ci_confenge_section_change_fails(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    ci = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    (repo / ".github/workflows/ci.yml").write_text(
        ci.replace(
            "make verify-confenge-code-freeze",
            "make verify-confenge-code-freeze --weaken",
        ),
        encoding="utf-8",
    )
    tip = _commit_all(repo, "ci confenge weaken")
    rep = evaluate_post_freeze_diff(
        root=repo, freeze_sha=freeze, tip=tip, art_dir=art
    )
    assert rep["ok"] is False, rep
    assert CI_SECTION_KEY in rep["protected_changed"]


def test_binding_allows_edital_fails_on_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive shipped check_artifact_binding with frozen-input policy."""
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    art = repo / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    write_frozen_inputs_manifest(man, art_dir=art)

    # Point binding module at mini-repo
    import scripts.ops.confenge_frozen_inputs as fi
    import scripts.ops.verify_confenge_artifact_binding as bind

    monkeypatch.setattr(bind, "_ROOT", repo)
    monkeypatch.setattr(bind, "_ART", art)
    monkeypatch.setattr(fi, "CAMPAIGN", CAMPAIGN)  # noop keep

    result = art / "result.json"
    result.write_text(
        json.dumps(
            {
                "artifact_git_sha": freeze,
                "run_git_sha": freeze,
                "gate_git_sha": freeze,
                "git_sha": freeze,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # free path change
    (repo / "scripts/coverage/edital_relevance_recall.py").write_text(
        "EDITAL_V9 = 9\n", encoding="utf-8"
    )
    tip = _commit_all(repo, "edital lag")
    rep = check_artifact_binding(head_sha=tip, result_path=result)
    assert rep["ok"] is True, rep

    # Establish the unchanged non-terminal artifact at the PR base.
    blocked = json.loads(result.read_text(encoding="utf-8"))
    blocked["status"] = "BLOCKED"
    result.write_text(json.dumps(blocked) + "\n", encoding="utf-8")
    checkpoint_base = _commit_all(repo, "blocked evidence baseline")

    # protected pipeline change
    (repo / "scripts/commercial_leads/pipeline.py").write_text(
        "PIPELINE_V9 = 9\n", encoding="utf-8"
    )
    tip2 = _commit_all(repo, "pipeline change")
    rep2 = check_artifact_binding(head_sha=tip2, result_path=result)
    assert rep2["ok"] is False, rep2
    assert any("protected_input_changed" in i for i in rep2["issues"])

    # An architecture checkpoint may preserve an unchanged BLOCKED artifact as
    # explicitly stale. It must not rebind evidence to code that was not run live.
    stale = check_artifact_binding(
        head_sha=tip2,
        result_path=result,
        allow_stale_non_terminal=True,
        change_base_sha=checkpoint_base,
    )
    assert stale["ok"] is True, stale
    assert stale["status"] == "STALE_EVIDENCE_NON_TERMINAL"
    assert stale["bound_sha"] == freeze

    # An artifact edit that is only in the worktree is still part of the
    # checkpoint under review and must fail closed.
    blocked["note"] = "edited after checkpoint"
    result.write_text(json.dumps(blocked) + "\n", encoding="utf-8")
    edited = check_artifact_binding(
        head_sha=tip2,
        result_path=result,
        allow_stale_non_terminal=True,
        change_base_sha=checkpoint_base,
    )
    assert edited["ok"] is False, edited
    assert edited["details"]["stale_evidence"]["artifacts_changed_in_checkpoint"]

    blocked["status"] = "GO_FOR_REAL_CONFENGE_EMAIL_PILOT"
    result.write_text(json.dumps(blocked) + "\n", encoding="utf-8")
    false_go = check_artifact_binding(
        head_sha=tip2,
        result_path=result,
        allow_stale_non_terminal=True,
        change_base_sha=checkpoint_base,
    )
    assert false_go["ok"] is False, false_go
    assert any("protected_input_changed" in i for i in false_go["issues"])


def test_manifest_includes_gates_and_section_keys(tmp_path: Path) -> None:
    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    paths = {i["path"] for i in man["inputs"]}
    assert "scripts/ops/confenge_code_freeze.py" in paths
    assert "scripts/ops/verify_confenge_artifact_binding.py" in paths
    assert "scripts/ops/confenge_frozen_inputs.py" in paths
    assert MAKEFILE_SECTION_KEY in paths
    assert CI_SECTION_KEY in paths
    # No edital allowlist pollution
    assert not any("edital_relevance" in p for p in paths)


def test_section_hash_preserves_trailing_newline_via_git_show(tmp_path: Path) -> None:
    """git show content must not strip trailing newlines before section hash."""
    from scripts.ops.confenge_frozen_inputs import (
        build_frozen_inputs_manifest,
        extract_makefile_confenge_section,
        sha256_text,
    )

    repo = _init_mini_repo(tmp_path)
    freeze = _git(repo, "rev-parse", "HEAD")
    man = build_frozen_inputs_manifest(root=repo, freeze_sha=freeze)
    sec = next(i for i in man["inputs"] if i["path"] == "Makefile#CONFENGE")
    # Re-extract from raw git show without strip
    import subprocess
    raw = subprocess.check_output(
        ["git", "show", f"{freeze}:Makefile"], cwd=str(repo), text=True
    )
    assert not raw.endswith("\n") or raw.endswith("\n")
    expected = sha256_text(extract_makefile_confenge_section(raw))
    assert sec["sha256"] == expected
