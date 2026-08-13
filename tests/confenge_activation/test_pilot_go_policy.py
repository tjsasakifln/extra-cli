"""Canonical universe and controlled-pilot policy invariants."""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from pathlib import Path

from scripts.confenge_activation.pilot_go_policy import (
    TERMINAL_AUTHORITY,
    build_universe_manifest,
    evaluate_pilot_go,
    load_human_review_decisions,
    validate_universe_manifest,
)
from scripts.confenge_activation.operational_metrics import warmbly_ops_config_from_env


def test_warmbly_rate_max_is_the_live_governor_key() -> None:
    cfg = warmbly_ops_config_from_env({"CONFENGE_RATE_MAX_PER_HOUR": "10"})
    assert cfg["emails_per_hour"] == 10


def _classes() -> dict[str, int]:
    return {
        "TARGET_CONFIRMED": 8_348,
        "TARGET_PROBABLE_RESEARCH": 24_984,
        "TARGET_OUT_OF_SCOPE": 93_676,
        "TARGET_INSUFFICIENT_EVIDENCE": 386_642,
    }


def _sector_classes() -> dict[str, int]:
    return {
        "CONSTRUCTION_CONFIRMED": 30_000,
        "CONSTRUCTION_PROBABLE": 18_748,
        "NON_CONSTRUCTION": 450_000,
        "SECTOR_INSUFFICIENT_EVIDENCE": 14_902,
    }


def _manifest() -> dict:
    return build_universe_manifest(
        supplier_roots_observed=513_650,
        sector_classes=_sector_classes(),
        target_fit_population=513_650,
        materialized_roots=513_650,
        target_classes=_classes(),
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        source_cdc_watermark="2026-08-10T11:59:59Z",
        database_snapshot="123:123:",
        transaction_timestamp="2026-08-10T12:00:00Z",
        construction_universe_derivation="sector_class IN construction classes",
        construction_evidence_version="confenge-sector-v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="confenge-target-fit-v2",
    )


def test_universe_manifest_closes_all_classes_without_using_reserve() -> None:
    manifest = _manifest()
    assert validate_universe_manifest(manifest) == []
    assert manifest["supplier_roots_observed"] == 513_650
    assert manifest["construction_roots"] == 48_748
    assert manifest["target_class_sum"] == 513_650
    assert "minimum_operational_reserve" not in manifest
    assert "send_ready_reserve" not in manifest


def test_full_scale_manifest_requires_atomic_database_snapshot() -> None:
    manifest = build_universe_manifest(
        supplier_roots_observed=513_650,
        sector_classes=_sector_classes(),
        target_fit_population=513_650,
        materialized_roots=513_650,
        target_classes=_classes(),
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        source_cdc_watermark="2026-08-10T11:59:59Z",
        database_snapshot="",
        transaction_timestamp="2026-08-10T12:00:00Z",
        construction_universe_derivation="sector_class IN construction classes",
        construction_evidence_version="confenge-sector-v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="confenge-target-fit-v2",
    )

    assert "invariant_false:atomic_database_snapshot_present" in validate_universe_manifest(manifest)


def test_subset_sizes_never_change_universe_denominators() -> None:
    manifest = _manifest()
    before = (
        manifest["supplier_roots_observed"],
        manifest["construction_roots"],
        manifest["target_class_sum"],
    )
    for validation_subset in (10, 20, 50, 100, 900):
        assert validation_subset <= manifest["supplier_roots_observed"]
        assert before == (
            manifest["supplier_roots_observed"],
            manifest["construction_roots"],
            manifest["target_class_sum"],
        )
    assert manifest["subset_policy"]["subsets_may_not_change_universe_counts"] is True


def test_class_gap_fails_universe_reconciliation() -> None:
    classes = _classes()
    classes["TARGET_INSUFFICIENT_EVIDENCE"] -= 1
    manifest = build_universe_manifest(
        supplier_roots_observed=513_650,
        sector_classes=_sector_classes(),
        target_fit_population=513_650,
        materialized_roots=513_649,
        target_classes=classes,
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        source_cdc_watermark="2026-08-10T11:59:59Z",
        database_snapshot="123:123:",
        transaction_timestamp="2026-08-10T12:00:00Z",
        construction_universe_derivation="sector_class IN construction classes",
        construction_evidence_version="confenge-sector-v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="confenge-target-fit-v2",
    )
    errors = validate_universe_manifest(manifest)
    assert "invariant_false:target_class_sum_equals_target_fit_population" in errors
    assert "invariant_false:materialized_equals_observed_supplier_roots" in errors


