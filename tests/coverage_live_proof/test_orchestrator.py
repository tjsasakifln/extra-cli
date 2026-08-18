"""Orchestrator unit tests that drive shipped helpers without a live database."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops.coverage_live_proof.admission import sanitize_text
from scripts.ops.coverage_live_proof.errors import MigrationApplyError, TeardownSafetyError
from scripts.ops.coverage_live_proof.runner import is_campaign_database, quote_ident
from scripts.ops.coverage_live_proof.seed import seed_fixture_sha256, seed_rows


def test_campaign_database_name_is_strict() -> None:
    assert is_campaign_database("coverage_live_proof_aabbccddeeff") is True
    assert is_campaign_database("extra_test") is False
    assert is_campaign_database("postgres") is False
    assert is_campaign_database("coverage_live_proof_extra_test") is False
    assert is_campaign_database("coverage_live_proof_") is False


def test_quote_ident_rejects_unsafe_names() -> None:
    assert quote_ident("coverage_live_proof_aabbccddeeff") == '"coverage_live_proof_aabbccddeeff"'
    with pytest.raises(TeardownSafetyError):
        quote_ident('extra"; DROP DATABASE extra_test; --')


def test_seed_fixture_is_deterministic() -> None:
    first = seed_fixture_sha256()
    second = seed_fixture_sha256()
    assert first == second
    assert len(first) == 64
    rows = seed_rows()
    assert {row.scenario for row in rows} == {"A", "B", "C"}
    assert rows[0].entity_id is None
    assert rows[0].canonical_entity_key is None
    assert rows[1].canonical_entity_key == "ent-10"
    assert rows[2].metadata.get("identity_status") == "unmappable"


def test_migration_error_message_hides_password() -> None:
    dsn = "postgresql://proof:hunter2@127.0.0.1:1/nope"
    wrapped = MigrationApplyError(
        sanitize_text("canonical migration apply failed: could not connect " + dsn, dsn)
    )
    text = str(wrapped)
    assert "hunter2" not in text
    assert "canonical migration apply failed" in text


def test_package_does_not_redefine_coverage_logic() -> None:
    root = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "coverage_live_proof"
    forbidden = (
        "GATE_THRESHOLD =",
        "def classify_evidence_identity",
        "def dual_coverage_evidence_gate",
        "def compute_dual_coverage",
    )
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} must not contain {token}"
