"""In-repo contracts for never-worked complementary sources #250 #253 #266 #257 #258 #259 #265."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.complementary.arp import persist_window
from scripts.complementary.dados_abertos import run_inventory, schema_drift
from scripts.complementary.licitacoes_e import classify_surface
from scripts.complementary.mides import redact_secrets, run_bounded_job
from scripts.complementary.portals import bind_entity, detect_platform, run_portal
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
    assert second.deduplicated == 2
    skipped = persist_window(pages, skipped=True)
    assert skipped.terminal == "skipped"
    assert skipped.terminal != "success"


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
