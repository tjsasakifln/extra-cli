"""Drive the shipped #302 live denominator builder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.national_contract_truth.live_universe import (
    build_denominator_report,
    close_partitions,
    parse_orgaos_catalog,
    run_live_universe,
)
from scripts.national_contract_truth.national_universe import sha256_payload

REPO = Path(__file__).resolve().parents[1]

OFFICIAL_CATALOG = [
    {"cnpj": "83102277000152", "razaoSocial": "PREFEITURA MUNICIPAL DE ITAJAI"},
    {"cnpj": "03563335000106", "razaoSocial": "PREFEITURA MUNICIPAL DE APARECIDA DO TABOADO"},
    {"cnpj": "99999999000191", "razaoSocial": "ORGAO AINDA NAO CONSULTADO"},
]


def test_parse_official_catalog_and_replay_hash() -> None:
    raw = json.dumps(OFFICIAL_CATALOG).encode("utf-8")
    orgs = parse_orgaos_catalog(raw)
    assert [org.org_id for org in orgs] == [
        "83102277000152",
        "03563335000106",
        "99999999000191",
    ]
    again = parse_orgaos_catalog(raw)
    assert again == orgs


def test_unconsulted_partitions_block_nacional_completo() -> None:
    orgs = parse_orgaos_catalog(OFFICIAL_CATALOG)
    partitions = close_partitions(orgs, observed_org_ids={"83102277000152", "03563335000106"})
    report = build_denominator_report(
        competence="contratos-2026",
        cutoff="2026-08-15",
        orgs=orgs,
        partitions=partitions,
        raw_hash=sha256_payload(OFFICIAL_CATALOG),
    )
    assert report["extra_1093_used_as_denominator"] is False
    assert report["nacional_completo"] is False
    assert report["by_status"]["FOUND"] == 2
    assert report["by_status"]["BLOCKED"] == 1
    assert "blocked_or_failed_partitions" in report["publish_blockers"]
    replay = build_denominator_report(
        competence="contratos-2026",
        cutoff="2026-08-15",
        orgs=orgs,
        partitions=partitions,
        raw_hash=sha256_payload(OFFICIAL_CATALOG),
    )
    assert replay["catalog_hash"] == report["catalog_hash"]
    assert replay["reconciliation_hash"] == report["reconciliation_hash"]


def test_run_live_universe_from_official_bytes() -> None:
    raw = json.dumps(OFFICIAL_CATALOG).encode("utf-8")
    report = run_live_universe(
        competence="contratos-2026",
        cutoff="2026-08-15T00:00:00Z",
        observed_org_ids={"83102277000152"},
        catalog_raw=raw,
    )
    assert report["source"] == "pncp"
    assert report["nacional_completo"] is False
    assert report["extra_1093_used_as_denominator"] is False
    assert report["org_count"] == 3


def test_shipped_cli_writes_denominator(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(OFFICIAL_CATALOG), encoding="utf-8")
    observed = tmp_path / "observed.txt"
    observed.write_text("83102277000152\n", encoding="utf-8")
    out = tmp_path / "national-denominator.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.national_contract_truth.live_universe",
            "--competence",
            "contratos-2026",
            "--cutoff",
            "2026-08-15T00:00:00Z",
            "--catalog-json",
            str(catalog),
            "--observed-orgs",
            str(observed),
            "--out",
            str(out),
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert summary["nacional_completo"] is False
    assert report["extra_1093_used_as_denominator"] is False
    assert report["by_status"]["FOUND"] == 1
    assert report["by_status"]["BLOCKED"] == 2
