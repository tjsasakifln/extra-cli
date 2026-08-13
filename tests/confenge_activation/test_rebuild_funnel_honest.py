"""Honest funnel rebuild: no synthetic keys, no pilot hard-code theater."""

from __future__ import annotations

import inspect

from scripts.confenge_activation import rebuild_national_funnel as rnf
from scripts.confenge_contact_resolution.contact_coverage import measure_contact_coverage


def test_measure_contact_coverage_uses_real_keys_not_synthetic() -> None:
    m = measure_contact_coverage(
        population_keys=["11222333", "44555666", "77888999"],
        attempted_keys=["11222333"],
        real_email_keys=["11222333"],
        company_owned_keys=["11222333"],
        identity_safe_keys=["11222333"],
        email_send_ready_keys=[],
        rejection_reasons={"mailbox_purpose_rejected": 0},
    )
    assert m["TARGET_CONFIRMED_total"] == 3
    assert m["contact_discovery_attempted"] == 1
    assert m["contact_discovery_not_attempted"] == 2
    assert m["closed_sum_check"]["confirmed_eq_attempted_plus_never"] is True
    assert m["email_send_ready"] == 0


def test_rebuild_source_has_no_synthetic_c_keys() -> None:
    src = inspect.getsource(rnf.gather_live_metrics)
    assert 'f"c{i}"' not in src
    assert "c0" not in src
    assert "min(confirmed, 41)" not in src
    assert "attempted_est" not in src
    assert 'raiz + "000100"' not in inspect.getsource(rnf)


def test_universe_query_counts_null_lineage_as_mismatch() -> None:
    sql = rnf._universe_closure_query("ACTIVE")
    assert sql.count("IS DISTINCT FROM %s") == 4
    assert "target_refresh_failed" in sql
    assert "target_recompute_required" in sql


def test_rebuild_source_calls_evaluate_email_send_ready() -> None:
    src = inspect.getsource(rnf)
    assert "evaluate_email_send_ready" in src
    assert "is_mailbox_send_allowed" in src
    assert "select_services" in src


def test_national_universe_label_not_fake_construction_only() -> None:
    src = inspect.getsource(rnf.gather_live_metrics)
    assert "pncp_supplier" in src or "supplier" in src.lower()
    assert "construction_roots" in src


def test_all_target_classes_count_toward_materialized_universe() -> None:
    src = inspect.getsource(rnf.gather_live_metrics)
    assert "TARGET_INSUFFICIENT_EVIDENCE" in src
    assert "materialized = sum(target_classes.values())" in src
    assert "universe_manifest" in src
    assert 'isolation_level="REPEATABLE READ"' in src
    assert "txid_current_snapshot()" in src
    assert "sector_classes[CONSTRUCTION_CONFIRMED]" in src
    assert "construction_universe_derivation" in src
    assert "TARGET_CONFIRMED+TARGET_PROBABLE_RESEARCH" not in src
