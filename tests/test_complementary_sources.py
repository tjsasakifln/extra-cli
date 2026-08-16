"""In-repo contracts for never-worked complementary sources #250 #253 #266 #257 #258 #259 #265."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.complementary.arp import persist_window
from scripts.complementary.dados_abertos import (
    merge_lineage_with_sc_compras,
    run_inventory,
    schema_drift,
)
from scripts.complementary.licitacoes_e import classify_surface
from scripts.complementary.mides import redact_secrets, run_bounded_job
from scripts.complementary.portals import bind_entity, detect_platform, run_portal
from scripts.crawl import (
    arp_lake,
    betha_atende_crawler,
    betha_egov_crawler,
    ipm_crawler,
    licitacoes_e_crawler,
)
from scripts.crawl.registry import lookup

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "complementary"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.complementary.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_registry_wires_new_sources() -> None:
    assert lookup("pncp_arp") is not None
    assert lookup("dados_abertos_sc") is not None
    assert lookup("betha_atende") is not None
    assert lookup("ipm") is not None
    assert lookup("betha_egov") is not None
    assert lookup("licitacoes_e") is not None
    assert lookup("arp").name == "pncp_arp"
    assert lookup("ipm").name == "ipm"
    assert "ipam" not in lookup("ipm").aliases


def test_arp_persist_idempotent_and_skip_is_not_success() -> None:
    pages = _load("arp_pages.json")["pages"]
    lake: dict = {}
    first = persist_window(pages, lake=lake)
    second = persist_window(pages, lake=lake)
    assert first.terminal == "success"
    assert first.fetched == 2
    assert {r["official_id"] for r in first.records} == {"ATA-001", "ATA-002"}
    assert all(r.get("vigencia_fim") or r.get("status") for r in first.records)
    assert first.job["authority"] == "staging_memory"
    assert second.deduplicated == 2
    skipped = persist_window(pages, skipped=True)
    assert skipped.terminal == "skipped"
    assert skipped.terminal != "success"


def test_arp_memory_staging_is_not_postgres_authority() -> None:
    pages = _load("arp_pages.json")["pages"]
    result = persist_window(pages)
    assert result.job["authority"] != "postgresql_local"
    assert result.job["table"] == "canonical_arp_atas"


@pytest.mark.real_db
def test_arp_writes_official_ids_to_local_postgres() -> None:
    import psycopg2

    from scripts.testing.real_db_guard import canonical_dsn, dsn_is_reachable

    dsn = canonical_dsn()
    if not dsn_is_reachable(dsn):
        pytest.skip("canonical LOCAL_DATALAKE_DSN is not reachable")
    pages = _load("arp_pages.json")["pages"]
    conn = psycopg2.connect(dsn)
    try:
        first = persist_window(pages, conn=conn)
        assert first.job["authority"] == "postgresql_local"
        assert first.terminal == "success"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT official_id FROM public.canonical_arp_atas WHERE official_id IN %s",
                (("ATA-001", "ATA-002"),),
            )
            found = {row[0] for row in cur.fetchall()}
        assert found == {"ATA-001", "ATA-002"}
        second = persist_window(pages, conn=conn)
        assert second.deduplicated >= 1
    finally:
        conn.close()


def test_dados_abertos_dedup_keeps_sc_compras_lineage() -> None:
    payload = _load("dados_abertos_packages.json")
    result = run_inventory(
        payload["packages"],
        processed_ids=set(payload["processed_ids"]),
        sc_compras_rows=payload["sc_compras"],
    )
    matched = [row for row in result.records if row.get("matched_sc_compras")]
    assert matched, "expected a Dados Abertos row to match SC Compras"
    for row in matched:
        sources = {link["source"] for link in row["lineage"]}
        assert "sc_compras" in sources
        assert "dados_abertos_sc" in sources
        sc_link = next(link for link in row["lineage"] if link["source"] == "sc_compras")
        assert sc_link["source_id"] == "SC-PREGAO-2024-01"
        assert "compras.sc.gov.br" in sc_link["url"]
    dropped = merge_lineage_with_sc_compras(
        [{"resource_id": "r1", "objeto": "pregao eletronico 2024", "url": "https://dados.sc/x"}],
        [{"source_id": "SC-PREGAO-2024-01", "objeto": "pregao eletronico 2024", "url": "https://www.compras.sc.gov.br/x"}],
    )
    if not any(link.get("source") == "sc_compras" for link in dropped[0].get("lineage", [])):
        raise AssertionError("SC Compras lineage must survive dedup")


def test_dados_abertos_inventory_and_schema_drift() -> None:
    payload = _load("dados_abertos_packages.json")
    ok = run_inventory(payload["packages"], processed_ids=set(payload["processed_ids"]))
    assert ok.terminal == "success"
    assert {r["resource_id"] for r in ok.records} == {"res-2024-csv", "res-2025-csv"}
    assert all(r.get("url") and r.get("hash") for r in ok.records)
    incomplete = run_inventory(payload["packages"], processed_ids={"res-2024-csv"})
    assert incomplete.terminal == "partial"
    drift = schema_drift(payload["packages"][0]["resources"][0], ["foo"], ["id", "objeto"])
    assert "objeto" in drift
    failed = run_inventory(payload["packages"], processed_ids=set(payload["processed_ids"]), drift=drift)
    assert failed.terminal == "FAILED"


def test_mides_blocked_without_creds_and_budget() -> None:
    blocked = run_bounded_job(interval="2024", estimated_bytes=10, rows=[], env={})
    assert blocked.terminal == "BLOCKED"
    assert "GOOGLE_APPLICATION_CREDENTIALS" in (blocked.reason or "")
    over = run_bounded_job(
        interval="2024",
        estimated_bytes=99,
        rows=[{"x": 1}],
        env={"GOOGLE_APPLICATION_CREDENTIALS": "/etc/passwd"},
        budget_bytes=10,
    )
    assert over.terminal == "BLOCKED"
    assert "budget" in (over.reason or "")
    ok = run_bounded_job(
        interval="2024-01/2024-12",
        estimated_bytes=100,
        rows=[{"id_municipio": "4205407"}],
        job_id="j1",
        env={"GOOGLE_APPLICATION_CREDENTIALS": "/etc/passwd"},
        budget_bytes=1000,
    )
    assert ok.terminal == "success"
    assert ok.job["job_id"] == "j1"
    assert ok.job["hash"]
    leaked = redact_secrets("creds=/secret/path.json", env={"GOOGLE_APPLICATION_CREDENTIALS": "/secret/path.json"})
    assert "/secret/path.json" not in leaked


def test_registry_crawl_never_returns_silent_empty() -> None:
    for mod, source in (
        (betha_atende_crawler, "betha_atende"),
        (ipm_crawler, "ipm"),
        (betha_egov_crawler, "betha_egov"),
        (licitacoes_e_crawler, "licitacoes_e"),
        (arp_lake, "pncp_arp"),
    ):
        rows = mod.crawl("full")
        assert rows, f"{source} crawl() returned silent empty list"
        assert rows[0]["terminal"] in {"BLOCKED", "NOT_APPLICABLE", "FAILED"}
        assert rows[0].get("silent_zero") is False
        assert rows[0]["source"] == source


def test_ipm_and_egov_fixtures_drive_shipped_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLEMENTARY_FIXTURE", str(FIXTURES / "portal_ipm_ipmbrasil.json"))
    first = ipm_crawler.crawl("incremental")
    assert first[0]["source_id"] == "IPM-BR-1"
    assert detect_platform(_load("portal_ipm_ipmbrasil.json")["binding"]["url"]) == "ipm"

    monkeypatch.setenv("COMPLEMENTARY_FIXTURE", str(FIXTURES / "portal_ipm_portaldecompras.json"))
    second = ipm_crawler.crawl("incremental")
    assert second[0]["source_id"] == "IPM-PC-77"
    assert detect_platform(_load("portal_ipm_portaldecompras.json")["binding"]["url"]) == "ipm"
    assert {first[0]["source_id"], second[0]["source_id"]} == {"IPM-BR-1", "IPM-PC-77"}

    monkeypatch.setenv("COMPLEMENTARY_FIXTURE", str(FIXTURES / "portal_egov_municipio.json"))
    egov = betha_egov_crawler.crawl("full")
    assert egov[0]["source_id"] == "EGOV-FLN-3"
    assert "Florianopolis" in str(egov[0].get("orgao") or "")
    assert detect_platform(_load("portal_egov_municipio.json")["binding"]["url"]) == "betha_egov"


def test_portals_detect_and_block() -> None:
    assert detect_platform("https://x.atende.net/licitacoes") == "betha_atende"
    assert detect_platform("https://foo.e-gov.betha.com.br/lic") == "betha_egov"
    assert detect_platform("https:// pref.betha.com.br/x".replace(" ", "")) is None
    assert detect_platform("https://portal.ipmbrasil.com.br/lic") == "ipm"
    assert detect_platform("https://ipam.org.br/x") is None
    bound = bind_entity(
        "https://x.atende.net/lic",
        cnpj="83.102.337/0001-81",
        ibge="4205407",
        municipio="Floripa",
    )
    assert bound["bound"] is True
    ok = run_portal(
        platform="betha_atende",
        pages=[{"status": 200, "complete": True, "payload": {"data": [{"id": "1", "objeto": "x"}]}}],
        binding=bound,
    )
    assert ok.terminal == "success"
    captcha = run_portal(
        platform="betha_atende",
        pages=[{"status": 200, "body": "please solve captcha", "payload": {"data": []}}],
        binding=bound,
    )
    assert captcha.terminal == "BLOCKED"


def test_licitacoes_e_deprecation_is_not_zero() -> None:
    result = classify_surface(_load("licitacoes_e_deprecated.json"))
    assert result.terminal == "NOT_APPLICABLE"
    assert result.terminal != "success"
    restricted = classify_surface({"status": 403, "restricted": True, "body": "login"})
    assert restricted.terminal == "BLOCKED"


def test_cli_twice_stable() -> None:
    cases = [
        ("arp", FIXTURES / "arp_pages.json", None),
        ("dados-abertos", FIXTURES / "dados_abertos_packages.json", None),
        ("mides", FIXTURES / "mides_job.json", None),
        ("portal", FIXTURES / "portal_atende.json", "betha_atende"),
        ("portal", FIXTURES / "portal_ipm_ipmbrasil.json", "ipm"),
        ("portal", FIXTURES / "portal_ipm_portaldecompras.json", "ipm"),
        ("portal", FIXTURES / "portal_egov_municipio.json", "betha_egov"),
        ("licitacoes-e", FIXTURES / "licitacoes_e_deprecated.json", None),
    ]
    for source, path, platform in cases:
        args = [source, "--fixture", str(path)]
        if platform:
            args.extend(["--platform", platform])
        first = _cli(*args)
        second = _cli(*args)
        assert first.returncode == second.returncode, source
        assert first.stdout == second.stdout, source
        payload = json.loads(first.stdout)
        assert payload["source"]
        assert payload["terminal"]
