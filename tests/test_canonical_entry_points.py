"""DoD §32.1 entry-point alignment tests."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.canonical_entry_points import validate_entry_points

ROOT = Path(__file__).resolve().parents[1]


def test_development_guide_exists_and_has_commands():
    r = validate_entry_points(ROOT)
    assert r["development_complete"] is True
    assert r["command_alignment"]["development"]["ok"] is True


def test_agents_and_cursor_align_with_development():
    r = validate_entry_points(ROOT)
    assert r["command_alignment"]["agents"]["ok"] is True
    assert r["command_alignment"]["cursor"]["ok"] is True
    assert r["three_entry_points_same_commands"] is True
    assert r["three_entry_points_same_docs"] is True


def test_product_requirements_outside_adapters():
    r = validate_entry_points(ROOT)
    assert r["adapters_dispensable"]["ok"] is True
    assert (ROOT / "DOD.md").is_file()
    assert (ROOT / "docs" / "DEVELOPMENT.md").is_file()


def test_precedence_documented():
    r = validate_entry_points(ROOT)
    assert r["precedence_documented"] is True


def test_no_false_local_ready_claim_in_adapters():
    r = validate_entry_points(ROOT)
    assert r["false_claim_hits"] == []
