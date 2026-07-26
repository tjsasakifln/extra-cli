"""Structural gates: population mode, snapshot binding, SHA binding, persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.commercial_leads import POPULATION_FULL, POPULATION_SAMPLE, SOURCE_STATE_RESTORED
from scripts.commercial_leads.isolation import assert_source_state_isolation, mask_dsn


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
    import scripts.commercial_leads.snapshot as snap_mod

    conn = MagicMock()
    with patch("scripts.commercial_leads.dbutil.fetch_all") as fa3:
        fa3.side_effect = [
            [{"n": 100}],
            [{"min_d": "2020-01-01", "max_d": "2026-01-01"}],
            [{"contrato_id": "a", "fornecedor_cnpj": "1", "obj_md5": "x"}],
        ]
        with patch.object(
            snap_mod,
            "compute_canonical_table_hash",
            return_value={
                "canonical_table_hash": "abc",
                "canonical_hash_algorithm": "sha256-rowmd5-ordered-agg-v1",
                "row_count": 100,
                "rows_hashed": 100,
                "table": "pncp_supplier_contracts",
            },
        ):
            result = snap_mod.bind_snapshot_to_database(
                conn,
                {
                    "contracts_count_declared": 999,
                    "details": {},
                    "canonical_table_hash": "abc",
                },
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
        with patch.object(
            snap_mod,
            "compute_canonical_table_hash",
            return_value={
                "canonical_table_hash": "deadbeef",
                "canonical_hash_algorithm": "sha256-rowmd5-ordered-agg-v1",
                "row_count": 60000,
                "rows_hashed": 60000,
                "table": "pncp_supplier_contracts",
            },
        ):
            result = snap_mod.bind_snapshot_to_database(
                conn,
                {
                    "contracts_count_declared": 60000,
                    "details": {},
                    "canonical_table_hash": "deadbeef",
                },
            )
    assert result["ok"] is True
    assert result["database_row_count"] == 60000
    assert result["canonical_table_hash"] == "deadbeef"
    assert result["status"] == "BOUND"


def test_bind_snapshot_canonical_mismatch_fails() -> None:
    import scripts.commercial_leads.snapshot as snap_mod

    conn = MagicMock()
    with patch("scripts.commercial_leads.dbutil.fetch_all") as fa:
        fa.side_effect = [
            [{"n": 60000}],
            [{"min_d": "2020-01-01", "max_d": "2026-07-01"}],
            [{"contrato_id": "a", "fornecedor_cnpj": "1", "obj_md5": "x"}],
        ]
        with patch.object(
            snap_mod,
            "compute_canonical_table_hash",
            return_value={
                "canonical_table_hash": "livehash",
                "canonical_hash_algorithm": "sha256-rowmd5-ordered-agg-v1",
                "row_count": 60000,
                "rows_hashed": 60000,
                "table": "pncp_supplier_contracts",
            },
        ):
            result = snap_mod.bind_snapshot_to_database(
                conn,
                {
                    "contracts_count_declared": 60000,
                    "canonical_table_hash": "oldhash",
                    "details": {},
                },
            )
    assert result["ok"] is False
    assert "canonical_table_hash_mismatch" in result["reasons"]

def test_artifact_sha_mismatch_policy_drives_shipped_gate(tmp_path: Path) -> None:
    """Shipped SHA-binding gate must FAIL when internal SHAs disagree."""
    from scripts.ops.verify_confenge_artifact_binding import check_artifact_binding

    head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    result = {
        "status": "BLOCKED",
        "git_sha": head,
        "artifact_git_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "run_git_sha": head,
        "gate_git_sha": head,
        "review_git_sha": head,
    }
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    report = check_artifact_binding(head_sha=head, result_path=path)
    assert report["ok"] is False
    assert report["status"] == "FAIL"
    assert any("mismatch" in i for i in report["issues"])


def test_artifact_sha_match_passes(tmp_path: Path) -> None:
    from scripts.ops.verify_confenge_artifact_binding import check_artifact_binding

    head = "cccccccccccccccccccccccccccccccccccccccc"
    result = {
        "status": "BLOCKED",
        "git_sha": head,
        "artifact_git_sha": head,
        "run_git_sha": head,
        "gate_git_sha": head,
        "review_git_sha": head,
    }
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    report = check_artifact_binding(head_sha=head, result_path=path)
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_public_consorcio_excluded_by_organ_markers() -> None:
    from scripts.commercial_leads.identity import resolve_supplier
    from scripts.commercial_leads.profile import load_profile

    prof = load_profile("config/commercial_profiles/confenge.yaml")
    markers = list((prof.data.get("exclusions") or {}).get("organ_name_markers") or [])
    r = resolve_supplier(
        "22835076000170",
        "CONSORCIO INTEGRADO MULTIFINALITARIO DO VALE DO JEQUITINHONHA",
        organ_markers=markers,
    )
    assert r.eligible is False
    assert r.exclusion_reason == "public_organ_name"


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
