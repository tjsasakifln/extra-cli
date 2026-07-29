"""Live-data fail-closed invariants for Extra weekly collection.

Covers:
  D4 — no silent SC fallback when canonical 200km universe unavailable
  D5 — UF unknown stays unknown (never imputed as SC for PNCP/generic)
  D3/D6 — success_zero / empty products require explicit complete scope
  Incremental checkpoint — refuse silent foreign/wrong resume
  PNCP open-proposal forward horizon
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.collect.run_contract import CollectionRun, classify_terminal_status
from scripts.ops.weekly_cycle import (
    EXIT_TECH,
    EXIT_UNRELIABLE,
    StageResult,
    _EXTRA_UNIVERSE_ORGAO,
    _write_csv,
    compute_exit_code,
    stage_intelligence,
)


# ---------------------------------------------------------------------------
# D4 — canonical universe / no SC fallback
# ---------------------------------------------------------------------------


def test_extra_universe_sql_requires_raio_and_sc() -> None:
    sql = _EXTRA_UNIVERSE_ORGAO
    assert "raio_200km" in sql
    assert "sc_public_entities" in sql
    assert "orgao_cnpj_8" in sql


def test_stage_intelligence_fails_when_universe_not_1093() -> None:
    """universe_n != 1093 → fail with CANONICAL_200KM_UNIVERSE_UNAVAILABLE, no SC SQL."""
    conn = MagicMock()
    # Opportunity query returns empty; universe count returns 0
    call_n = {"i": 0}

    def fake_q(_conn, sql, params=None):  # noqa: ANN001
        call_n["i"] += 1
        s = " ".join(str(sql).split())
        if "COUNT(*)" in s and "raio_200km" in s and "sc_public_entities" in s:
            return [{"n": 0}]
        # opportunity / orgaos selects
        return []

    import scripts.ops.weekly_cycle as wc

    monkey_q = fake_q
    original = wc._q
    wc._q = monkey_q  # type: ignore[assignment]
    try:
        result = stage_intelligence(conn, limit=5, collection_id="col-test")
    finally:
        wc._q = original  # type: ignore[assignment]

    assert result.status == "fail"
    assert result.error is not None
    assert "CANONICAL_200KM_UNIVERSE_UNAVAILABLE" in result.error
    assert result.detail.get("sc_uf_fallback") is False
    assert result.detail.get("contracts_scope_sql_applied") is False
    assert result.detail.get("contracts") == []
    assert result.detail.get("scope") == "CANONICAL_200KM_UNIVERSE_UNAVAILABLE"


def test_stage_intelligence_fails_when_universe_wrong_count() -> None:
    conn = MagicMock()

    def fake_q(_conn, sql, params=None):  # noqa: ANN001
        s = " ".join(str(sql).split())
        if "COUNT(*)" in s and "raio_200km" in s:
            return [{"n": 500}]  # not 1093
        return []

    import scripts.ops.weekly_cycle as wc

    original = wc._q
    wc._q = fake_q  # type: ignore[assignment]
    try:
        result = stage_intelligence(conn, limit=5)
    finally:
        wc._q = original  # type: ignore[assignment]

    assert result.status == "fail"
    assert "1093" in (result.error or "")
    assert "CANONICAL_200KM_UNIVERSE_UNAVAILABLE" in (result.error or "")


def test_exit_nonzero_when_intelligence_canonical_fail_strict() -> None:
    opp = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    opp.finish(
        records_obtained=3,
        records_persisted=3,
        request_completed=True,
        scope_complete=True,
    )
    stages = [
        StageResult(name="validate_db", status="ok"),
        StageResult(
            name="intelligence",
            status="fail",
            error="CANONICAL_200KM_UNIVERSE_UNAVAILABLE: universe_200km=12 != 1093",
        ),
        StageResult(
            name="delivery",
            status="ok",
            detail={
                "excel_ok": True,
                "checksums_file": "x",
                "product_checksums": {"a": {}},
            },
        ),
    ]
    assert compute_exit_code(stages, [opp], strict=True) == EXIT_TECH
    assert compute_exit_code(stages, [opp], strict=False) == EXIT_TECH


# ---------------------------------------------------------------------------
# D5 — UF never imputed as SC for PNCP / generic
# ---------------------------------------------------------------------------


def test_normalize_pncp_missing_uf_stays_unknown() -> None:
    from scripts.opportunity_intel.transformer import normalize_pncp

    raw = {
        "numeroControlePNCP": "x-1",
        "objeto": "Obra sem UF",
        "orgaoCNPJ": "12345678000199",
    }
    rec = normalize_pncp(raw)
    assert rec.uf in ("", None)
    assert rec.uf != "SC"


def test_normalize_pncp_empty_uf_stays_unknown() -> None:
    from scripts.opportunity_intel.transformer import normalize_pncp

    raw = {"id": "1", "objeto": "x", "uf": "", "UF": None}
    rec = normalize_pncp(raw)
    assert rec.uf != "SC"
    assert not rec.uf


def test_normalize_pncp_reads_unidade_orgao_uf() -> None:
    from scripts.opportunity_intel.transformer import normalize_pncp

    raw = {
        "numeroControlePNCP": "n-1",
        "objeto": "Com unidade",
        "unidadeOrgao": {"ufSigla": "PR", "municipioNome": "Curitiba"},
    }
    rec = normalize_pncp(raw)
    assert rec.uf == "PR"
    assert rec.municipio == "Curitiba"


def test_normalize_generic_missing_uf_not_sc() -> None:
    from scripts.opportunity_intel.transformer import normalize_generic

    rec = normalize_generic({"id": "g1", "objeto": "sem uf"}, "other")
    assert rec.uf != "SC"
    assert not rec.uf


def test_normalize_dom_sc_keeps_sc() -> None:
    """DOM-SC is territorially SC by source identity — allowed exception."""
    from scripts.opportunity_intel.transformer import normalize_dom_sc

    rec = normalize_dom_sc({"id": 1, "titulo": "Ato municipal"})
    assert rec.uf == "SC"
    assert rec.source == "dom_sc"


# ---------------------------------------------------------------------------
# D3/D6 — empty / success_zero fail-closed
# ---------------------------------------------------------------------------


def test_success_zero_requires_scope_and_no_error() -> None:
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=True,
            source_available=True,
            error=None,
        )
        == "success_zero"
    )
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=False,
            source_available=True,
            error=None,
        )
        == "partial"
    )
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=True,
            source_available=True,
            error="page timeout",
        )
        == "failure"
    )


def test_empty_csv_writes_explicit_zero_row_count(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    _write_csv(path, [])
    text = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "row_count" in text
    assert "0" in text
    # Not a blank file that could be confused with a failed write
    assert text.strip() != ""


def test_empty_csv_with_rows_keeps_headers(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    _write_csv(path, [{"a": 1, "b": 2}])
    text = path.read_text(encoding="utf-8")
    assert "a" in text and "b" in text
    assert "1" in text


# ---------------------------------------------------------------------------
# Incremental checkpoint — no silent foreign/wrong resume
# ---------------------------------------------------------------------------


def test_incremental_refuses_foreign_checkpoint_without_reset(tmp_path: Path) -> None:
    from scripts.crawl import run_contracts_incremental as inc
    from scripts.crawl.contracts_crawler import CrawlCheckpoint
    from scripts.crawl.run_contracts_90d_pilot import (
        _configure_checkpoint_dir,
        save_checkpoint,
    )

    ckpt_dir = tmp_path / "ckpts"
    ckpt_dir.mkdir()
    _configure_checkpoint_dir(str(ckpt_dir))
    cp = CrawlCheckpoint(mode="full")
    cp.completed_windows = ["20260701_20260707"]
    cp.meta = {
        "run_id": "run-foreign-old",
        "incremental_days": 7,
    }
    save_checkpoint(cp)

    # Ensure ALLOW is off
    prev = os.environ.pop("CONTRACTS_ALLOW_CROSS_RUN_RESUME", None)
    try:
        rc = inc.main(
            [
                "--dsn",
                "postgresql://unused",
                "--days",
                "7",
                "--checkpoint-dir",
                str(ckpt_dir),
                "--output-json",
                str(tmp_path / "out.json"),
                "--dry-run",
            ]
        )
    finally:
        if prev is not None:
            os.environ["CONTRACTS_ALLOW_CROSS_RUN_RESUME"] = prev

    assert rc == 1


def test_incremental_refuses_days_mismatch(tmp_path: Path) -> None:
    from scripts.crawl import run_contracts_incremental as inc
    from scripts.crawl.contracts_crawler import CrawlCheckpoint
    from scripts.crawl.run_contracts_90d_pilot import (
        _configure_checkpoint_dir,
        save_checkpoint,
    )

    ckpt_dir = tmp_path / "ckpts"
    ckpt_dir.mkdir()
    _configure_checkpoint_dir(str(ckpt_dir))
    cp = CrawlCheckpoint(mode="full")
    cp.completed_windows = ["20260701_20260707"]
    cp.meta = {"run_id": "run-x", "incremental_days": 7}
    save_checkpoint(cp)

    os.environ["CONTRACTS_ALLOW_CROSS_RUN_RESUME"] = "1"
    try:
        rc = inc.main(
            [
                "--dsn",
                "postgresql://unused",
                "--days",
                "14",  # mismatch
                "--checkpoint-dir",
                str(ckpt_dir),
                "--output-json",
                str(tmp_path / "out.json"),
                "--dry-run",
            ]
        )
    finally:
        os.environ.pop("CONTRACTS_ALLOW_CROSS_RUN_RESUME", None)

    assert rc == 1


def test_incremental_reset_clears_foreign_binding(tmp_path: Path) -> None:
    from scripts.crawl import run_contracts_incremental as inc
    from scripts.crawl.contracts_crawler import CrawlCheckpoint
    from scripts.crawl.run_contracts_90d_pilot import (
        _configure_checkpoint_dir,
        load_checkpoint,
        save_checkpoint,
    )

    ckpt_dir = tmp_path / "ckpts"
    ckpt_dir.mkdir()
    _configure_checkpoint_dir(str(ckpt_dir))
    cp = CrawlCheckpoint(mode="full")
    cp.completed_windows = ["20260701_20260707"]
    cp.meta = {"run_id": "run-foreign-old", "incremental_days": 7}
    save_checkpoint(cp)

    # dry-run after reset should not hard-fail on foreign guard
    # (may still fail later on DSN/pilot — only assert guard passes past checkpoint)
    # We spy by only testing the guard path via reset + load state.
    from scripts.crawl.run_contracts_90d_pilot import run_pilot as real_run_pilot

    calls: list[dict] = []

    def fake_pilot(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return {
            "status": "success",
            "totals": {
                "inserted": 0,
                "fetched": 0,
                "windows_failed": 0,
                "page_errors": 0,
            },
        }

    original = inc.run_pilot if hasattr(inc, "run_pilot") else None
    # Patch at the import site used inside main
    import scripts.crawl.run_contracts_90d_pilot as pilot_mod

    prev_pilot = pilot_mod.run_pilot
    pilot_mod.run_pilot = fake_pilot  # type: ignore[assignment]
    try:
        rc = inc.main(
            [
                "--dsn",
                "postgresql://test",
                "--days",
                "7",
                "--checkpoint-dir",
                str(ckpt_dir),
                "--output-json",
                str(tmp_path / "out.json"),
                "--reset-checkpoint",
                "--dry-run",
            ]
        )
    finally:
        pilot_mod.run_pilot = prev_pilot  # type: ignore[assignment]

    assert rc == 0
    assert calls, "run_pilot should have been invoked after reset"
    # Checkpoint after reset should not keep foreign run_id binding pre-pilot
    # (pilot may rebind; windows must be cleared by reset)
    # Re-load via configured dir
    _configure_checkpoint_dir(str(ckpt_dir))
    after = load_checkpoint("full")
    # completed windows were cleared by reset; pilot may have re-added none
    assert after.meta.get("incremental_days") == 7


# ---------------------------------------------------------------------------
# PNCP open-proposal forward horizon
# ---------------------------------------------------------------------------


def test_pncp_open_proposal_horizon_forward_from_today() -> None:
    from scripts.opportunity_intel.crawler_base import CrawlRequest
    from scripts.opportunity_intel.pncp_crawler import (
        PNCP_OPEN_PROPOSAL_HORIZON_DAYS,
        PncpOpportunityCrawler,
    )

    crawler = PncpOpportunityCrawler(dsn=None)
    req = CrawlRequest(
        source="pncp",
        target="modalidade:6",
        date_from=date.today() - timedelta(days=7),
        date_to=date.today(),
        mode="incremental",
    )
    data_final = crawler.resolve_data_final(req)
    assert data_final == date.today() + timedelta(days=PNCP_OPEN_PROPOSAL_HORIZON_DAYS)
    url = crawler.build_url(req, 1)
    assert f"dataFinal={data_final.strftime('%Y%m%d')}" in url
    # Must not use bare today as dataFinal (same-day-only window)
    assert f"dataFinal={date.today().strftime('%Y%m%d')}" not in url
    assert "uf=SC" in url


def test_pncp_open_proposal_respects_future_date_to() -> None:
    from scripts.opportunity_intel.crawler_base import CrawlRequest
    from scripts.opportunity_intel.pncp_crawler import PncpOpportunityCrawler

    crawler = PncpOpportunityCrawler(dsn=None)
    future = date.today() + timedelta(days=60)
    req = CrawlRequest(
        source="pncp",
        target="modalidade:6",
        date_from=date.today(),
        date_to=future,
        mode="incremental",
    )
    assert crawler.resolve_data_final(req) == future


def test_weekly_source_mentions_canonical_unavailable_constant() -> None:
    from scripts.ops import weekly_cycle as wc

    src = Path(wc.__file__).read_text(encoding="utf-8")
    assert "CANONICAL_200KM_UNIVERSE_UNAVAILABLE" in src
    assert "sc_uf_fallback" in src
    # Ensure the old silent fallback assignment is gone
    assert 'else "c.uf = \'SC\'"' not in src
    assert "extra_sc_uf_fallback_empty_universe" not in src
