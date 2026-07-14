"""Unit coverage for the QW-01 auditable radar invariants."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from openpyxl import Workbook

from scripts.lib.universe import CanonicalEntity, CanonicalUniverse, load_canonical_universe
from scripts.opportunity_intel.cli import build_parser
from scripts.opportunity_intel.crawler_base import BaseOpportunityCrawler, _retry_wait_seconds
from scripts.opportunity_intel.models import CrawlRequest, FetchResult
from scripts.opportunity_intel.pncp_audit import _summarize_scope
from scripts.opportunity_intel.profile import load_client_profile
from scripts.opportunity_intel.radar import (
    _spreadsheet_cell,
    build_monitoring_metrics,
    evidence_is_monitoring_success,
)
from scripts.opportunity_intel.scoring import score_opportunity


def _entity(entity_id: str = "extra-test", *, within_radius: bool | None = True) -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=entity_id,
        seed_row=2,
        razao_social="Município Teste",
        cnpj8="12345678",
        municipio="Florianópolis",
        codigo_ibge="4205407",
        natureza_juridica="Município",
        latitude=-27.59,
        longitude=-48.55,
        distancia_km=10.0,
        radius_decision="included" if within_radius else "unresolved",
        within_radius=within_radius,
        decision_method="test",
        identity_key="12345678|FLORIANOPOLIS|MUNICIPIO TESTE",
    )


def _universe(*entities: CanonicalEntity) -> CanonicalUniverse:
    return CanonicalUniverse(
        seed_path="seed.xlsx",
        seed_sha256="a" * 64,
        radius_km=200.0,
        entities=list(entities),
    )


class _StubCrawler(BaseOpportunityCrawler):
    def __init__(self, results: list[FetchResult]):
        super().__init__(
            source_name="stub",
            dsn="postgresql://unused",
            request_delay=0,
            page_size=2,
            max_pages=10,
        )
        self.results = results

    def build_url(self, request: CrawlRequest, page: int) -> str:
        return f"https://example.test?page={page}"

    def parse_response(self, raw_data):
        return raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data

    def fetch_page(self, url: str, page: int) -> FetchResult:
        return self.results[page - 1]


class _UrlValidationCrawler(BaseOpportunityCrawler):
    def __init__(self, max_retries: int = 0):
        super().__init__(
            source_name="url-test",
            dsn="postgresql://unused",
            max_retries=max_retries,
        )

    def build_url(self, request: CrawlRequest, page: int) -> str:
        return "file:///etc/passwd"

    def parse_response(self, raw_data):
        return []


def test_seed_snapshot_preserves_rows_duplicates_and_unresolved(tmp_path) -> None:
    seed = tmp_path / "seed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Entes Públicos SC"
    sheet.append(
        [
            "Razão Social",
            "CNPJ",
            "Município",
            "IBGE",
            "Natureza",
            "Extra",
            "Latitude",
            "Longitude",
            "Distância",
            "Raio 200km?",
        ]
    )
    sheet.append(["Ente A", "12.345.678/0001-00", "Cidade A", 1, "M", None, -27, -48, 10, "SIM"])
    sheet.append(["Ente B", "12.345.678/0002-00", "Cidade B", 2, "M", None, -28, -49, 250, "NÃO"])
    sheet.append(["Ente C", "98.765.432/0001-00", "Cidade C", 3, "M", None, None, None, None, None])
    sheet.append(["Ente A", "12.345.678/0001-00", "Cidade A", 1, "M", None, -27, -48, 10, "SIM"])
    workbook.save(seed)

    universe = load_canonical_universe(seed)

    assert len(universe.entities) == 4
    assert len(universe.included) == 2
    assert len(universe.excluded) == 1
    assert len(universe.unresolved) == 1
    assert universe.duplicate_roots == ["12345678"]
    assert len({entity.entity_id for entity in universe.entities}) == 4
    assert universe.summary()["conservative_monitoring_denominator"] == 3


def test_reported_pagination_is_complete() -> None:
    results = [
        FetchResult(
            status=200,
            raw_data=[{"id": "1"}],
            page=1,
            total_pages=2,
            total_records=2,
            page_size=1,
        ),
        FetchResult(
            status=200,
            raw_data=[{"id": "2"}],
            page=2,
            total_pages=2,
            total_records=2,
            page_size=1,
            completion_rule="reported_total_pages",
        ),
    ]

    outcome = _summarize_scope(1, results, max_pages=None, max_records=None)

    assert outcome.scope_complete is True
    assert outcome.pages_expected == 2
    assert outcome.pages_processed == 2
    assert outcome.records_expected == 2


def test_crawler_preserves_api_totals_and_limits_records_not_pages() -> None:
    crawler = _StubCrawler(
        [
            FetchResult(
                status=200,
                raw_data=[{"id": "1"}, {"id": "2"}],
                page=1,
                total_pages=3,
                total_records=5,
                page_size=2,
            ),
            FetchResult(
                status=200,
                raw_data=[{"id": "3"}, {"id": "4"}],
                page=2,
                total_pages=3,
                total_records=5,
                page_size=2,
            ),
        ]
    )
    totals = crawler.extract_pagination({"data": [], "totalPaginas": 3, "totalRegistros": 5})
    results = crawler.crawl(CrawlRequest(source="stub", mode="dry-run", max_pages=10, max_records=2, page_size=2))

    assert totals == (3, 5)
    assert len(results) == 1
    assert sum(len(result.raw_data) for result in results) == 2
    assert results[0].total_pages == 3
    assert results[0].total_records == 5


def test_crawler_rejects_non_https_urls_before_opening() -> None:
    result = _UrlValidationCrawler().fetch_page("file:///etc/passwd", page=1)
    assert result.status == 0
    assert result.error == "Blocked URL: opportunity crawlers require an absolute HTTPS endpoint"


def test_crawler_retries_http_429_and_honors_retry_after() -> None:
    url = "https://pncp.gov.br/example"
    throttled = HTTPError(url, 429, "Too Many Requests", {"Retry-After": "0"}, None)
    response = MagicMock()
    response.__enter__.return_value.status = 204
    response.__enter__.return_value.read.return_value = b""
    crawler = _UrlValidationCrawler(max_retries=1)

    with (
        patch("urllib.request.urlopen", side_effect=[throttled, response]) as urlopen,
        patch("time.sleep") as sleep,
    ):
        result = crawler.fetch_page(url, page=1)

    assert result.success is True
    assert result.completion_rule == "http_204_complete"
    assert urlopen.call_count == 2
    sleep.assert_called_once_with(0.0)


def test_retry_backoff_is_conservative_without_retry_after() -> None:
    assert _retry_wait_seconds(None, 0) == 5.0
    assert _retry_wait_seconds(None, 1) == 10.0


def test_page_limit_cannot_be_complete_or_success_zero() -> None:
    result = FetchResult(
        status=200,
        raw_data=[],
        page=1,
        total_pages=3,
        total_records=0,
        page_size=50,
    )

    outcome = _summarize_scope(1, [result], max_pages=1, max_records=None)

    assert outcome.scope_complete is False
    assert outcome.error_code == "MAX_PAGES"


def test_monitoring_success_requires_fresh_complete_scope() -> None:
    valid = {
        "state": "success_zero",
        "freshness_status": "fresh",
        "pages_expected": 2,
        "pages_processed": 2,
        "evidence_metadata": {"scope_complete": True, "completion_rule": "reported_total_pages"},
    }
    assert evidence_is_monitoring_success(valid) is True

    for field, value in (
        ("freshness_status", "stale"),
        ("pages_processed", 1),
        ("evidence_metadata", {"scope_complete": False, "completion_rule": "reported_total_pages"}),
    ):
        invalid = {**valid, field: value}
        assert evidence_is_monitoring_success(invalid) is False


def test_monitoring_denominator_includes_unresolved_but_not_excluded() -> None:
    included = _entity("included", within_radius=True)
    unresolved = _entity("unresolved", within_radius=None)
    excluded = _entity("excluded", within_radius=False)
    evidence = {
        "included": {
            "state": "success_zero",
            "freshness_status": "fresh",
            "pages_expected": 1,
            "pages_processed": 1,
            "evidence_metadata": {"scope_complete": True, "completion_rule": "reported_total_pages"},
        }
    }

    metrics, gaps = build_monitoring_metrics(_universe(included, unresolved, excluded), evidence)

    assert metrics["denominator"] == 2
    assert metrics["numerator"] == 1
    assert metrics["percent"] == 50.0
    assert [gap["entity_id"] for gap in gaps] == ["unresolved"]


def test_data_confidence_and_client_fit_are_independent_dimensions() -> None:
    profile = load_client_profile("config/client_profiles/extra.yaml")
    entity = _entity()
    now = datetime.now(UTC)
    base = {
        "source": "pncp",
        "source_url": "https://pncp.gov.br/example",
        "orgao_cnpj": "12345678000100",
        "orgao_nome": "Município Teste",
        "municipio": "Florianópolis",
        "objeto": "Reforma predial de escola pública",
        "modalidade": "Concorrência eletrônica",
        "data_encerramento": now + timedelta(days=10),
        "status_canonico": "open",
        "last_seen_at": now,
    }
    matching = score_opportunity(base, entity, profile, "future_deadline", now=now)
    non_matching_row = {**base, "objeto": "Aquisição de material de escritório"}
    non_matching = score_opportunity(non_matching_row, entity, profile, "future_deadline", now=now)
    non_official_row = deepcopy(base)
    non_official_row["source"] = "other"
    non_official = score_opportunity(non_official_row, entity, profile, "future_deadline", now=now)

    assert matching.data_confidence_score == non_matching.data_confidence_score
    assert matching.client_fit_score > non_matching.client_fit_score
    assert matching.data_confidence_score > non_official.data_confidence_score
    assert matching.client_fit_score == non_official.client_fit_score


def test_cli_exposes_auditable_radar_options() -> None:
    args = build_parser().parse_args(
        [
            "radar",
            "--profile",
            "config/client_profiles/extra.yaml",
            "--window-days",
            "30",
            "--update",
            "never",
        ]
    )

    assert args.command == "radar"
    assert args.window_days == 30
    assert args.update == "never"
    assert args.output_dir == "output/qw-01"


def test_spreadsheet_export_sanitizes_controls_and_formulas() -> None:
    assert _spreadsheet_cell("Reforma\x1c predial") == "Reforma predial"
    assert _spreadsheet_cell('=HYPERLINK("https://evil.test")') == '\'=HYPERLINK("https://evil.test")'
    assert _spreadsheet_cell(123.45) == 123.45
