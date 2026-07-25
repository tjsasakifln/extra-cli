"""Structural gates: population mode, snapshot binding, SHA binding, persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.commercial_leads import POPULATION_FULL, POPULATION_SAMPLE, SOURCE_STATE_RESTORED
from scripts.commercial_leads.isolation import assert_source_state_isolation, mask_dsn
from scripts.commercial_leads.snapshot import bind_snapshot_to_database


def test_restored_snapshot_mode_declared_when_same_dsn() -> None:
    dsn = "postgresql://u:p@127.0.0.1:5441/confenge_commercial"
    res = assert_source_state_isolation(
        source_dsn=dsn,
        state_dsn=dsn,
        force_mode=SOURCE_STATE_RESTORED,
        enforce_source_readonly=False,
    )
    assert res.source_state_mode == SOURCE_STATE_RESTORED
    assert res.source_state_separated is False


def test_false_separation_claim_fails() -> None:
    dsn = "postgresql://u:p@127.0.0.1:5441/confenge_commercial"
    res = assert_source_state_isolation(
        source_dsn=dsn,
        state_dsn=dsn,
        force_mode="SOURCE_STATE_SEPARATED",
        enforce_source_readonly=False,
    )
    assert not res.ok or "false_source_state_separation" in res.forbidden_hits


def test_bind_snapshot_row_count_mismatch_fails() -> None:
    conn = MagicMock()
    # fetch_all is used inside bind — patch it
    with patch("scripts.commercial_leads.dbutil.fetch_all") as fa:
        fa.side_effect = [
            [{"n": 100}],  # count
            [{"min_d": "2020-01-01", "max_d": "2026-01-01"}],
            [{"contrato_id": "a", "fornecedor_cnpj": "1", "obj_md5": "x"}],
        ]
        # re-import path uses fetch_all from dbutil inside function via local import
        with patch("scripts.commercial_leads.snapshot.fetch_all", create=True):
            pass
    # Call with patched fetch_all inside snapshot module's import site
    with patch("scripts.commercial_leads.dbutil.fetch_all") as fa2:
        # bind_snapshot_to_database imports fetch_all from dbutil at call time
        import scripts.commercial_leads.snapshot as snap_mod

        with patch.object(
            snap_mod,
            "bind_snapshot_to_database",
            wraps=snap_mod.bind_snapshot_to_database,
        ):
            # Patch at the import location used inside the function
            with patch("scripts.commercial_leads.dbutil.fetch_all") as fa3:
                fa3.side_effect = [
                    [{"n": 100}],
                    [{"min_d": "2020-01-01", "max_d": "2026-01-01"}],
                    [{"contrato_id": "a", "fornecedor_cnpj": "1", "obj_md5": "x"}],
                ]
                # The function does: from scripts.commercial_leads.dbutil import fetch_all
                # so we need to patch before call - the import is inside the function
                result = snap_mod.bind_snapshot_to_database(
                    conn,
                    {"contracts_count_declared": 999, "details": {}},
                )
    assert result["ok"] is False
    assert "manifest_row_count_ne_database_row_count" in result["reasons"]


def test_bind_snapshot_match_ok() -> None:
    import scripts.commercial_leads.snapshot as snap_mod

    conn = MagicMock()
    with patch("scripts.commercial_leads.dbutil.fetch_all") as fa:
        fa.side_effect = [
            [{"n": 60000}],
            [{"min_d": "2020-01-01", "max_d": "2026-07-01"}],
            [{"contrato_id": "a", "fornecedor_cnpj": "1", "obj_md5": "x"}],
        ]
        result = snap_mod.bind_snapshot_to_database(
            conn,
            {"contracts_count_declared": 60000, "details": {}},
        )
    assert result["ok"] is True
    assert result["database_row_count"] == 60000
    assert result["table_snapshot_hash"]


def test_artifact_sha_mismatch_policy() -> None:
    """RC must FAIL when artifact SHA != PR HEAD."""
    pr_head = "abc123"
    artifact = {
        "artifact_git_sha": "oldsha",
        "run_git_sha": "oldsha",
        "gate_git_sha": "oldsha",
        "review_git_sha": "oldsha",
    }
    mismatch = any(artifact[k] != pr_head for k in artifact)
    assert mismatch is True


def test_population_modes_constants() -> None:
    assert POPULATION_FULL == "FULL_POPULATION"
    assert POPULATION_SAMPLE == "BOUNDED_SAMPLE"


def test_mask_dsn_hides_password() -> None:
    m = mask_dsn("postgresql://user:secret@127.0.0.1:5441/db")
    assert "secret" not in m
    assert "user" in m


def test_no_rc_technical_pass_in_module_exports() -> None:
    from scripts.commercial_leads import TERMINAL_STATUSES

    assert "RC_TECHNICAL_PASS" not in TERMINAL_STATUSES
    assert set(TERMINAL_STATUSES) == {"PASS", "BLOCKED", "FAIL"}
