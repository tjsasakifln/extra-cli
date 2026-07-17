"""Unit tests for scripts.crawl.run_evidence (no network, no DB)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.crawl.run_evidence import (
    assert_checkpoint_run_id,
    bind_checkpoint_run_id,
    build_run_evidence,
    env_non_secret,
    get_git_meta,
    host_id,
    new_run_id,
    sha256_bytes,
    sha256_file,
)


def test_new_run_id_format_and_uniqueness():
    a = new_run_id("contracts")
    b = new_run_id("contracts")
    assert a.startswith("contracts-")
    assert a != b
    assert len(a) > 20


def test_sha256_bytes_stable():
    assert sha256_bytes(b"hello") == sha256_bytes(b"hello")
    assert sha256_bytes(b"hello") != sha256_bytes(b"world")
    assert len(sha256_bytes(b"")) == 64


def test_sha256_file_roundtrip(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"abc123")
    h = sha256_file(p)
    assert h == sha256_bytes(b"abc123")
    assert sha256_file(tmp_path / "missing.bin") is None


def test_get_git_meta_soft_fail_shape():
    meta = get_git_meta()
    assert "git_sha" in meta
    assert "git_branch" in meta
    # In this repo git should usually work; values may be str or None
    assert meta["git_sha"] is None or isinstance(meta["git_sha"], str)
    assert meta["git_branch"] is None or isinstance(meta["git_branch"], str)


def test_host_id_is_short_hex():
    h = host_id()
    assert isinstance(h, str)
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_env_non_secret_excludes_dsn_and_password(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTRACTS_FULL_DAYS", "90")
    monkeypatch.setenv("CONTRACTS_WINDOW_DAYS", "30")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@host/db")
    monkeypatch.setenv("CONTRACTS_PASSWORD", "nope")
    monkeypatch.setenv("SOME_TOKEN", "nope")
    snap = env_non_secret()
    assert snap.get("CONTRACTS_FULL_DAYS") == "90"
    assert snap.get("CONTRACTS_WINDOW_DAYS") == "30"
    assert "DATABASE_URL" not in snap
    assert "CONTRACTS_PASSWORD" not in snap
    assert "SOME_TOKEN" not in snap


def test_build_run_evidence_required_fields(tmp_path: Path):
    ck = tmp_path / "cp.json"
    ck.write_text("{}", encoding="utf-8")
    out = tmp_path / "out.json"
    out.write_text('{"status":"partial"}', encoding="utf-8")

    ev = build_run_evidence(
        run_id="run-test-1",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T01:00:00+00:00",
        command="pilot.py",
        args={"days": 90},
        checkpoint_path=str(ck),
        output_path=str(out),
        status="partial",
        errors=["timeout"],
        criteria={"P1_run_status": False},
        claims_allowed=["path ok"],
        claims_forbidden=["full 90d"],
        counts_before={"n": 0},
        counts_after={"n": 10},
        migration_head="051",
    )
    for key in (
        "run_id",
        "git_sha",
        "git_branch",
        "started_at",
        "completed_at",
        "host_id",
        "command",
        "args",
        "env_non_secret",
        "checkpoint_path",
        "checkpoint_hash",
        "output_path",
        "output_hash",
        "log_path",
        "log_hash",
        "migration_head",
        "counts_before",
        "counts_after",
        "status",
        "errors",
        "criteria",
        "claims_allowed",
        "claims_forbidden",
    ):
        assert key in ev, f"missing {key}"
    assert ev["run_id"] == "run-test-1"
    assert ev["status"] == "partial"
    assert ev["checkpoint_hash"] == sha256_file(ck)
    assert ev["output_hash"] == sha256_file(out)
    assert ev["migration_head"] == "051"
    assert ev["errors"] == ["timeout"]


def test_bind_and_assert_checkpoint_run_id():
    cp: dict = {"mode": "full", "completed_windows": ["w1"]}
    bound = bind_checkpoint_run_id(cp, "run-A")
    assert bound["meta"]["run_id"] == "run-A"
    assert "run-A" in bound["meta"]["run_ids"]
    assert bound["meta"]["previous_run_ids"] == []

    assert_checkpoint_run_id(bound, "run-A")  # no raise

    rebound = bind_checkpoint_run_id(bound, "run-B")
    assert rebound["meta"]["run_id"] == "run-B"
    assert "run-A" in rebound["meta"]["previous_run_ids"]
    assert "run-A" in rebound["meta"]["run_ids"]
    assert "run-B" in rebound["meta"]["run_ids"]

    with pytest.raises(ValueError, match="mismatch"):
        assert_checkpoint_run_id(rebound, "run-A")


def test_bind_preserves_completed_windows():
    cp = {"completed_windows": ["a", "b"], "meta": {"run_id": "old"}}
    out = bind_checkpoint_run_id(cp, "new")
    assert out["completed_windows"] == ["a", "b"]
    assert out["meta"]["previous_run_ids"] == ["old"]


def test_assert_proof_run_coherence_ok():
    from scripts.crawl.run_evidence import assert_proof_run_coherence
    assert_proof_run_coherence({
        "run_id": "r1",
        "status": "partial",
        "totals": {"windows_ok": 1, "windows_skipped_resume": 0},
        "path_proof": {"status": "success", "run_id": "r1"},
        "evidence": {"run_id": "r1", "checkpoint_hash": "deadbeef"},
    })


def test_assert_proof_missing_run_id():
    from scripts.crawl.run_evidence import assert_proof_run_coherence
    import pytest
    with pytest.raises(ValueError, match="run_id"):
        assert_proof_run_coherence({"status": "partial", "evidence": {}})
