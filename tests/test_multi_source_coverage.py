"""Unit tests for scripts.coverage.multi_source_coverage."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from scripts.coverage import multi_source_coverage as msc

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def as_of() -> date:
    return date(2026, 7, 17)


@pytest.fixture
def now(as_of: date) -> datetime:
    return datetime(as_of.year, as_of.month, as_of.day, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mini_root(tmp_path: Path, as_of: date) -> Path:
    """Minimal project tree with artifacts for all four sources + historical metric."""
    root = tmp_path

    # IBGE universe (3 municipios for small tests; real code uses len(keys))
    ibge = {
        "florianopolis": "4205407",
        "papanduva": "4212200",
        "blumenau": "4202404",
    }
    _write_json(root / "data" / "ibge_cache.json", ibge)

    # CIGA DOM
    ciga_run = "ciga-dom-test-001"
    ciga_dir = root / "output" / "ciga_dom" / ciga_run
    pubs = [
        {
            "source": "ciga_dom",
            "municipio": "Papanduva",
            "orgao": "Prefeitura municipal de Papanduva",
            "data": as_of.isoformat(),
            "titulo": "AVISO DE LICITACAO",
            "url": "https://example.com/a.pdf",
            "texto": "licitacao",
            "act_category": "aviso_licitacao",
        },
        {
            "source": "ciga_dom",
            "municipio": "Blumenau",
            "orgao": "Prefeitura de Blumenau",
            "data": as_of.isoformat(),
            "titulo": "PORTARIA",
            "url": "https://example.com/b.pdf",
            "texto": "nomeacao",
            "act_category": "nao_relacionado",
        },
        {
            "source": "ciga_dom",
            "municipio": "Florianópolis",
            "orgao": "PMF",
            "data": (as_of - timedelta(days=40)).isoformat(),  # outside 30d
            "titulo": "EDITAL",
            "url": "",
            "texto": "edital antigo",
            "act_category": "edital",
        },
    ]
    _write_jsonl(ciga_dir / "publications.jsonl", pubs)
    summary = {
        "run_id": ciga_run,
        "source": "ciga_dom",
        "mode": "smoke",
        "status": "success",
        "counts": {"records_normalized": 3, "municipalities_observed": 3},
        "completed_at": datetime(as_of.year, as_of.month, as_of.day, 2, 14, 43, tzinfo=UTC).isoformat(),
        "started_at": datetime(as_of.year, as_of.month, as_of.day, 2, 14, 36, tzinfo=UTC).isoformat(),
    }
    _write_json(ciga_dir / "summary.json", summary)
    _write_json(root / "output" / "ciga_dom" / "latest_summary.json", summary)
    _write_json(
        root / "output" / "ciga_dom" / "freshness_manifest.json",
        {
            "source": "ciga_dom",
            "run_id": ciga_run,
            "generated_at": summary["completed_at"],
            "latest_resource_modified": f"{as_of.isoformat()}T19:14:41",
            "status": "success",
        },
    )

    # sc_compras
    sc_run = "sc_compras-incremental-test-001"
    sc_dir = root / "output" / "sc_compras" / sc_run
    sc_rows = [
        {
            "pncp_id": "sc-1",
            "objeto_compra": "Servico X",
            "orgao_razao_social": "Secretaria de Estado da Saúde - SES",
            "orgao_cnpj": None,
            "data_publicacao": as_of.isoformat(),
            "data_abertura": (as_of + timedelta(days=7)).isoformat(),
            "modalidade_nome": "Dispensa",
            "municipio": None,
            "valor_total_estimado": None,
            "link_pncp": "https://compras.sc.gov.br/1",
            "documentos": [],
            "status": "aberta",
        },
        {
            "pncp_id": "sc-2",
            "objeto_compra": "Servico Y",
            "orgao_razao_social": "Secretaria de Estado da Administração - SEA",
            "orgao_cnpj": "123",
            "data_publicacao": as_of.isoformat(),
            "data_abertura": None,
            "modalidade_nome": "Pregao",
            "municipio": "Florianopolis",
            "valor_total_estimado": 1000,
            "link_pncp": "https://compras.sc.gov.br/2",
            "documentos": [{"id": 1}],
            "status": "aberta",
        },
    ]
    _write_jsonl(sc_dir / "licitacoes.jsonl", sc_rows)
    _write_json(
        sc_dir / "artifact.json",
        {
            "run_id": sc_run,
            "source": "sc_compras",
            "mode": "incremental",
            "ano": 2026,
            "status": "ok",
            "completed_at": f"{as_of.isoformat()}T02:15:45Z",
            "started_at": f"{as_of.isoformat()}T02:15:44Z",
            "metrics": {
                "api_total_elementos_reported": 100,
                "records_normalized": 2,
                "coverage_claim": "year filter only",
                "list_meta": {"total_elementos": 100},
            },
        },
    )

    # dados_abertos_sc
    dados_summary = {
        "run_id": "dados-sc-smoke-test-001",
        "source": "dados_abertos_sc",
        "mode": "smoke",
        "status": "ok",
        "completed_at": f"{as_of.isoformat()}T02:13:40+00:00",
        "counts": {
            "resources_listed": 14,
            "resources_selected": 1,
            "rows_normalized": 3,
            "act_categories": {"edital": 1, "aviso_licitacao": 1, "outros": 1},
        },
        "download_results": [],
        "sample_records": [],
    }
    _write_json(
        root / "output" / "dados_abertos_sc" / "smoke-dados-sc-smoke-test-001.json",
        dados_summary,
    )
    dados_rows = [
        {
            "orgao": "Orgao A",
            "titulo": "EDITAL",
            "data_publicacao": "2025-04-01",
            "tipo_ato": "EDITAL",
            "act_category": "edital",
            "texto_ou_extrato": "texto",
            "link_edicao": None,
            "link_extrato": None,
        },
        {
            "orgao": "Orgao B",
            "titulo": "AVISO",
            "data_publicacao": as_of.isoformat(),
            "tipo_ato": "AVISO",
            "act_category": "aviso_licitacao",
            "texto_ou_extrato": "texto",
            "link_edicao": "https://example.com/ed",
            "link_extrato": None,
        },
        {
            "orgao": "Orgao C",
            "titulo": "OUTRO",
            "data_publicacao": as_of.isoformat(),
            "tipo_ato": "OUTRO",
            "act_category": "outros",
            "texto_ou_extrato": "texto",
            "link_edicao": None,
            "link_extrato": "https://example.com/ex",
        },
    ]
    _write_jsonl(
        root
        / "data"
        / "normalized"
        / "dados_abertos_sc"
        / "res1"
        / "dados-sc-smoke-test-001.jsonl",
        dados_rows,
    )

    # Historical + readiness proxies for PNCP
    _write_json(
        root / "output" / "coverage" / "next30d-metrics-final.json",
        {
            "covered_200km": 52,
            "editais_denominator": 1093,
            "editais_crude_pct": 4.76,
            "pncp_raw_bids": 2948,
            "timestamp": f"{as_of.isoformat()}T01:20:00+00:00",
        },
    )
    _write_json(
        root / "output" / "sc_compras" / "coverage-truth" / "coverage-truth-2026-07-16.json",
        {
            "denominator": {"total_entities_within_radius": 1093},
            "bid_presence": {"pct": 4.8, "entities_with_bids": 52},
        },
    )
    _write_json(
        root / "output" / "readiness" / "target-reconciliation-summary.json",
        {
            "generated_at": f"{as_of.isoformat()}T08:26:17",
            "universe": {"targets_within_200km": 1093, "confirmed_universe": 1093},
            "spreadsheet": {"total_rows": 2085},
            "match_results": {
                "FOUND_EXACT": {"count": 309},
                "MISSED_SOURCE_NOT_COVERED": {"count": 1776},
            },
        },
    )
    _write_json(
        root / "output" / "readiness" / "opportunity-coverage-manifest.json",
        {
            "meta": {"generated_at": f"{as_of.isoformat()}T00:00:00+00:00"},
            "universe": {
                "total_entities_within_200km": 1093,
                "entities_with_opportunity_data": 461,
            },
        },
    )
    _write_json(
        root / "output" / "readiness" / "freshness-gate.json",
        {
            "generated_at": f"{as_of.isoformat()}T01:01:47+00:00",
            "critical_sources": [
                {
                    "source": "pncp",
                    "last_success_at": None,
                    "latest_business_date": None,
                    "freshness_status": "never",
                }
            ],
        },
    )
    return root


# ---------------------------------------------------------------------------
# Unit: pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_normalize_muni_key_accents(self):
        assert msc.normalize_muni_key("Florianópolis") == msc.normalize_muni_key("florianopolis")
        assert msc.normalize_muni_key("Balneário Camboriú") == "balneario camboriu"

    def test_parse_date_variants(self):
        assert msc.parse_date("2026-07-16") == date(2026, 7, 16)
        assert msc.parse_date("16/07/2026") == date(2026, 7, 16)
        assert msc.parse_date("2026-07-16T11:43:34") == date(2026, 7, 16)
        assert msc.parse_date(None) is None
        assert msc.parse_date("") is None

    def test_safe_pct(self):
        assert msc.safe_pct(52, 1093) == 4.76
        assert msc.safe_pct(1, 0) is None
        assert msc.safe_pct(None, 10) is None

    def test_metric_schema_keys(self):
        m = msc.metric(
            name="x",
            numerator=1,
            denominator=2,
            formula="1/2",
            period="p",
            sources=["s"],
            limitations=["l"],
            calc_date="2026-07-17",
            run_id="r",
            confidence="high",
        )
        required = {
            "name",
            "numerator",
            "denominator",
            "formula",
            "period",
            "sources",
            "limitations",
            "calc_date",
            "run_id",
            "result",
            "confidence",
        }
        assert required.issubset(m.keys())
        assert m["result"] == 50.0


# ---------------------------------------------------------------------------
# Unit: individual metrics
# ---------------------------------------------------------------------------


class TestMunicipalitiesMetric:
    def test_window_and_ibge_match(self, mini_root: Path, as_of: date):
        ibge = msc.load_ibge_universe(mini_root / "data" / "ibge_cache.json")
        ciga = msc.discover_ciga_dom(mini_root)
        m = msc.calc_municipalities_with_publication_30d(
            ciga=ciga,
            ibge=ibge,
            window_days=30,
            as_of=as_of,
            calc_date=as_of.isoformat(),
            run_id="t",
        )
        # Papanduva + Blumenau in window; Florianópolis only outside window
        assert m["numerator"] == 2
        assert m["denominator"] == 3
        assert m["result"] == pytest.approx(66.67, abs=0.01)
        assert m["confidence"] in {"medium", "high"}
        assert "ciga_dom" in m["primary_source"]


class TestOrgsMetric:
    def test_union_orgs_and_universe(self, mini_root: Path, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        sc = msc.discover_sc_compras(mini_root)
        dados = msc.discover_dados_abertos_sc(mini_root)
        m = msc.calc_orgs_with_recent_licitacao(
            ciga=ciga,
            sc=sc,
            dados=dados,
            window_days=30,
            as_of=as_of,
            calc_date=as_of.isoformat(),
            run_id="t",
            root=mini_root,
        )
        assert m["denominator"] == 1093
        # sc: SES + SEA; ciga procurement in window: Papanduva only (aviso_licitacao)
        # dados: Orgao B aviso in window; Orgao C outros excluded; Orgao A outside window
        assert m["numerator"] >= 3
        assert m["result"] is not None
        assert m["result"] < 5  # far below 100% — not confused with municipal coverage


class TestPncpReconciled:
    def test_proxy_from_target_reconciliation(self, mini_root: Path, as_of: date):
        pncp = msc.discover_pncp(mini_root)
        m = msc.calc_pncp_sc_reconciled(pncp=pncp, calc_date=as_of.isoformat(), run_id="t")
        assert m["name"] == "pncp_sc_reconciled"
        assert m["numerator"] == 309
        assert m["denominator"] == 1093
        assert m["confidence"] == "low"  # proxy, not formal recon
        assert any("PROXY" in lim or "proxy" in lim.lower() for lim in m["limitations"])


class TestSourceCoverage:
    def test_sc_compras_sample_over_api_total(self, mini_root: Path, as_of: date):
        sc = msc.discover_sc_compras(mini_root)
        ibge = msc.load_ibge_universe(mini_root / "data" / "ibge_cache.json")
        m = msc.calc_source_coverage(
            source="sc_compras",
            art=sc,
            ibge=ibge,
            calc_date=as_of.isoformat(),
            run_id="t",
            as_of=as_of,
        )
        assert m["numerator"] == 2
        assert m["denominator"] == 100
        assert m["result"] == 2.0

    def test_ciga_muni_coverage(self, mini_root: Path, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        ibge = msc.load_ibge_universe(mini_root / "data" / "ibge_cache.json")
        m = msc.calc_source_coverage(
            source="ciga_dom",
            art=ciga,
            ibge=ibge,
            calc_date=as_of.isoformat(),
            run_id="t",
            as_of=as_of,
        )
        # all 3 munis present in artifact
        assert m["numerator"] == 3
        assert m["denominator"] == 3
        assert m["result"] == 100.0


class TestTemporalFieldDocFreshness:
    def test_temporal_ciga_one_day_in_window(self, mini_root: Path, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        m = msc.calc_temporal_coverage(
            source="ciga_dom",
            records=ciga.records,
            date_keys=["data"],
            window_days=30,
            as_of=as_of,
            calc_date=as_of.isoformat(),
            run_id="t",
            source_paths=["x"],
        )
        assert m["numerator"] == 1  # only as_of day in window (old florianopolis outside)
        assert m["denominator"] == 31

    def test_act_category_distribution(self, mini_root: Path, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        m = msc.calc_act_category_distribution(
            source="ciga_dom",
            records=ciga.records,
            calc_date=as_of.isoformat(),
            run_id="t",
            source_paths=[],
        )
        assert m["numerator"] >= 2  # aviso_licitacao + edital
        assert m["denominator"] == len(msc.PROCUREMENT_ACT_CATEGORIES)
        assert "distribution" in m

    def test_field_completeness_and_docs(self, mini_root: Path, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        fc = msc.calc_field_completeness(
            source="ciga_dom",
            records=ciga.records,
            fields=msc.FIELD_SETS["ciga_dom"],
            calc_date=as_of.isoformat(),
            run_id="t",
            source_paths=[],
        )
        assert fc["denominator"] == 3 * len(msc.FIELD_SETS["ciga_dom"])
        assert 0 < fc["result"] <= 100

        dc = msc.calc_document_coverage(
            source="ciga_dom",
            records=ciga.records,
            link_keys=["url"],
            calc_date=as_of.isoformat(),
            run_id="t",
            source_paths=[],
        )
        # 2 of 3 have non-empty url
        assert dc["numerator"] == 2
        assert dc["denominator"] == 3

    def test_freshness_hours(self, mini_root: Path, now: datetime, as_of: date):
        ciga = msc.discover_ciga_dom(mini_root)
        m = msc.calc_freshness_hours(
            source="ciga_dom",
            art=ciga,
            now=now,
            calc_date=as_of.isoformat(),
            run_id="t",
        )
        assert m["result_unit"] == "hours"
        assert m["result"] is not None
        assert m["result"] >= 0


class TestHistoricalPreserved:
    def test_historical_not_overwritten(self, mini_root: Path, as_of: date):
        m = msc.calc_historical_editais_raw(as_of.isoformat(), "t", mini_root)
        assert m["name"] == "historical_editais_raw_coverage"
        assert m["numerator"] == 52
        assert m["denominator"] == 1093
        assert m["result"] == 4.76
        assert m.get("preserved") is True
        assert m.get("do_not_overwrite") is True
        assert any("4.76" in lim or "PRESERVED" in lim or "preserved" in lim.lower() for lim in m["limitations"])


# ---------------------------------------------------------------------------
# Integration: full collect + write
# ---------------------------------------------------------------------------


class TestCollectAll:
    def test_collect_all_metrics_has_required_names(self, mini_root: Path, now: datetime):
        report = msc.collect_all_metrics(
            root=mini_root,
            window_days=30,
            now=now,
            run_id="test-run-001",
        )
        names = {m["name"] for m in report["metrics"]}
        required = {
            "historical_editais_raw_coverage",
            "municipalities_with_publication_30d",
            "orgs_with_recent_licitacao",
            "pncp_sc_reconciled",
            "source_coverage_dados_abertos_sc",
            "source_coverage_ciga_dom",
            "source_coverage_sc_compras",
            "source_coverage_pncp",
            "temporal_coverage_ciga_dom",
            "temporal_coverage_sc_compras",
            "temporal_coverage_dados_abertos_sc",
            "act_category_distribution_ciga_dom",
            "act_category_distribution_dados_abertos_sc",
            "field_completeness_ciga_dom",
            "field_completeness_sc_compras",
            "field_completeness_dados_abertos_sc",
            "document_coverage_ciga_dom",
            "document_coverage_sc_compras",
            "document_coverage_dados_abertos_sc",
            "freshness_hours_ciga_dom",
            "freshness_hours_sc_compras",
            "freshness_hours_dados_abertos_sc",
            "freshness_hours_pncp",
        }
        missing = required - names
        assert not missing, f"missing metrics: {missing}"

        # Historical remains 4.76
        hist = next(m for m in report["metrics"] if m["name"] == "historical_editais_raw_coverage")
        assert hist["result"] == 4.76

        # Methodology notes change policy
        assert report["methodology"]["historical_metric_policy"] == "preserve_separately"

        # Every metric has required documentation fields
        for m in report["metrics"]:
            assert m["formula"]
            assert m["period"]
            assert m["sources"]
            assert m["limitations"]
            assert m["calc_date"]
            assert m["run_id"] == "test-run-001"
            assert m["confidence"] in {"high", "medium", "low", "none"}

    def test_write_report_files(self, mini_root: Path, now: datetime, tmp_path: Path):
        report = msc.collect_all_metrics(root=mini_root, window_days=30, now=now, run_id="write-001")
        out = tmp_path / "coverage_out"
        json_path, md_path = msc.write_report(report, out)
        assert json_path.exists()
        assert md_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["run_id"] == "write-001"
        md = md_path.read_text(encoding="utf-8")
        assert "historical_editais_raw_coverage" in md
        assert "4.76" in md
        assert (out / "multi_source-latest.json").exists()

    def test_main_cli(self, mini_root: Path, tmp_path: Path):
        out = tmp_path / "cli_out"
        rc = msc.main(
            [
                "--root",
                str(mini_root),
                "--output-dir",
                str(out),
                "--window-days",
                "30",
                "--run-id",
                "cli-001",
            ]
        )
        assert rc == 0
        assert (out / "multi_source-cli-001.json").exists()
        assert (out / "multi_source-cli-001.md").exists()
