"""Canonical universe and controlled-pilot policy invariants."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_activation.pilot_go_policy import (
    build_universe_manifest,
    evaluate_pilot_go,
    load_human_review_decisions,
    validate_universe_manifest,
)


def _classes() -> dict[str, int]:
    return {
        "TARGET_CONFIRMED": 8_348,
        "TARGET_PROBABLE_RESEARCH": 24_984,
        "TARGET_OUT_OF_SCOPE": 93_676,
        "TARGET_INSUFFICIENT_EVIDENCE": 386_642,
    }


def _manifest() -> dict:
    return build_universe_manifest(
        observed_supplier_roots=513_650,
        materialized_roots=513_650,
        target_classes=_classes(),
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        target_fit_version="confenge-target-fit-v2",
        database_snapshot="123:123:",
        construction_commercial_roots=48_748,
    )


def test_universe_manifest_closes_all_classes_without_using_reserve() -> None:
    manifest = _manifest()
    assert validate_universe_manifest(manifest) == []
    assert manifest["observed_supplier_roots"] == 513_650
    assert manifest["construction_commercial_roots"] == 48_748
    assert manifest["target_class_sum"] == 513_650
    assert "minimum_operational_reserve" not in manifest
    assert "send_ready_reserve" not in manifest


def test_full_scale_manifest_requires_atomic_database_snapshot() -> None:
    manifest = build_universe_manifest(
        observed_supplier_roots=513_650,
        materialized_roots=513_650,
        target_classes=_classes(),
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        target_fit_version="confenge-target-fit-v2",
        construction_commercial_roots=48_748,
    )

    assert "invariant_false:atomic_database_snapshot_present" in validate_universe_manifest(manifest)


def test_subset_sizes_never_change_universe_denominators() -> None:
    manifest = _manifest()
    before = (
        manifest["observed_supplier_roots"],
        manifest["construction_commercial_roots"],
        manifest["target_class_sum"],
    )
    for validation_subset in (10, 20, 50, 100, 900):
        assert validation_subset <= manifest["observed_supplier_roots"]
        assert before == (
            manifest["observed_supplier_roots"],
            manifest["construction_commercial_roots"],
            manifest["target_class_sum"],
        )
    assert manifest["subset_policy"]["subsets_may_not_change_universe_counts"] is True


def test_class_gap_fails_universe_reconciliation() -> None:
    classes = _classes()
    classes["TARGET_INSUFFICIENT_EVIDENCE"] -= 1
    manifest = build_universe_manifest(
        observed_supplier_roots=513_650,
        materialized_roots=513_649,
        target_classes=classes,
        source_contract_rows=4_400_000,
        datalake_watermark="2026-08-10T12:00:00Z",
        target_fit_version="confenge-target-fit-v2",
        database_snapshot="123:123:",
    )
    errors = validate_universe_manifest(manifest)
    assert "invariant_false:class_sum_equals_observed_supplier_roots" in errors
    assert "invariant_false:materialized_equals_observed_supplier_roots" in errors


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
    assert legacy["GO_FOR_REAL_CONFENGE_EMAIL_PILOT"] is False
