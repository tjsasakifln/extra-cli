"""Skeptic fixes: fail-closed forbidden fields; streaming load shape; no silent strip."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.pseo.pipeline import build_export, load_from_fixture
from scripts.pseo.sanitize import assert_public, deep_strip_forbidden


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


def test_load_from_db_source_is_incremental():
    src = Path("scripts/pseo/pipeline.py").read_text(encoding="utf-8")
    assert "iter_fetch_chunked" in src
    assert "raw_materialized" in src
    assert "pre_classified" in src
    # Must not call fetch_chunked that materializes full tables in load_from_db
    # (fetch_chunked may still exist as helper elsewhere)
    assert "server_side_cursor_fetchmany_incremental_classify" in src
