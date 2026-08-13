"""Tests for PNCP per-entity pagination proof (#241)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.crawl.pncp_entity_pagination import (
    closing_requery,
    expected_pages,
    proof_report,
    prove_scope,
    record_page,
    sanitize_url,
    sla_status,
)


def _page(n: int, records: int = 2) -> object:
    return record_page(
        url=f"https://pncp.gov.br/api/consulta/v1/contratacoes?pagina={n}&token=SECRET",
        status=200,
        body=f"page-{n}".encode(),
        page=n,
        records=records,
    )


def test_pages_expected_equals_pages_fetched() -> None:
    pages = [_page(1), _page(2)]
    proof = prove_scope(
        ente_id="cnpj-1",
        window="2026-07",
        modalidade="6",
        pages_expected=2,
        pages=pages,
        found_count=4,
        query_complete=True,
    )
    assert proof.pages_match
    assert proof.verdict == "FOUND"
    assert expected_pages(4, 2) == 2


def test_each_page_records_sanitized_url_http_raw_and_hash() -> None:
    page = _page(1)
    assert "token=" not in page.url
    assert "pagina=1" in page.url
    assert page.status == 200
    assert page.fetched_at
    assert page.raw_uri.startswith("cas://pncp/")
    assert len(page.sha256) == 64
    assert sanitize_url("https://x?api_key=abc&p=1") == "https://x?p=1"


def test_zero_confirmed_only_when_complete_and_empty() -> None:
    empty = prove_scope(
        ente_id="cnpj-2",
        window="2026-07",
        modalidade="6",
        pages_expected=1,
        pages=[_page(1, records=0)],
        found_count=0,
        query_complete=True,
    )
    assert empty.verdict == "ZERO_CONFIRMED"
    incomplete = prove_scope(
        ente_id="cnpj-2",
        window="2026-07",
        modalidade="6",
        pages_expected=3,
        pages=[_page(1)],
        found_count=0,
        query_complete=False,
    )
    assert incomplete.verdict == "SCOPE_INCOMPLETE"
    assert incomplete.pages_match is False


def test_sla_and_closing_requery() -> None:
    published = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
    ok = sla_status(published + timedelta(hours=3), published)
    assert ok["within_slo"] is True
    hard = sla_status(published + timedelta(hours=30), published)
    assert hard["breach"] is True
    requery = closing_requery(["a", "b"], {"a", "b"})
    assert requery["complete"] is True
    missing = closing_requery(["a", "b"], {"a"})
    assert missing["missing"] == ["b"]


def test_report_relates_issues_34_and_40() -> None:
    report = proof_report(
        [
            prove_scope(
                ente_id="x",
                window="2026-07",
                modalidade=None,
                pages_expected=1,
                pages=[_page(1)],
                found_count=1,
                query_complete=True,
            )
        ]
    )
    assert report["related"] == ["#34", "#40"]
    assert report["scopes"][0]["verdict"] == "FOUND"
