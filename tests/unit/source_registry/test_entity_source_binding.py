"""Tests for capability-aware entity_source_binding (migration 058 / Option A)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.source_registry.bindings import (
    CAPABILITIES,
    EntitySourceBinding,
    binding_identity_key,
    detect_invalid_duplicates,
    ensure_capability_pair,
    filter_by_capability,
)

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migrations"
    / "058_entity_source_binding_capability.sql"
)


def test_migration_file_exists_and_declares_capability_unique() -> None:
    assert MIGRATION.is_file()
    text = MIGRATION.read_text(encoding="utf-8")
    assert "entity_source_binding" in text
    assert "notices_or_bids" in text
    assert "contracts" in text
    assert "UNIQUE (canonical_id, source_id, capability)" in text or re.search(
        r"UNIQUE\s*\(\s*canonical_id\s*,\s*source_id\s*,\s*capability\s*\)",
        text,
        re.I,
    )


def test_both_capabilities_on_same_entity_source() -> None:
    pair = ensure_capability_pair("123:ENT", "pncp")
    assert len(pair) == 2
    caps = {b.capability for b in pair}
    assert caps == set(CAPABILITIES)
    assert detect_invalid_duplicates(pair) == []


def test_duplicate_identity_detected() -> None:
    a = EntitySourceBinding(
        canonical_id="x", source_id="pncp", capability="notices_or_bids"
    )
    b = EntitySourceBinding(
        canonical_id="x", source_id="pncp", capability="notices_or_bids"
    )
    dups = detect_invalid_duplicates([a, b])
    assert dups == [("x", "pncp", "notices_or_bids")]


def test_multi_capability_not_duplicate() -> None:
    a = EntitySourceBinding(
        canonical_id="x", source_id="pncp", capability="notices_or_bids"
    )
    b = EntitySourceBinding(
        canonical_id="x", source_id="pncp", capability="contracts"
    )
    assert detect_invalid_duplicates([a, b]) == []
    assert binding_identity_key(a) != binding_identity_key(b)


def test_validate_rejects_bad_capability() -> None:
    bad = EntitySourceBinding(
        canonical_id="x", source_id="pncp", capability="pricing"
    )
    errs = bad.validate()
    assert any("invalid_capability" in e for e in errs)


def test_filter_by_capability() -> None:
    bindings = ensure_capability_pair("y", "ciga") + ensure_capability_pair("z", "pncp")
    only = filter_by_capability(bindings, "contracts")
    assert len(only) == 2
    assert all(b.capability == "contracts" for b in only)


def test_filter_unknown_capability_raises() -> None:
    with pytest.raises(ValueError, match="unknown capability"):
        filter_by_capability([], "nope")
