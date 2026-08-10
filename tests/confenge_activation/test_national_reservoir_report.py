"""National reservoir funnel pack + hot-set independent of ESR size."""

from __future__ import annotations

from scripts.confenge_activation.national_reservoir_report import (
    build_artifact_pack,
    build_funnel_rows,
    write_artifact_pack,
)
from scripts.confenge_activation.planner import select_hot_set


def test_funnel_rows_closed_percentages() -> None:
    metrics = {
        "national_universe": 48748,
        "target_fit_eligible": 48748,
        "target_fit_dirty_enqueued": 1000,
        "target_fit_processed": 900,
        "target_fit_materialized": 1038,
        "target_confirmed": 156,
        "target_probable": 609,
        "target_out": 273,
        "contact_attempted": 80,
        "contact_never_attempted": 76,
        "email_candidate": 50,
        "real_email": 45,
        "company_owned": 41,
        "identity_safe": 41,
        "provenance_valid": 41,
        "service_fit": 41,
        "copy_context": 41,
        "email_send_ready": 41,
        "warmbly_imported": 41,
        "warmbly_eligible": 0,
        "active_hot_set": 10,
        "loss_reasons": {},
    }
    rows = build_funnel_rows(metrics)
    by_key = {r["key"]: r for r in rows}
    assert by_key["national_universe"]["count"] == 48748
    assert by_key["email_send_ready"]["count"] == 41
    # ESR % of national is small — honest, not capped at 50 as goal
    assert by_key["email_send_ready"]["pct_of_national"] is not None
    assert by_key["email_send_ready"]["pct_of_national"] < 1.0


def test_write_artifact_pack(tmp_path) -> None:  # noqa: ANN001
    metrics = {
        "national_universe": 100,
        "target_fit_eligible": 100,
        "target_fit_materialized": 80,
        "target_confirmed": 20,
        "contact_attempted": 10,
        "contact_never_attempted": 10,
        "email_send_ready": 5,
        "active_hot_set": 3,
        "loss_reasons": {"contact_attempted": {"no_email_found": 5}},
        "target_fit_coverage": {
            "coverage_ratio": 0.8,
            "coverage_mode": "PARTIAL",
            "FULL_NATIONAL_READY": False,
        },
        "contact_coverage": {"TARGET_CONFIRMED_total": 20, "email_send_ready": 5},
        "service_distribution": {"distribution": []},
        "reservoir_health": {"coverage_mode": "PARTIAL"},
        "pilot_go": False,
        "national_reservoir_healthy": False,
        "truncation_root_cause": "test root cause",
    }
    out = write_artifact_pack(metrics, tmp_path)
    assert (out / "FUNNEL.md").is_file()
    assert (out / "LOSS-REASONS.json").is_file()
    assert (out / "SERVICE-DISTRIBUTION.json").is_file()
    assert (out / "TARGET-FIT-COVERAGE.json").is_file()
    assert (out / "CONTACT-COVERAGE.json").is_file()
    assert (out / "RESERVOIR-HEALTH.json").is_file()
    text = (out / "FUNNEL.md").read_text(encoding="utf-8")
    assert "EMAIL_SEND_READY" in text
    assert "PILOT_GO" in text
    pack = build_artifact_pack(metrics)
    assert pack["RESERVOIR-HEALTH.json"]["warmbly_capacity_per_hour"] == 10


def test_hot_set_capacity_independent_of_large_reservoir() -> None:
    """Hot set is capacity-aware; large EMAIL_SEND_READY does not force huge hot set."""
    from scripts.confenge_activation.models import ActivationProjection
    from scripts.confenge_activation.policy import load_policy

    policy = load_policy()
    projections: list[ActivationProjection] = []
    for i in range(200):
        projections.append(
            ActivationProjection(
                cnpj14=f"{i:08d}0001{i % 10:02d}",
                activation_state="ACTIONABLE_NOW",
                activation_score=90.0,
                reason_codes=["test"],
                evaluated_at="2026-08-10T00:00:00Z",
                next_best_action_at=None,
                expires_at=None,
                source_hash=f"h{i}",
                trigger_hash=f"t{i}",
                policy_version=getattr(policy, "version", "v1"),
                company_key=f"cnpj_root:{i:08d}",
                cnpj_raiz=f"{i:08d}",
            )
        )
    # capacity_override bounds hot set only — reservoir size stays 200
    hot = select_hot_set(projections, policy=policy, capacity_override=10)
    assert len(hot) <= 10
    assert len(projections) == 200
