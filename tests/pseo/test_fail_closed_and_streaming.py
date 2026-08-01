"""Skeptic fixes: fail-closed forbidden fields; streaming load shape; no silent strip."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.pseo.pipeline import build_export, load_from_fixture
from scripts.pseo.provenance import EXPORT_ENTRYPOINT
from scripts.pseo.sanitize import assert_public, deep_strip_forbidden
from scripts.pseo.validation import validate_export_dir


def test_assert_public_fails_on_forbidden_score_total():
    with pytest.raises(ValueError, match="Forbidden"):
        assert_public({"markets": [{"id": "m", "score_total": 9.9}]}, "payload")


def test_build_export_does_not_silently_strip_forbidden(monkeypatch: pytest.MonkeyPatch):
    """If a builder injects a forbidden key, export must fail — not strip."""
    from scripts.pseo import pipeline as pl

    contracts, bids, counts = load_from_fixture(
        Path("tests/pseo/fixtures/sample_contracts.json")
    )

    original_markets = pl.build_markets

    def poisoned_markets(*args, **kwargs):
        markets = original_markets(*args, **kwargs)
        if markets:
            markets[0]["commercial_state"] = "HOT"
        else:
            markets.append(
                {
                    "id": "poison",
                    "slug": "poison",
                    "contract_count": 1,
                    "buyer_count": 1,
                    "supplier_count": 1,
                    "total_value": 1.0,
                    "commercial_state": "HOT",
                }
            )
        return markets

    monkeypatch.setattr(pl, "build_markets", poisoned_markets)
    with pytest.raises(ValueError, match="Forbidden|commercial_state|export_payload"):
        build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")


def test_deep_strip_still_exists_but_is_not_used_in_build_export_source():
    """Guard: pipeline must not call deep_strip_forbidden (fail-closed policy)."""
    src = Path("scripts/pseo/pipeline.py").read_text(encoding="utf-8")
    assert "deep_strip_forbidden(" not in src
    # helper may still exist for legacy tooling but must not be the export path
    stripped = deep_strip_forbidden({"score_total": 1, "ok": True})
    assert "score_total" not in stripped


def test_require_commit_entrypoint_true_on_promote_path():
    src = Path("scripts/pseo/pipeline.py").read_text(encoding="utf-8")
    assert "require_commit_entrypoint=False" not in src
    assert "require_commit_entrypoint=True" in src


def test_bogus_source_commit_sha_rejected_even_when_cli_export_exists(tmp_path: Path):
    """B7: presence of cli_export.py must NOT accept a fake/unreachable SHA.

    Previously validation short-circuited when cli_export.py existed, making
    source_commit_sha a no-op. Bogus SHAs must fail require_commit_entrypoint.
    """
    # Prove durable entry still exists (the old short-circuit condition)
    assert Path("scripts/pseo/cli_export.py").is_file()

    # Minimal valid-shaped export with a deliberately bogus commit SHA
    body = {"markets": []}
    body_text = json.dumps(body, sort_keys=True) + "\n"
    markets_hash = hashlib.sha256(body_text.encode()).hexdigest()
    dataset_hash = hashlib.sha256(b"test-dataset").hexdigest()
    manifest = {
        "schema_version": "1.1.0",
        "generated_at": "2026-07-31T00:00:00Z",
        "data_as_of": "2026-07-31",
        "source_run_id": "test",
        "source_repository": "extra-cli",
        "source_commit_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "source_branch": "test",
        "export_entrypoint": EXPORT_ENTRYPOINT,
        "export_version": "1.0.0",
        "dataset_hash": dataset_hash,
        "checksums": {"markets.json": markets_hash},
        "sources": [],
        "counts": {},
        "timezone": "America/Sao_Paulo",
        "freshness": {"data_period_end": "2026-07-31"},
        "limitations": [],
    }
    out = tmp_path / "export"
    out.mkdir()
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (out / "markets.json").write_text(body_text, encoding="utf-8")

    # Hash verification will also fail (dataset_hash wrong) — we only care that
    # the bogus SHA itself is reported as an error, not silently accepted.
    vr = validate_export_dir(out, repo_root=Path(".").resolve(), require_commit_entrypoint=True)
    assert vr["ok"] is False
    sha_errors = [e for e in vr["errors"] if "source_commit_sha" in e or "entrypoint" in e.lower()]
    assert sha_errors, (
        f"expected source_commit_sha/entrypoint error for bogus SHA; got: {vr['errors']}"
    )
    assert any("deadbeef" in e for e in vr["errors"]) or any(
        "does not contain export entrypoint" in e for e in vr["errors"]
    )


def test_unknown_source_commit_sha_rejected(tmp_path: Path):
    """B7: missing/unknown source_commit_sha must fail when require_commit_entrypoint."""
    body_text = "[]\n"
    markets_hash = hashlib.sha256(body_text.encode()).hexdigest()
    manifest = {
        "schema_version": "1.1.0",
        "generated_at": "2026-07-31T00:00:00Z",
        "data_as_of": "2026-07-31",
        "source_run_id": "test",
        "source_repository": "extra-cli",
        "source_commit_sha": "unknown",
        "source_branch": "test",
        "export_entrypoint": EXPORT_ENTRYPOINT,
        "export_version": "1.0.0",
        "dataset_hash": hashlib.sha256(b"x").hexdigest(),
        "checksums": {"markets.json": markets_hash},
        "sources": [],
        "counts": {},
        "timezone": "America/Sao_Paulo",
        "freshness": {"data_period_end": "2026-07-31"},
        "limitations": [],
    }
    out = tmp_path / "export"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (out / "markets.json").write_text(body_text, encoding="utf-8")
    vr = validate_export_dir(out, repo_root=Path(".").resolve(), require_commit_entrypoint=True)
    assert vr["ok"] is False
    assert any("source_commit_sha missing or unknown" in e for e in vr["errors"])


def test_load_from_db_source_is_incremental():
    src = Path("scripts/pseo/pipeline.py").read_text(encoding="utf-8")
    assert "iter_fetch_chunked" in src
    assert "raw_materialized" in src
    assert "StagingStore" in src or "staging" in src
    # SQLite staging path — no giant pre_classified list retained during extract
    assert "server_side_cursor_fetchmany_sqlite_staging" in src
    assert "insert_classified_batch" in src
    assert "secure_delete" in src

def test_staging_load_all_forbidden():
    """B3: full materialization helpers must fail closed on export path."""
    from scripts.pseo.staging import StagingStore

    st = StagingStore()
    try:
        try:
            st.load_all_classified()
            raise AssertionError("load_all_classified must raise")
        except RuntimeError as e:
            assert "forbidden" in str(e).lower() or "memory" in str(e).lower()
        try:
            st.load_all_bids()
            raise AssertionError("load_all_bids must raise")
        except RuntimeError as e:
            assert "forbidden" in str(e).lower() or "memory" in str(e).lower()
    finally:
        st.secure_delete()
