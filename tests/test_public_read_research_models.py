"""Drive the shipped research-flagship gate, series and export (#400)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.public_read.claim_gate import evaluate_national_claim
from scripts.public_read.contract import CONTRACT_PATH, load_contract
from scripts.public_read.export import (
    EXPORT_FILENAME,
    assert_truth_plane_clean,
    build_export_document,
    render_export_bytes,
    write_research_export,
)
from scripts.public_read.payload import load_research_payload

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_research"
FAIL_CLOSED = (
    "missing_partitions",
    "stale",
    "unknown_values",
    "duplicated_source_lineage",
    "inconsistent_denominator",
)
EXPECTED_REASON = {
    "missing_partitions": "missing_partitions",
    "stale": "freshness_stale",
    "unknown_values": "unknown_values",
    "duplicated_source_lineage": "duplicated_source_lineage",
    "inconsistent_denominator": "inconsistent_denominator_extra_1093",
}
_CLAIM_LANGUAGE = re.compile(r"\b(brasil|nacional)\b", re.IGNORECASE)
_STRUCTURAL_KEYS = frozenset(
    {
        "nacional_completo",
        "national_claim_allowed",
        "national_universe_id",
        "national_denominator_incomplete",
    }
)


def _payload(name: str):
    return load_research_payload(FIXTURES / f"{name}.json")


def _string_values(node: object, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            if key in _STRUCTURAL_KEYS:
                continue
            found.extend(_string_values(value, next_path))
        return found
    if isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_string_values(item, f"{path}[{index}]"))
        return found
    if isinstance(node, str):
        found.append((path, node))
    return found


def test_contract_declares_consumer_grain_and_budget() -> None:
    contract = load_contract()
    assert contract["schema"] == "public-read-research-flagship/1.0"
    assert contract["consumer"]["id"] == "web-cfg/flagship-research"
    assert "#73" in contract["consumer"]["pull_requests"]
    assert contract["wedge"]["id"] == "contracts-prices-margin-defense"
    assert contract["grain"]
    assert contract["keys"] == [
        "competence",
        "geography_kind",
        "geography_code",
        "archetype_id",
    ]
    assert contract["query_budget"]["query_family"] == "research_flagship_series"
    assert CONTRACT_PATH.is_file()


def test_full_coverage_is_the_only_authorized_national_claim() -> None:
    allowed = evaluate_national_claim(_payload("full_coverage"))
    assert allowed.national_claim_allowed is True
    assert allowed.nacional_completo is True
    assert allowed.reason_codes == ()
    assert allowed.extra_1093_used_as_denominator is False

    for name in FAIL_CLOSED:
        decision = evaluate_national_claim(_payload(name))
        assert decision.national_claim_allowed is False, name
        assert decision.reason_codes, name
        assert EXPECTED_REASON[name] in decision.reason_codes, (name, decision.reason_codes)


def test_export_document_carries_contract_fields_and_provenance() -> None:
    document = build_export_document(_payload("full_coverage"))
    assert document["grain"]
    assert document["keys"]
    assert document["as_of"]
    assert document["denominator"]["authority"] == "national_universe/1.0"
    assert document["freshness"]["policy"] == "contracts-freshness-slo-v1"
    assert document["completeness"]
    assert document["provenance"]["catalog_hash"]
    assert document["provenance"]["reconciliation_hash"]
    assert document["unknown"]["reason_codes"] == []
    assert document["query_budget"]["max_rows"] == 64
    assert document["claim"]["national_claim_allowed"] is True
    assert document["claim"]["publishable_geography"] == "BR"
    assert any(cell["geography_code"] == "BR" for cell in document["series"])
    assert_truth_plane_clean(document)


@pytest.mark.parametrize("name", FAIL_CLOSED)
def test_fail_closed_export_refuses_national_claim_language(name: str) -> None:
    document = build_export_document(_payload(name))
    assert document["claim"]["national_claim_allowed"] is False
    assert document["claim"]["reason_codes"]
    assert document["claim"]["publishable_geography"] is None
    assert document["claim"]["publishable_claim"] is None
    assert all(cell["geography_code"] != "BR" for cell in document["series"])
    for path, value in _string_values(document):
        assert not _CLAIM_LANGUAGE.search(value), (name, path, value)
    raw = json.dumps(document, ensure_ascii=False)
    assert "CONFENGE" not in raw
    assert "confenge" not in raw.lower()
    assert "Brasil" not in raw


def test_unknown_value_stays_unknown_in_series() -> None:
    document = build_export_document(_payload("unknown_values"))
    unknown_cells = [cell for cell in document["series"] if cell["value_status"] == "UNKNOWN"]
    assert unknown_cells
    assert all(cell["total_value_brl"] is None for cell in unknown_cells)
    assert "unknown_values" in document["claim"]["reason_codes"]


def test_inconsistent_denominator_never_uses_1093_as_closed_universe() -> None:
    decision = evaluate_national_claim(_payload("inconsistent_denominator"))
    assert decision.extra_1093_used_as_denominator is True
    assert decision.nacional_completo is False
    assert decision.national_claim_allowed is False
    assert "inconsistent_denominator_extra_1093" in decision.reason_codes


def test_render_export_bytes_is_deterministic() -> None:
    payload = _payload("full_coverage")
    first = render_export_bytes(payload)
    second = render_export_bytes(payload)
    assert first == second
    assert b"CONFENGE" not in first


def test_shipped_cli_export_twice_and_fail_closed(tmp_path: Path) -> None:
    fixture = FIXTURES / "full_coverage.json"
    out_1 = tmp_path / "full-1"
    out_2 = tmp_path / "full-2"
    fail_out = tmp_path / "fail"
    command = [sys.executable, "-m", "scripts.public_read", "export-research"]
    first = subprocess.run(
        [*command, "--fixture", str(fixture), "--out", str(out_1)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [*command, "--fixture", str(fixture), "--out", str(out_2)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    fail = subprocess.run(
        [
            *command,
            "--fixture",
            str(FIXTURES / "missing_partitions.json"),
            "--out",
            str(fail_out),
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    bytes_1 = (out_1 / EXPORT_FILENAME).read_bytes()
    bytes_2 = (out_2 / EXPORT_FILENAME).read_bytes()
    assert bytes_1 == bytes_2
    artifact = json.loads(bytes_1)
    fail_artifact = json.loads((fail_out / EXPORT_FILENAME).read_bytes())
    assert artifact["claim"]["national_claim_allowed"] is True
    assert fail_artifact["claim"]["national_claim_allowed"] is False
    assert fail_artifact["claim"]["reason_codes"]
    assert all(cell["geography_code"] != "BR" for cell in fail_artifact["series"])
    assert "CONFENGE" not in bytes_1.decode("utf-8")
    assert '"ok": true' in first.stdout.lower() or '"ok":true' in first.stdout.replace(" ", "").lower()
    assert json.loads(first.stdout)["content_hash"] == json.loads(second.stdout)["content_hash"]
    assert json.loads(fail.stdout)["national_claim_allowed"] is False

    health = subprocess.run(
        [sys.executable, "-m", "scripts.public_read", "health", "--artifact", str(out_1)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    health_doc = json.loads(health.stdout)
    assert health_doc["freshness_status"] == "FRESH"
    assert health_doc["coverage_status"] == "COMPLETE"
    assert "consumer_error_count" in health_doc


def test_write_research_export_matches_render(tmp_path: Path) -> None:
    payload = _payload("full_coverage")
    path = write_research_export(payload, tmp_path)
    assert path.read_bytes() == render_export_bytes(payload)


def test_migration_094_is_additive_select_only() -> None:
    sql = (REPO / "db" / "migrations" / "094_public_intelligence_research_models.sql").read_text(encoding="utf-8")
    assert "094 was free" in sql
    assert "CREATE SCHEMA" not in sql
    assert "DROP VIEW IF EXISTS public_read_v1.contracts" not in sql
    assert "DROP COLUMN" not in sql
    assert "GRANT SELECT ON public_read_v1.research_flagship_series" in sql
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "REVOKE INSERT, UPDATE, DELETE" in sql
    assert "smartlic_public_reader" in sql
    assert "research_flagship_series" in sql
    assert "research_claim_gate" in sql
    assert "research_health" in sql
    v1 = (REPO / "docs" / "contracts" / "public-read-v1.md").read_text(encoding="utf-8")
    assert "v1.1.0" in v1
    assert "No v1.0.0 column was removed" in v1
