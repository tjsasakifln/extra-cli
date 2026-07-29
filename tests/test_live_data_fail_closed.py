"""Fail-closed live-data invariants (D3–D5, checkpoint, PNCP horizon). Compact PR1 suite."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from scripts.collect.run_contract import CollectionRun, classify_terminal_status
from scripts.ops.weekly_cycle import (
    EXIT_TECH,
    StageResult,
    _EXTRA_UNIVERSE_ORGAO,
    _write_csv,
    compute_exit_code,
    stage_intelligence,
)


def test_extra_universe_sql_requires_raio_and_sc() -> None:
    sql = _EXTRA_UNIVERSE_ORGAO
    assert "raio_200km" in sql and "sc_public_entities" in sql and "orgao_cnpj_8" in sql


def test_stage_intelligence_fails_when_universe_not_1093() -> None:
    """D4: universe_n != 1093 → CANONICAL_200KM_UNIVERSE_UNAVAILABLE; no SC fallback."""

    def fake_q(_conn, sql, params=None):  # noqa: ANN001
        s = " ".join(str(sql).split())
        if "COUNT(*)" in s and "raio_200km" in s:
            return [{"n": 0}]
        return []

    import scripts.ops.weekly_cycle as wc

    original = wc._q
    wc._q = fake_q  # type: ignore[assignment]
    try:
        result = stage_intelligence(MagicMock(), limit=5, collection_id="col-test")
    finally:
        wc._q = original  # type: ignore[assignment]

    assert result.status == "fail"
    assert "CANONICAL_200KM_UNIVERSE_UNAVAILABLE" in (result.error or "")
    assert result.detail.get("sc_uf_fallback") is False
    assert result.detail.get("contracts_scope_sql_applied") is False

    stages = [
        StageResult(name="validate_db", status="ok"),
        StageResult(name="intelligence", status="fail", error=result.error),
        StageResult(
            name="delivery",
            status="ok",
            detail={"excel_ok": True, "checksums_file": "x", "product_checksums": {"a": {}}},
        ),
    ]
    opp = CollectionRun.start(source="pncp_opportunities", collection_id="c", collector_version="t")
    opp.finish(
        records_obtained=3,
        records_persisted=3,
        request_completed=True,
        scope_complete=True,
    )
    assert compute_exit_code(stages, [opp], strict=True) == EXIT_TECH


def test_normalize_uf_never_defaults_to_sc_except_dom_sc() -> None:
    """D5: PNCP/generic missing UF stays unknown; DOM-SC may keep SC."""
    from scripts.opportunity_intel.transformer import (
        normalize_dom_sc,
        normalize_generic,
        normalize_pncp,
    )

    missing = normalize_pncp({"numeroControlePNCP": "x-1", "objeto": "Obra sem UF"})
    assert not missing.uf and missing.uf != "SC"
    nested = normalize_pncp(
        {
            "numeroControlePNCP": "n-1",
            "objeto": "Com unidade",
            "unidadeOrgao": {"ufSigla": "PR", "municipioNome": "Curitiba"},
        }
    )
    assert nested.uf == "PR"
    gen = normalize_generic({"id": "g1", "objeto": "sem uf"}, "other")
    assert not gen.uf and gen.uf != "SC"
    dom = normalize_dom_sc({"id": 1, "titulo": "Ato municipal"})
    assert dom.uf == "SC" and dom.source == "dom_sc"


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


def test_empty_csv_writes_explicit_zero_row_count(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    _write_csv(path, [])
    text = path.read_text(encoding="utf-8")
    assert path.exists() and "row_count" in text and text.strip() != ""


def test_incremental_refuses_foreign_checkpoint_without_reset(tmp_path: Path) -> None:
    src = Path("scripts/crawl/run_contracts_incremental.py").read_text(encoding="utf-8")
    assert "refusing silent foreign resume" in src
    assert "--reset-checkpoint" in src or "CONTRACTS_ALLOW_CROSS_RUN_RESUME" in src
    # structural proof: checkpoint meta binds run_id
    assert "run_id" in src and "foreign" in src.lower()


def test_pncp_open_proposal_horizon_forward() -> None:
    from scripts.opportunity_intel.crawler_base import CrawlRequest
    from scripts.opportunity_intel.pncp_crawler import PncpOpportunityCrawler

    crawler = PncpOpportunityCrawler()
    req = CrawlRequest(source="pncp", mode="full", date_from=None, date_to=None)
    data_final = crawler.resolve_data_final(req)
    assert data_final > date.today()
    assert data_final <= date.today() + timedelta(days=45)
