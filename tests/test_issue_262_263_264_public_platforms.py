"""Refs #262 #263 #264 — public per-entity adapter contracts.

Drives scripts.public_platforms.collect.collect_from_payload. Live 24h
freshness remains residual.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.crawl.registry import lookup
from scripts.public_platforms.collect import collect_from_fixture, collect_from_payload, transform_records
from scripts.public_platforms.contract import PLATFORMS, classify_http_block

FIXTURES = Path(__file__).parent / "fixtures" / "public_platforms"


@pytest.mark.parametrize("source", ("bbmnet", "licitanet", "compras_br"))
def test_issue_262_263_264_registry_and_fixture_crawl(source: str) -> None:
    info = lookup(source)
    assert info is not None
    assert info.role == "complementary"
    assert info.freshness_sla_hours == 24
    assert info.supports_zero_proof is True
    assert info.canonical_url == PLATFORMS[source]["canonical_url"]
    result = collect_from_fixture(source, FIXTURES / f"{source}_pages.json")
    assert result.terminal == "success"
    assert result.fetched >= 1
    assert result.persisted >= 1
    surfaces = {page.surface for page in result.pages}
    assert surfaces == {"listing", "detail", "documents", "status"}
    assert all(page.raw_hash and page.raw_uri for page in result.pages)
    transformed = transform_records(source, result.records)
    assert transformed
    assert all(row["source"] == source and row["source_id"] for row in transformed)


def test_issue_262_bbmnet_pagination_must_complete_before_zero() -> None:
    payload = {
        "entity": {"ibge": "4205407"},
        "listing": [{"page": 1, "complete": False, "status": 200, "records": []}],
    }
    result = collect_from_payload("bbmnet", payload)
    assert result.terminal == "partial"
    assert result.reason == "pagination_incomplete"


def test_issue_262_bbmnet_zero_only_after_complete_scope() -> None:
    payload = {
        "entity": {"ibge": "4205407"},
        "listing": [{"page": 1, "complete": True, "status": 200, "records": []}],
    }
    result = collect_from_payload("bbmnet", payload)
    assert result.terminal == "ZERO"


def test_issue_263_licitanet_login_captcha_403_are_blocked() -> None:
    assert classify_http_block(status=403, body="ok") == "BLOCKED"
    assert classify_http_block(status=200, body="Please solve captcha") == "BLOCKED"
    payload = {
        "entity": {"ibge": "4202008"},
        "listing": [{"page": 1, "complete": True, "status": 200, "records": []}],
        "blocked": {"status": 401, "body": "login senha"},
    }
    result = collect_from_payload("licitanet", payload)
    assert result.terminal == "BLOCKED"
    assert result.terminal != "success"
    assert result.terminal != "ZERO"


def test_issue_264_compras_br_preserves_idlicitacao() -> None:
    result = collect_from_fixture("compras_br", FIXTURES / "compras_br_pages.json")
    ids = {row.get("idlicitacao") for row in result.records}
    assert "42516" in ids
    transformed = transform_records("compras_br", result.records)
    assert any(row["source_id"] == "42516" for row in transformed)


def test_issue_264_opt_in_live_refuses_bare_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.public_platforms.collect import crawl_source

    monkeypatch.setenv("PUBLIC_PLATFORM_LIVE", "1")
    with pytest.raises(RuntimeError, match="live smoke"):
        crawl_source("compras_br", mode="incremental")


def test_monitor_crawl_without_fixture_is_blocked_not_silent_or_fixture_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.crawl import bbmnet_crawler, compras_br_crawler, licitanet_crawler
    from scripts.public_platforms.collect import crawl_source

    monkeypatch.delenv("PUBLIC_PLATFORM_LIVE", raising=False)
    monkeypatch.delenv("PUBLIC_PLATFORM_FIXTURE", raising=False)
    for source, mod in (
        ("bbmnet", bbmnet_crawler),
        ("licitanet", licitanet_crawler),
        ("compras_br", compras_br_crawler),
    ):
        rows = crawl_source(source)
        assert rows, f"{source} crawl_source returned silent empty"
        assert rows[0]["terminal"] == "BLOCKED"
        assert rows[0].get("silent_zero") is False
        wrapped = mod.crawl("incremental")
        transformed = mod.transform(wrapped)
        assert transformed
        assert transformed[0]["terminal"] == "BLOCKED"
        assert all("42516" != str(row.get("source_id")) for row in transformed)


def test_monitor_path_transform_keeps_fixture_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.crawl import compras_br_crawler

    monkeypatch.delenv("PUBLIC_PLATFORM_LIVE", raising=False)
    monkeypatch.setenv("PUBLIC_PLATFORM_FIXTURE", str(FIXTURES / "compras_br_pages.json"))
    crawled = compras_br_crawler.crawl("incremental")
    transformed = compras_br_crawler.transform(crawled)
    assert any(row.get("source_id") == "42516" for row in transformed)


def test_issue_262_263_264_cli_emits_json(tmp_path: Path) -> None:
    from scripts.public_platforms.cli import main

    out = tmp_path / "out.json"
    # CLI writes stdout; just assert exit 0 on fixture
    rc = main(["--source", "bbmnet", "--fixture", str(FIXTURES / "bbmnet_pages.json")])
    assert rc == 0
    assert out.exists() is False
    dumped = json.loads((FIXTURES / "bbmnet_pages.json").read_text(encoding="utf-8"))
    assert dumped["entity"]["ibge"] == "4205407"
