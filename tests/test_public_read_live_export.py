"""Live/snapshot path of the shipped research-flagship export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.public_read.claim_gate import evaluate_national_claim
from scripts.public_read.export import EXPORT_FILENAME, render_export_bytes, write_research_export
from scripts.public_read.live_payload import payload_from_live_corpus, payload_from_snapshot_document

REPO = Path(__file__).resolve().parents[1]


def _denominator() -> dict:
    return {
        "source": "pncp",
        "competence": "contratos-2026",
        "cutoff": "2026-08-15T00:00:00Z",
        "method": "pncp-orgaos-publicantes-v1",
        "nacional_completo": False,
        "orgs": [
            {
                "org_id": "83102277000152",
                "source": "pncp",
                "competence": "contratos-2026",
                "name": "PREFEITURA MUNICIPAL DE ITAJAI",
                "unit_count": 1,
            },
            {
                "org_id": "99999999000191",
                "source": "pncp",
                "competence": "contratos-2026",
                "name": "ORGAO BLOQUEADO",
                "unit_count": 1,
            },
        ],
        "partitions": [
            {
                "partition_id": "83102277000152",
                "status": "FOUND",
                "evidence": "observed_official_contract:83102277000152",
            },
            {
                "partition_id": "99999999000191",
                "status": "BLOCKED",
                "evidence": "not_consulted_this_run",
            },
        ],
    }


def _contracts() -> list[dict]:
    return [
        {
            "contrato_id": "83102277000152-2-000626/2026",
            "uf": "SC",
            "valor_total": "740874.59",
            "source": "pncp_contracts",
            "source_id": "83102277000152-2-000626/2026",
            "ingested_at": "2026-08-14T11:27:51+00:00",
        }
    ]


def test_live_corpus_refuses_national_claim_when_302_incomplete() -> None:
    payload = payload_from_live_corpus(
        contracts=_contracts(),
        denominator=_denominator(),
        as_of="2026-08-15T00:00:00Z",
        competence="contratos-2026",
        publication_age_hours=2.0,
        publication_lag_p99_hours=2.0,
        payload_id="live-corpus",
    )
    decision = evaluate_national_claim(payload)
    assert decision.nacional_completo is False
    assert decision.national_claim_allowed is False
    document = json.loads(render_export_bytes(payload))
    assert document["schema"] == "public-read-research-flagship/1.0"
    assert document["claim"]["national_claim_allowed"] is False
    assert document["claim"]["publishable_geography"] is None
    assert all(cell["geography_code"] != "BR" for cell in document["series"])
    assert "national_denominator_incomplete" in document["claim"]["reason_codes"]
    assert "CONFENGE" not in json.dumps(document)


def test_snapshot_not_ready_is_explicit() -> None:
    with pytest.raises(ValueError, match="snapshot_not_ready"):
        payload_from_snapshot_document({"state": "BUILDING", "contracts": []})


def test_shipped_cli_live_contracts_twice(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts.jsonl"
    contracts.write_text(json.dumps(_contracts()[0]) + "\n", encoding="utf-8")
    denominator = tmp_path / "denom.json"
    denominator.write_text(json.dumps(_denominator()), encoding="utf-8")
    out_1 = tmp_path / "r1"
    out_2 = tmp_path / "r2"
    command = [
        sys.executable,
        "-m",
        "scripts.public_read",
        "export-research",
        "--contracts-jsonl",
        str(contracts),
        "--denominator",
        str(denominator),
        "--as-of",
        "2026-08-15T00:00:00Z",
        "--competence",
        "contratos-2026",
        "--publication-age-hours",
        "2",
        "--publication-lag-p99-hours",
        "2",
    ]
    first = subprocess.run(
        [*command, "--out", str(out_1)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [*command, "--out", str(out_2)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    bytes_1 = (out_1 / EXPORT_FILENAME).read_bytes()
    bytes_2 = (out_2 / EXPORT_FILENAME).read_bytes()
    assert bytes_1 == bytes_2
    artifact = json.loads(bytes_1)
    assert artifact["claim"]["national_claim_allowed"] is False
    assert json.loads(first.stdout)["content_hash"] == json.loads(second.stdout)["content_hash"]
    health = subprocess.run(
        [sys.executable, "-m", "scripts.public_read", "health", "--artifact", str(out_1)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    health_doc = json.loads(health.stdout)
    assert health_doc["national_claim_allowed"] is False
    assert health_doc["coverage_status"] in {"INCOMPLETE", "UNKNOWN"}
    payload = payload_from_live_corpus(
        contracts=_contracts(),
        denominator=_denominator(),
        as_of="2026-08-15T00:00:00Z",
        competence="contratos-2026",
        publication_age_hours=2.0,
        publication_lag_p99_hours=2.0,
        payload_id="live-corpus",
    )
    assert write_research_export(payload, tmp_path / "r3").read_bytes() == bytes_1
