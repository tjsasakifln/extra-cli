"""CLI structural tests + additional invariants without requiring live DB."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.confenge_target_fit.cli import build_parser
from scripts.confenge_target_fit.company_key import (
    canary_bucket,
    company_key_from_raiz,
    is_consortium_contract,
)
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.transitions import classify_event_type


ROOT = Path(__file__).resolve().parents[2]


def test_cli_subcommands_present():
    p = build_parser()
    # argparse doesn't expose easily; parse help via choices by trying each
    for cmd in (
        "refresh",
        "worker",
        "reconcile",
        "status",
        "explain",
        "requeue",
        "set-mode",
        "metrics",
        "shadow-export",
        "version",
    ):
        args = p.parse_args([cmd] if cmd not in {"explain", "requeue", "set-mode"} else (
            [cmd, "--cnpj", "12345678000199"] if cmd != "set-mode" else [cmd, "SHADOW"]
        ))
        assert args.cmd == cmd


def test_migration_file_exists_and_defines_core_tables():
    mig = ROOT / "db/migrations/071_confenge_target_fit_continuous_refresh.sql"
    assert mig.is_file()
    text = mig.read_text(encoding="utf-8")
    for table in (
        "confenge_target_fit_dirty",
        "confenge_company_target_fit_current",
        "confenge_company_target_fit_history",
        "confenge_target_fit_events",
        "confenge_target_fit_shadow",
        "confenge_target_fit_downstream_invalidation",
        "confenge_target_fit_control",
    ):
        assert table in text


def test_systemd_units_exist():
    d = ROOT / "deploy/systemd"
    for name in (
        "extra-confenge-target-fit-refresh.service",
        "extra-confenge-target-fit-refresh.timer",
        "extra-confenge-target-fit-worker.service",
        "extra-confenge-target-fit-reconcile.service",
        "extra-confenge-target-fit-reconcile.timer",
    ):
        path = d / name
        assert path.is_file(), name
        body = path.read_text(encoding="utf-8")
        assert "extra-cli" in body or "TARGET_FIT" in body or "confenge_target_fit" in body


def test_docs_exist():
    doc = ROOT / "docs/confenge/TARGET-FIT-CONTINUOUS-REFRESH.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "TARGET_FIT = derived state of the datalake" in text
    assert "SHADOW" in text
    assert "EMAIL_SEND_READY" in text


def test_hook_is_soft_fail_boundary():
    """Hook module must catch exceptions so ETL never rolls back."""
    path = ROOT / "scripts/confenge_target_fit/hook_after_datalake.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # ensure notify_datalake_committed has a try/except
    fn = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "notify_datalake_committed"
    ][0]
    assert any(isinstance(n, ast.Try) for n in fn.body)


def test_config_defaults_conservative():
    cfg = TargetFitRefreshConfig()
    assert cfg.async_mode == "SHADOW"
    assert cfg.batch_size <= 100
    assert cfg.workers <= 4
    assert cfg.stale_blocks_send is True


def test_event_types_for_transitions():
    from scripts.confenge_target_fit import (
        EVT_CONFIRMED,
        EVT_DOWNGRADE,
        EVT_LOST,
        EVT_UNCHANGED,
    )

    assert (
        classify_event_type(
            old_class="TARGET_OUT_OF_SCOPE",
            new_class="TARGET_CONFIRMED",
            old_version="v1",
            new_version="v1",
            old_evidence=[],
            new_evidence=[{"id": "1"}],
        )
        == EVT_CONFIRMED
    )
    assert (
        classify_event_type(
            old_class="TARGET_CONFIRMED",
            new_class="TARGET_OUT_OF_SCOPE",
            old_version="v1",
            new_version="v1",
            old_evidence=[{"id": "1"}],
            new_evidence=[],
        )
        == EVT_LOST
    )
    assert (
        classify_event_type(
            old_class="TARGET_CONFIRMED",
            new_class="TARGET_PROBABLE_RESEARCH",
            old_version="v1",
            new_version="v1",
            old_evidence=[],
            new_evidence=[],
        )
        == EVT_DOWNGRADE
    )
    assert (
        classify_event_type(
            old_class="TARGET_CONFIRMED",
            new_class="TARGET_CONFIRMED",
            old_version="v1",
            new_version="v1",
            old_evidence=[{"id": "1"}],
            new_evidence=[{"id": "1"}],
        )
        == EVT_UNCHANGED
    )


def test_company_key_roundtrip():
    k = company_key_from_raiz("12345678")
    assert k == "cnpj_root:12345678"
    assert canary_bucket(k) == canary_bucket(k)


def test_consortium_detection():
    assert is_consortium_contract(
        {"objeto_contrato": "obras em consorcio", "fornecedor_nome": "X"}
    )
    assert not is_consortium_contract(
        {"objeto_contrato": "pavimentacao", "fornecedor_nome": "CONSTRUTORA X"}
    )


def test_target_fit_module_exports_pr211_contract():
    from scripts.confenge_universe import target_fit as tf

    assert tf.TARGET_CONFIRMED == "TARGET_CONFIRMED"
    assert tf.TARGET_PROBABLE_RESEARCH == "TARGET_PROBABLE_RESEARCH"
    assert tf.TARGET_OUT_OF_SCOPE == "TARGET_OUT_OF_SCOPE"
    assert hasattr(tf, "classify_target_fit")
    assert hasattr(tf, "TARGET_FIT_VERSION")