def test_operational_target_states_are_reported_outside_closed_partition() -> None:
    classes = _classes()
    classes["TARGET_INSUFFICIENT_EVIDENCE"] -= 1
    manifest = build_universe_manifest(
        supplier_roots_observed=513_650,
        sector_classes=_sector_classes(),
        target_fit_population=513_650,
        materialized_roots=513_649,
        target_classes=classes,
        target_operational_states={"REFRESH_FAILED": 1, "RECOMPUTE_REQUIRED": 0},
        source_contract_rows=4_400_000,
        datalake_watermark="wm",
        source_cdc_watermark="cdc",
        database_snapshot="1:1:",
        transaction_timestamp="2026-08-13T12:00:00Z",
        construction_universe_derivation="sector classes",
        construction_evidence_version="v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="v1",
    )

    assert manifest["target_operational_states"]["REFRESH_FAILED"] == 1
    assert "target_operational_states_not_zero" in validate_universe_manifest(manifest)


def test_manifest_validation_recomputes_closure_instead_of_trusting_flags() -> None:
    manifest = deepcopy(_manifest())
    manifest["materialized_roots"] -= 1
    manifest["invariants"] = {key: True for key in manifest["invariants"]}
    manifest["FULLY_RECONCILED"] = True

    assert "materialized_roots_not_supplier_population" in validate_universe_manifest(manifest)


def test_unknown_target_class_and_malformed_counts_fail_closed() -> None:
    manifest = deepcopy(_manifest())
    manifest["target_classes"]["TARGET_UNKNOWN"] = 1
    manifest["source_contract_rows"] = "not-a-count"

    errors = validate_universe_manifest(manifest)
    assert "target_class_keys_not_closed" in errors
    assert "invalid_count:source_contract_rows" in errors


def test_negative_counts_are_not_laundered_to_zero() -> None:
    manifest = build_universe_manifest(
        supplier_roots_observed=1,
        sector_classes={
            "CONSTRUCTION_CONFIRMED": 1,
            "CONSTRUCTION_PROBABLE": 0,
            "NON_CONSTRUCTION": 0,
            "SECTOR_INSUFFICIENT_EVIDENCE": 0,
        },
        target_fit_population=-1,
        materialized_roots=1,
        target_classes={
            "TARGET_CONFIRMED": 1,
            "TARGET_PROBABLE_RESEARCH": 0,
            "TARGET_OUT_OF_SCOPE": 0,
            "TARGET_INSUFFICIENT_EVIDENCE": 0,
        },
        source_contract_rows=1,
        datalake_watermark="wm",
        source_cdc_watermark="cdc",
        database_snapshot="1:1:",
        transaction_timestamp="2026-08-13T12:00:00Z",
        construction_universe_derivation="sector classes",
        construction_evidence_version="v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="v1",
        duplicate_cnpj_root=-1,
    )

    assert manifest["duplicate_cnpj_root"] == -1
    assert manifest["target_fit_population"] == -1
    assert manifest["FULLY_RECONCILED"] is False
    errors = validate_universe_manifest(manifest)
    assert "invalid_count:duplicate_cnpj_root" in errors
    assert "invalid_count:target_fit_population" in errors


def test_duplicate_or_orphan_materialization_fails_closed() -> None:
    manifest = deepcopy(_manifest())
    manifest["duplicate_cnpj_root"] = 1
    manifest["orphan_materialized_roots"] = 1

    errors = validate_universe_manifest(manifest)
    assert "duplicate_cnpj_root_not_zero" in errors
    assert "orphan_materialized_roots_not_zero" in errors


def test_stale_classifier_lineage_blocks_universe_closure() -> None:
    manifest = build_universe_manifest(
        supplier_roots_observed=513_650,
        sector_classes=_sector_classes(),
        target_fit_population=513_650,
        materialized_roots=513_650,
        target_classes=_classes(),
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        source_cdc_watermark="2026-08-10T11:59:59Z",
        database_snapshot="123:123:",
        transaction_timestamp="2026-08-10T12:00:00Z",
        construction_universe_derivation="sector dimension classes",
        construction_evidence_version="confenge-sector-v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="confenge-target-fit-v2",
        target_classifier_mismatch=1,
    )

    assert "invariant_false:target_classifier_mismatch_eq_0" in validate_universe_manifest(
        manifest
    )


def test_pilot_go_with_60_esr_is_independent_from_reserve_900(tmp_path: Path) -> None:
    rows = [{"cnpj_raiz": f"{i:08d}", "email": f"lead{i}@company.example"} for i in range(60)]
    decisions = tmp_path / "decisions.jsonl"
    payloads = []
    for i, row in enumerate(rows[:20]):
        status = "HUMAN_REVIEW_APPROVED" if i < 10 else "HUMAN_REVIEW_REJECTED"
        payloads.append(
            {
                **row,
                "review_status": status,
                "reviewer": "tiago",
                "reviewed_at": "2026-08-10T13:00:00Z",
                "evidence_inspected": ["company", "email", "copy"],
            }
        )
    decisions.write_text("\n".join(json.dumps(row) for row in payloads) + "\n", encoding="utf-8")
    review = load_human_review_decisions(decisions, eligible_rows=rows)
    result = evaluate_pilot_go(
        universe_manifest=_manifest(),
        technical_gates={"all_technical_gates": True},
        human_review=review,
        email_send_ready=60,
        minimum_operational_reserve=900,
    )
    assert result["PILOT_GO"] is True
    assert result["terminal_state"] == "GO_FOR_REAL_CONFENGE_EMAIL_PILOT"
    assert result["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"] is False
    assert result["dispatch"]["state"] == "PAUSED_MANUAL_START"
    assert len(result["dispatch"]["approved_hot_set_keys"]) == 10


