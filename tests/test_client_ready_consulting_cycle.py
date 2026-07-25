"""Tests for CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 integrated entry point.

Drives real shipped functions — no reimplementation of isolation/terminal logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.client_ready_consulting_cycle import (
    BLOCKED_MISSING_FROZEN_RC,
    CAMPAIGN_ID,
    FROZEN_RC_ARTIFACT_NAME,
    FROZEN_RC_PRODUCT_SHA,
    FROZEN_RC_RUN_ID,
    REQUIRED_IDENTITY_FILES,
    assemble_client_ready_frozen_rc,
    decide_terminal,
    identity_checksum_mismatches,
    isolation_guard,
    main,
    missing_required_frozen_binaries,
    validate_acceptance_binding,
)

ROOT = Path(__file__).resolve().parents[1]


def _full_identity_ck(**overrides: str) -> dict[str, str]:
    base = {
        "pack-manifest.json": "a" * 64,
        "executive-summary.md": "b" * 64,
        "consulting-pack.xlsx": "c" * 64,
        "executive-report.pdf": "d" * 64,
    }
    base.update(overrides)
    return base


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
        "package_checksums": _full_identity_ck(
            **{
                "pack-manifest.json": "0" * 64,
                "executive-summary.md": "1" * 64,
            }
        ),
    }
    out = validate_acceptance_binding(
        prior,
        pack_run_id="new-run",
        rc_sha="b" * 40,
        pack_checksums=_full_identity_ck(
            **{
                "pack-manifest.json": "c" * 64,
                "executive-summary.md": "d" * 64,
            }
        ),
    )
    assert out["status"] == "PENDING_HUMAN"
    assert out["accepted_by"] is None
    assert out["binding"]["valid"] is False
    assert out["binding"]["prior_accepted_run_id"] == "old-run"
    assert any("run_id" in m for m in out["binding"]["mismatches"])


def test_validate_acceptance_binding_keeps_matching_accept() -> None:
    ck = _full_identity_ck()
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


# --- Fail-closed identity binding (adversarial suite for PR #131 human accept) ---


def _accepted_base(**ck_overrides: str) -> dict:
    ck = _full_identity_ck(**ck_overrides)
    return {
        "status": "ACCEPTED",
        "accepted_by": "Tiago Sasaki",
        "accepted_at": "2026-07-24T21:40:15Z",
        "run_id": "run-1",
        "rc_sha": "e" * 40,
        "package_checksums": ck,
    }


def test_binding_invalid_when_pdf_missing_from_pack() -> None:
    """1. PDF absent in pack_checksums → binding invalid (missing_actual_artifact)."""
    prior = _accepted_base()
    pack_ck = _full_identity_ck()
    del pack_ck["executive-report.pdf"]
    out = validate_acceptance_binding(
        prior, pack_run_id="run-1", rc_sha="e" * 40, pack_checksums=pack_ck
    )
    assert out["status"] == "PENDING_HUMAN"
    assert out["binding"]["valid"] is False
    assert "missing_actual_artifact:executive-report.pdf" in out["binding"]["mismatches"]


def test_binding_invalid_when_xlsx_missing_from_pack() -> None:
    """2. XLSX absent → binding invalid."""
    prior = _accepted_base()
    pack_ck = _full_identity_ck()
    del pack_ck["consulting-pack.xlsx"]
    out = validate_acceptance_binding(
        prior, pack_run_id="run-1", rc_sha="e" * 40, pack_checksums=pack_ck
    )
    assert out["binding"]["valid"] is False
    assert "missing_actual_artifact:consulting-pack.xlsx" in out["binding"]["mismatches"]


def test_binding_invalid_when_manifest_missing_from_accepted() -> None:
    """3. Manifest absent from accepted_ck → binding invalid."""
    prior = _accepted_base()
    del prior["package_checksums"]["pack-manifest.json"]
    out = validate_acceptance_binding(
        prior,
        pack_run_id="run-1",
        rc_sha="e" * 40,
        pack_checksums=_full_identity_ck(),
    )
    assert out["binding"]["valid"] is False
    assert "missing_expected_checksum:pack-manifest.json" in out["binding"]["mismatches"]


def test_binding_invalid_when_summary_missing_from_accepted() -> None:
    """4. Summary absent from accepted_ck → binding invalid."""
    prior = _accepted_base()
    del prior["package_checksums"]["executive-summary.md"]
    out = validate_acceptance_binding(
        prior,
        pack_run_id="run-1",
        rc_sha="e" * 40,
        pack_checksums=_full_identity_ck(),
    )
    assert out["binding"]["valid"] is False
    assert "missing_expected_checksum:executive-summary.md" in out["binding"]["mismatches"]


def test_binding_invalid_on_checksum_mismatch() -> None:
    """5. Checksum different → binding invalid with checksum_mismatch classification."""
    prior = _accepted_base()
    pack_ck = _full_identity_ck(**{"executive-report.pdf": "f" * 64})
    out = validate_acceptance_binding(
        prior, pack_run_id="run-1", rc_sha="e" * 40, pack_checksums=pack_ck
    )
    assert out["binding"]["valid"] is False
    assert "checksum_mismatch:executive-report.pdf" in out["binding"]["mismatches"]


def test_binding_invalid_on_run_id_divergence() -> None:
    """6. run_id divergente → binding invalid."""
    prior = _accepted_base()
    out = validate_acceptance_binding(
        prior,
        pack_run_id="other-run",
        rc_sha="e" * 40,
        pack_checksums=_full_identity_ck(),
    )
    assert out["binding"]["valid"] is False
    assert any(m.startswith("run_id:") for m in out["binding"]["mismatches"])


def test_binding_invalid_on_product_rc_sha_divergence() -> None:
    """7. product_rc_sha divergente → binding invalid."""
    prior = _accepted_base()
    out = validate_acceptance_binding(
        prior,
        pack_run_id="run-1",
        rc_sha="f" * 40,
        pack_checksums=_full_identity_ck(),
    )
    assert out["binding"]["valid"] is False
    assert any("product_rc_sha" in m for m in out["binding"]["mismatches"])


def test_binding_valid_when_all_identity_present_and_equal() -> None:
    """8. Todos presentes e idênticos → binding.valid=true."""
    ck = _full_identity_ck()
    prior = _accepted_base()
    out = validate_acceptance_binding(
        prior, pack_run_id="run-1", rc_sha="e" * 40, pack_checksums=ck
    )
    assert out["status"] == "ACCEPTED"
    assert out["binding"]["valid"] is True
    assert out["binding"].get("mismatches") == []


def test_agent_cannot_register_accepted() -> None:
    """9. Um agente não consegue registrar ACCEPTED."""
    for who in ("agent", "auto", "system", "null", None, ""):
        prior = _accepted_base()
        prior["accepted_by"] = who
        out = validate_acceptance_binding(
            prior,
            pack_run_id="run-1",
            rc_sha="e" * 40,
            pack_checksums=_full_identity_ck(),
        )
        assert out["status"] == "PENDING_HUMAN", who
        assert out["binding"]["valid"] is False, who
        assert out.get("accepted_by") in (None, ""), who


def test_later_doc_commits_do_not_invalidate_frozen_product_rc_sha() -> None:
    """10. Commits documentais posteriores não invalidam product_rc_sha congelado.

    Binding uses pack-manifest git_sha / freeze rc_sha, not HEAD tip.
    """
    frozen = FROZEN_RC_PRODUCT_SHA
    head_tip = "5aa77eb9deadbeefdeadbeefdeadbeefdeadbeef"  # later docs tip
    ck = _full_identity_ck()
    prior = {
        "status": "ACCEPTED",
        "accepted_by": "Tiago Sasaki",
        "accepted_at": "2026-07-24T21:40:15Z",
        "run_id": FROZEN_RC_RUN_ID,
        "rc_sha": frozen,
        "package_checksums": ck,
    }
    out = validate_acceptance_binding(
        prior,
        pack_run_id=FROZEN_RC_RUN_ID,
        rc_sha=frozen,
        pack_checksums=ck,
    )
    assert out["status"] == "ACCEPTED"
    assert out["binding"]["valid"] is True
    assert out["binding"]["product_rc_sha"] == frozen
    assert out["binding"]["product_rc_sha"] != head_tip
    bad = validate_acceptance_binding(
        prior,
        pack_run_id=FROZEN_RC_RUN_ID,
        rc_sha=head_tip,
        pack_checksums=ck,
    )
    assert bad["binding"]["valid"] is False
    assert any("product_rc_sha" in m for m in bad["binding"]["mismatches"])


def test_identity_mismatches_not_both_present_short_circuit() -> None:
    """Regression: 'if key in both' is not sufficient — missing either side fails."""
    accepted = {"pack-manifest.json": "a" * 64}
    pack = {"pack-manifest.json": "a" * 64}
    ms = identity_checksum_mismatches(accepted, pack)
    assert "missing_expected_checksum:executive-summary.md" in ms
    assert "missing_expected_checksum:consulting-pack.xlsx" in ms
    assert "missing_expected_checksum:executive-report.pdf" in ms
    accepted2 = _full_identity_ck()
    pack2 = _full_identity_ck()
    del pack2["executive-report.pdf"]
    ms2 = identity_checksum_mismatches(accepted2, pack2)
    assert "missing_actual_artifact:executive-report.pdf" in ms2


def test_verify_accept_fails_without_frozen_binaries(tmp_path: Path) -> None:
    """CLI verify-accept fails when local tree lacks required frozen binaries."""
    out = tmp_path / "campaign"
    pack = out / "pack"
    pack.mkdir(parents=True)
    (pack / "pack-manifest.json").write_text(
        json.dumps({"run_id": "r1", "git_sha": "a" * 40}), encoding="utf-8"
    )
    (pack / "executive-summary.md").write_text("summary\n", encoding="utf-8")
    ua = {
        "status": "PENDING_HUMAN",
        "run_id": "r1",
        "rc_sha": "a" * 40,
        "package_checksums": {},
        "accepted_by": None,
        "accepted_at": None,
    }
    (out / "user-acceptance.json").write_text(json.dumps(ua), encoding="utf-8")
    code = main(["verify-accept", "--out", str(out)])
    assert code == 1
    missing = set(missing_required_frozen_binaries(pack))
    assert "consulting-pack.xlsx" in missing
    assert "executive-report.pdf" in missing


def test_verify_accept_pack_dir_option(tmp_path: Path) -> None:
    """--pack-dir validates extracted artifact without putting binaries in git pack/."""
    import hashlib

    out = tmp_path / "campaign"
    out.mkdir()
    art = tmp_path / "extracted-artifact"
    art.mkdir()
    pdf = b"%PDF-1.4 frozen-rc"
    xlsx = b"PK\x03\x04frozen-xlsx"
    (art / "executive-report.pdf").write_bytes(pdf)
    (art / "consulting-pack.xlsx").write_bytes(xlsx)
    summary = "executive summary freeze\n"
    (art / "executive-summary.md").write_text(summary, encoding="utf-8")

    def h(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    manifest = {
        "run_id": FROZEN_RC_RUN_ID,
        "git_sha": FROZEN_RC_PRODUCT_SHA,
        "reconcile": {"status": "PASS"},
    }
    (art / "pack-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    ck = {
        "pack-manifest.json": h((art / "pack-manifest.json").read_bytes()),
        "executive-summary.md": h(summary.encode()),
        "consulting-pack.xlsx": h(xlsx),
        "executive-report.pdf": h(pdf),
    }
    ua = {
        "status": "PENDING_HUMAN",
        "run_id": FROZEN_RC_RUN_ID,
        "rc_sha": FROZEN_RC_PRODUCT_SHA,
        "package_checksums": ck,
        "accepted_by": None,
        "accepted_at": None,
        "agent_auto_accept_forbidden": True,
    }
    (out / "user-acceptance.json").write_text(json.dumps(ua, indent=2), encoding="utf-8")
    (out / "package-reconciliation.json").write_text(
        json.dumps({"status": "PASS", "run_id": FROZEN_RC_RUN_ID}), encoding="utf-8"
    )
    (out / "recurrence.json").write_text(
        json.dumps(
            {
                "mode": "LABELED_DETERMINISTIC_REPLAY",
                "live_dual_snapshot": False,
            }
        ),
        encoding="utf-8",
    )
    (out / "pack").mkdir()
    code = main(["verify-accept", "--out", str(out), "--pack-dir", str(art)])
    assert code == 2
    refreshed = json.loads((out / "user-acceptance.json").read_text(encoding="utf-8"))
    assert refreshed["status"] == "PENDING_HUMAN"
    assert refreshed["accepted_by"] is None


def test_assemble_frozen_rc_produces_identity(tmp_path: Path) -> None:
    """assemble_client_ready_frozen_rc extracts exact freeze bytes (git snapshot)."""
    import hashlib

    staging = tmp_path / "staging"
    result = assemble_client_ready_frozen_rc(
        out_dir=ROOT / "artifacts/campaigns" / CAMPAIGN_ID,
        staging_dir=staging,
    )
    assert result["status"] in {
        "READY_FOR_ACTUAL_HUMAN_PRODUCT_REVIEW",
        BLOCKED_MISSING_FROZEN_RC,
    }
    if result["status"] == BLOCKED_MISSING_FROZEN_RC:
        pytest.skip(f"freeze snapshot unavailable in this clone: {result}")
    assert result["artifact_name"] == FROZEN_RC_ARTIFACT_NAME
    assert result["run_id"] == FROZEN_RC_RUN_ID
    assert result["product_rc_sha"] == FROZEN_RC_PRODUCT_SHA
    assert result["production_touched"] is False
    assert result["soak_touched"] is False
    assert (staging / "ARTIFACT-IDENTITY.json").is_file()
    identity = json.loads((staging / "ARTIFACT-IDENTITY.json").read_text(encoding="utf-8"))
    assert identity["classification"] == "HUMAN_REVIEW_ARTIFACT"
    assert identity["production_touched"] is False
    assert (staging / "executive-report.pdf").is_file()
    assert (staging / "consulting-pack.xlsx").is_file()
    ua = json.loads(
        (ROOT / "artifacts/campaigns" / CAMPAIGN_ID / "user-acceptance.json").read_text(
            encoding="utf-8"
        )
    )
    for name in ("executive-report.pdf", "consulting-pack.xlsx"):
        digest = hashlib.sha256((staging / name).read_bytes()).hexdigest()
        assert digest == ua["package_checksums"][name]


def test_pending_human_preserved_in_repo() -> None:
    """Campaign user-acceptance remains PENDING_HUMAN (no agent ACCEPTED)."""
    path = ROOT / "artifacts/campaigns" / CAMPAIGN_ID / "user-acceptance.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "PENDING_HUMAN"
    assert data.get("accepted_by") is None
    assert data.get("accepted_at") is None
    assert data["run_id"] == FROZEN_RC_RUN_ID
    assert data["rc_sha"] == FROZEN_RC_PRODUCT_SHA
    for key in REQUIRED_IDENTITY_FILES:
        assert key in data["package_checksums"]


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
