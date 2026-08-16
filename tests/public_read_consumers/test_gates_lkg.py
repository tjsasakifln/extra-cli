"""Freshness, LKG preservation and invalidation."""

from __future__ import annotations

from scripts.public_read_consumers.gates import is_stale, lkg_usable
from scripts.public_read_consumers.hashutil import attach_hash
from scripts.public_read_consumers.snapshot import (
    diff_manifests,
    invalidation_keys_hit,
    label_lkg,
    preserve_or_fail,
    should_publish_current,
)


def test_stale_after_48h() -> None:
    assert is_stale(generated_at="2026-08-16T00:00:00+00:00", source_as_of="2026-08-13T23:00:00+00:00") is True
    assert is_stale(generated_at="2026-08-16T00:00:00+00:00", source_as_of="2026-08-15T00:00:00+00:00") is False


def test_live_absent_does_not_publish() -> None:
    ok, reason = should_publish_current(True, live=True, official_live_present=False)
    assert ok is False
    assert reason == "official_live_absent"


def test_lkg_usable_only_with_label_and_limit() -> None:
    labeled = label_lkg({"schema": "x", "as_of": "2026-08-15T00:00:00+00:00"}, source_as_of="2026-08-15T00:00:00+00:00")
    assert labeled["last_known_good"] is True
    assert lkg_usable(labeled, now="2026-08-16T00:00:00+00:00") is True
    assert lkg_usable(labeled, now="2026-09-01T00:00:00+00:00") is False
    assert lkg_usable({"content_hash": "abc"}, now="2026-08-16T00:00:00+00:00") is False


def test_preserve_or_fail_when_gate_fails(tmp_path) -> None:
    lkg = tmp_path / "lkg"
    lkg.mkdir()
    labeled = label_lkg(
        {"schema": "x", "as_of": "2026-08-15T00:00:00+00:00", "source_as_of": "2026-08-15T00:00:00+00:00"},
        source_as_of="2026-08-15T00:00:00+00:00",
    )
    (lkg / "manifest.json").write_text(__import__("json").dumps(labeled), encoding="utf-8")
    decision = preserve_or_fail(
        output_dir=tmp_path,
        now="2026-08-16T00:00:00+00:00",
        gate_ok=False,
        live=True,
        official_live_present=False,
    )
    assert decision["action"] == "preserve_lkg"


def test_diff_and_invalidation_keys() -> None:
    left = attach_hash({"schema": "x", "facts": 1, "freshness": {"invalidation_keys": ["facts"]}})
    right = attach_hash({"schema": "x", "facts": 2, "freshness": {"invalidation_keys": ["facts"]}})
    diff = diff_manifests(left, right)
    assert diff["equal"] is False
    assert "facts" in invalidation_keys_hit(left, right)