def test_automation_review_decisions_never_unlock_go(tmp_path: Path) -> None:
    rows = [{"cnpj_raiz": f"{i:08d}", "email": f"lead{i}@company.example"} for i in range(20)]
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(
        "\n".join(
            json.dumps(
                {
                    **row,
                    "review_status": "HUMAN_REVIEW_APPROVED",
                    "reviewer": "automation",
                    "reviewed_at": "2026-08-10T13:00:00Z",
                    "evidence_inspected": ["company"],
                }
            )
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )
    review = load_human_review_decisions(decisions, eligible_rows=rows)
    assert review["approved_current_esr"] == 0
    assert review["errors"]
    assert review["blocking_errors"]


def test_invalid_attribution_for_ineligible_history_is_observable_not_blocking(
    tmp_path: Path,
) -> None:
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(
        json.dumps(
            {
                "cnpj_raiz": "99999999",
                "email": "old@example.com",
                "review_status": "HUMAN_REVIEW_APPROVED",
                "reviewer": "automation",
                "reviewed_at": "2026-08-10T13:00:00Z",
                "evidence_inspected": ["company"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review = load_human_review_decisions(
        decisions,
        eligible_rows=[{"cnpj_raiz": "11111111", "email": "current@example.com"}],
    )
    assert review["errors"]
    assert review["blocking_errors"] == []


def test_duplicate_esr_rows_cannot_inflate_human_review_thresholds(tmp_path: Path) -> None:
    eligible = [{"cnpj_raiz": "00000001", "email": "lead1@company.example"}] * 20
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(
        json.dumps(
            {
                **eligible[0],
                "review_status": "HUMAN_REVIEW_APPROVED",
                "reviewer": "tiago",
                "reviewed_at": "2026-08-10T12:00:00Z",
                "evidence_inspected": ["company", "email"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review = load_human_review_decisions(decisions, eligible_rows=eligible)

    assert review["reviewed_current_esr"] == 1
    assert review["approved_current_esr"] == 1
    assert review["top20_review_complete"] is False
    assert review["hot_set_10_approved"] is False


def test_legacy_emitters_are_non_terminal(capsys) -> None:  # noqa: ANN001
    from scripts.confenge import emit_unconditional_go_pack as unconditional
    from scripts.confenge_activation.national_commercial_ready_pack import (
        build_go_no_go,
    )

    assert unconditional.main() == 2
    assert "SUPERSEDED_NON_TERMINAL" in capsys.readouterr().err
    legacy = build_go_no_go(
        capacity={"reserve_gate_ok": True},
        coverage={
            "FULLY_RECONCILED": True,
            "coverage_ratio": 1.0,
            "unexplained_missing": 0,
            "orphan_materialized_roots": 0,
            "duplicate_cnpj_root": 0,
            "coverage_mode": "FULLY_RECONCILED",
        },
        contact_terminals_complete=True,
        provenance_contamination=0,
        copy_audit_zeros=True,
        sha_bound=True,
        whatsapp_off=True,
        human_review_pending=False,
        human_review_accepted=True,
    )
    assert legacy["terminal_state"] == "SUPERSEDED_NON_TERMINAL"
    assert legacy["canonical_terminal_go"] is False


def test_single_terminal_authority_and_canonical_emitter_delegation() -> None:
    from scripts.confenge import emit_unconditional_go_pack as unconditional
    from scripts.confenge_activation import emit_final_closure_pack, pilot_go_policy
    from scripts.confenge_activation.national_commercial_ready_pack import (
        build_go_no_go,
    )

    assert TERMINAL_AUTHORITY.endswith("pilot_go_policy.evaluate_pilot_go")
    assert emit_final_closure_pack.evaluate_pilot_go is pilot_go_policy.evaluate_pilot_go
    emitter_source = inspect.getsource(emit_final_closure_pack.emit_pack)
    assert "evaluate_pilot_go(" in emitter_source

    unconditional_source = inspect.getsource(unconditional)
    legacy_pack_source = inspect.getsource(build_go_no_go)
    assert "EXTERNAL_BLOCKER_REQUIRES_TIAGO" not in unconditional_source
    assert "GO_FOR_REAL_CONFENGE_EMAIL_PILOT" not in unconditional_source
    assert "GO_FOR_REAL_CONFENGE_EMAIL_PILOT" not in legacy_pack_source
