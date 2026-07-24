"""Tests for CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 integrated entry point.

Drives real shipped functions — no reimplementation of isolation/terminal logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.client_ready_consulting_cycle import (
    CAMPAIGN_ID,
    decide_terminal,
    isolation_guard,
    main,
    validate_acceptance_binding,
)

ROOT = Path(__file__).resolve().parents[1]


def test_isolation_rejects_ec_prod() -> None:
    with pytest.raises(SystemExit) as ei:
        isolation_guard("postgresql://u:p@ec-prod:5432/extra_prod")
    payload = json.loads(str(ei.value))
    assert payload["status"] == "FAIL"
    assert payload["isolation"]["ok"] is False


def test_isolation_rejects_port_5432() -> None:
    with pytest.raises(SystemExit):
        isolation_guard("postgresql://test:test@127.0.0.1:5432/anything")


def test_isolation_rejects_opt_path_in_dsn() -> None:
    with pytest.raises(SystemExit):
        isolation_guard("postgresql://test:test@127.0.0.1:5436//opt/extra-consultoria")


def test_isolation_accepts_campaign_local_dsn() -> None:
    r = isolation_guard("postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc")
    assert r["ok"] is True
    assert r["production_touched"] is False
    assert r["soak_touched"] is False
    assert r["production_touched"] is not None
    assert r["soak_touched"] is not None


def test_decide_terminal_blocked_without_human_accept() -> None:
    isolation = {"ok": True, "production_touched": False, "soak_touched": False}
    migrations = {"idempotent": True}
    snapshot = {"ok": True}
    pack = {"reconcile": {"status": "PASS"}}
    linkage = {"status": "completed"}
    monthly = {"mode": "LIVE_ISOLATED", "live_recurrence": True}
    acceptance = {"status": "PENDING_HUMAN"}
    term, blockers = decide_terminal(
        isolation=isolation,
        migrations=migrations,
        snapshot=snapshot,
        pack=pack,
        linkage=linkage,
        monthly=monthly,
        acceptance=acceptance,
        failures=[],
    )
    assert term == "BLOCKED"
    assert any("PENDING_HUMAN" in b for b in blockers)


def test_decide_terminal_fail_on_reconcile() -> None:
    term, _ = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "FAIL"}},
        linkage={"status": "completed"},
        monthly={"mode": "LIVE_ISOLATED"},
        acceptance={"status": "ACCEPTED", "accepted_by": "Tiago"},
        failures=[],
    )
    assert term == "FAIL"


def test_decide_terminal_pass_with_accept_and_labeled_recurrence_mechanics() -> None:
    """PASS allowed with bound human ACCEPT + labeled recurrence mechanics (not live dual)."""
    term, blockers = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "PASS"}},
        linkage={"status": "completed"},
        monthly={
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_recurrence": False,
            "synthetic_inject_used": True,
            "live_dual_snapshot": False,
        },
        acceptance={
            "status": "ACCEPTED",
            "accepted_by": "Tiago Sasaki",
            "binding": {"valid": True},
        },
        failures=[],
        recurrence={
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_dual_snapshot": False,
        },
    )
    assert term == "PASS"
    assert blockers == []


def test_decide_terminal_fails_false_live_dual_snapshot_claim() -> None:
    """Honesty: labeled inject cannot report live_dual_snapshot=true."""
    term, blockers = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "PASS"}},
        linkage={"status": "completed"},
        monthly={
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "synthetic_inject_used": True,
            "live_dual_snapshot": False,
        },
        acceptance={
            "status": "ACCEPTED",
            "accepted_by": "Tiago Sasaki",
            "binding": {"valid": True},
        },
        failures=[],
        recurrence={
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_dual_snapshot": True,  # false claim
        },
    )
    assert term == "FAIL"
    assert any("false_live_dual_snapshot" in b for b in blockers)


def test_decide_terminal_fails_live_isolated_dual_without_proof() -> None:
    """LIVE_ISOLATED + live_dual_snapshot without dual_snapshot_proof must FAIL."""
    term, blockers = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "PASS"}},
        linkage={"status": "completed"},
        monthly={
            "mode": "LIVE_ISOLATED",
            "live_dual_snapshot": True,
            "dual_snapshot_proof": False,
        },
        acceptance={
            "status": "ACCEPTED",
            "accepted_by": "Tiago Sasaki",
            "binding": {"valid": True},
        },
        failures=[],
        recurrence={"mode": "LIVE_ISOLATED", "live_dual_snapshot": True},
    )
    assert term == "FAIL"
    assert any("false_live_dual_snapshot" in b for b in blockers)


def test_validate_acceptance_binding_rejects_stale_accept() -> None:
    """ACCEPTED for old run_id/rc_sha/checksums must demote to PENDING (no silent rebind)."""
    prior = {
        "status": "ACCEPTED",
        "accepted_by": "Tiago Sasaki",
        "accepted_at": "2026-07-24T21:40:15Z",
        "run_id": "old-run",
        "rc_sha": "a" * 40,
        "package_checksums": {
            "pack-manifest.json": "0" * 64,
            "executive-summary.md": "1" * 64,
        },
    }
    out = validate_acceptance_binding(
        prior,
        pack_run_id="new-run",
        rc_sha="b" * 40,
        pack_checksums={
            "pack-manifest.json": "c" * 64,
            "executive-summary.md": "d" * 64,
        },
    )
    assert out["status"] == "PENDING_HUMAN"
    assert out["accepted_by"] is None
    assert out["run_id"] == "new-run"
    assert out["rc_sha"] == "b" * 40
    assert out["binding"]["valid"] is False
    assert out["binding"]["prior_accepted_run_id"] == "old-run"
    assert any("run_id" in m for m in out["binding"]["mismatches"])


def test_validate_acceptance_binding_keeps_matching_accept() -> None:
    ck = {
        "pack-manifest.json": "a" * 64,
        "executive-summary.md": "b" * 64,
        "consulting-pack.xlsx": "c" * 64,
        "executive-report.pdf": "d" * 64,
    }
    prior = {
        "status": "ACCEPTED",
        "accepted_by": "Tiago Sasaki",
        "accepted_at": "2026-07-24T21:40:15Z",
        "run_id": "run-1",
        "rc_sha": "e" * 40,
        "package_checksums": dict(ck),
    }
    out = validate_acceptance_binding(
        prior, pack_run_id="run-1", rc_sha="e" * 40, pack_checksums=ck
    )
    assert out["status"] == "ACCEPTED"
    assert out["accepted_by"] == "Tiago Sasaki"
    assert out["binding"]["valid"] is True

def test_cli_guard_exit_codes() -> None:
    assert main(["guard", "--dsn", "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc"]) == 0
    assert main(["guard", "--dsn", "postgresql://u:p@ec-prod/db"]) == 3


def test_makefile_targets_registered() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    for t in (
        "client-ready-consulting-cycle",
        "campaign-gate-client-ready-recurring-consulting-cycle",
        "release-candidate-client-ready-recurring-consulting-cycle",
        "verify-client-ready-recurring-consulting-cycle-isolated",
        "dod-audit-client-ready-recurring-consulting-cycle",
    ):
        assert t in mk


def test_orchestrator_module_importable() -> None:
    assert CAMPAIGN_ID == "CLIENT-READY-RECURRING-CONSULTING-CYCLE-01"
    assert (ROOT / "scripts/ops/client_ready_consulting_cycle.py").is_file()
    assert (ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql").is_file()
    assert (ROOT / "db/migrations/061_canonical_entity_linkage.sql").is_file()


def test_terminal_status_vocabulary_only_three() -> None:
    """Global status must be exactly PASS|BLOCKED|FAIL — no alternate terminals."""
    src = (ROOT / "scripts/ops/client_ready_consulting_cycle.py").read_text(encoding="utf-8")
    for banned in (
        "TECHNICAL_PASS",
        "READY_FOR_REVIEW",
        "MOSTLY_PASS",
        "CONDITIONAL_PASS",
        "BLOCKED_HUMAN",
    ):
        # may appear in comments/docs of other campaigns; orchestrator decide path must not return them
        assert f'return "{banned}"' not in src


def test_build_recurrence_delta_reads_live_cycle2(tmp_path: Path) -> None:
    """IAF-08a: must not invent success_zero when cycle_2 has deltas; dual=false for inject."""
    from scripts.ops.client_ready_consulting_cycle import build_recurrence_delta

    mon = tmp_path / "monthly"
    mon.mkdir()
    (mon / "monthly-monitor-live.json").write_text(
        json.dumps(
            {
                "mode": "LABELED_DETERMINISTIC_REPLAY",
                "live_dual_snapshot": False,
                "synthetic_inject_used": True,
                "cycle_1": {"cycle": {"cycle_id": "c1"}, "new_editais": [{"edital_id": "1"}]},
                "cycle_2": {
                    "cycle": {"cycle_id": "c2"},
                    "new_editais": [{"edital_id": "LIVE-DELTA"}],
                    "status_deltas": [
                        {
                            "edital_id": "1",
                            "event_type": "SUSPENSAO",
                            "from_status": "open",
                            "to_status": "SUSPENSA",
                        }
                    ],
                    "expiring_contracts": [{"id": "c1"}, {"id": "c2"}],
                    "variation": {
                        "fields": {
                            "organs_count": {"previous": 10, "current": 11, "delta": 1},
                            "winners_count": {"previous": 5, "current": 5, "delta": 0},
                        }
                    },
                },
                "proofs": {
                    "new_editais_detected": True,
                    "labeled_inject_not_second_real_snapshot": True,
                },
            }
        ),
        encoding="utf-8",
    )
    out = build_recurrence_delta(
        {
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_recurrence": False,
            "synthetic_inject_used": True,
        },
        tmp_path,
    )
    assert out["categories"]["new_opportunities"]["count"] == 1
    assert out["categories"]["new_opportunities"]["success_zero"] is False
    assert out["categories"]["status_changes"]["count"] == 1
    assert out["categories"]["status_changes"]["success_zero"] is False
    assert out["categories"]["org_ranking_changes"]["count"] == 1
    assert out["live_dual_snapshot"] is False
    assert out["mode"] == "LABELED_DETERMINISTIC_REPLAY"


def test_reconcile_compares_distinct_meta_and_artifacts(tmp_path: Path) -> None:
    """IAF-05: reconcile must not hardcode same_run_id or ignore artifacts."""
    from scripts.ops import live_consulting_pack as lcp

    pdf = tmp_path / "a.pdf"
    xls = tmp_path / "a.xlsx"
    pdf.write_bytes(b"%PDF-1.4 run_id=rid-1 fake")
    # minimal xlsx zip is complex; write non-empty distinct bytes
    xls.write_bytes(b"PK\x03\x04 excel-placeholder-rid-1")
    meta = {"run_id": "rid-1", "git_sha": "abc", "as_of": "2026-07-24"}
    rec = lcp.reconcile(
        run_id="rid-1",
        meta_pdf=dict(meta),
        meta_excel=dict(meta),
        a={"population": {"eligible_population": 10}, "rows": []},
        b={"population": {"eligible_population": 10}, "rows": []},
        c={"population": {"eligible_population": 10}, "rows": []},
        d={"population": {"eligible_population": 10}, "panels": []},
        pdf_path=pdf,
        excel_path=xls,
    )
    assert rec["same_run_id"] is True
    assert rec["status"] == "PASS"
    assert rec["artifact_checks"]["binaries_distinct"] is True
    assert rec["artifact_checks"]["pdf_sha256"] != rec["artifact_checks"]["excel_sha256"]

    bad = lcp.reconcile(
        run_id="rid-1",
        meta_pdf={"run_id": "rid-1", "git_sha": "abc"},
        meta_excel={"run_id": "rid-OTHER", "git_sha": "abc"},
        a={},
        b={},
        c={},
        d={},
    )
    assert bad["same_run_id"] is False
    assert bad["status"] == "FAIL"
