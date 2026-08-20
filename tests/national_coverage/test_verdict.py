"""Fail-closed verdicts from the shipped evaluate path."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.national_coverage.evaluate import evaluate_from_dict

FIXTURES = Path("docs/contracts/national-coverage/fixtures")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_partial_fixture_does_not_authorize_national() -> None:
    first = evaluate_from_dict(_load("official-partial.json"))
    second = evaluate_from_dict(_load("official-partial.json"))
    assert first["verdict"] == "PARTIAL"
    assert first["national_claim_authorized"] is False
    assert first["national_universe_id"] == second["national_universe_id"]
    assert first["catalog_hash"] == second["catalog_hash"]
    assert first["content_hash"] == second["content_hash"]
    assert first["partitions"]["expected"] == 3
    assert first["partitions"]["closed"] == 2
    assert first["partitions"]["by_status"]["FOUND"] == 1
    assert first["partitions"]["by_status"]["ZERO_CONFIRMED"] == 1
    assert first["partitions"]["by_status"]["BLOCKED"] == 1
    assert "partitions_not_closed" in first["reason_codes"]
    consumer = first["consumer"]
    assert consumer["national_claim_authorized"] is False
    assert consumer["coverage_pct"] is not None
    assert 0 < consumer["coverage_pct"] < 100


def test_closed_toy_authorizes_only_when_every_partition_closes() -> None:
    payload = evaluate_from_dict(_load("official-closed-toy.json"))
    assert payload["verdict"] == "NATIONAL_CLAIM_AUTHORIZED"
    assert payload["national_claim_authorized"] is True
    assert payload["partitions"]["expected"] == payload["partitions"]["closed"]
    assert payload["partitions"]["by_status"]["BLOCKED"] == 0
    assert payload["partitions"]["by_status"]["FAILED"] == 0


def test_national_scope_against_partial_is_not_authorized() -> None:
    payload = evaluate_from_dict(_load("official-partial.json"))
    assert payload["consumer"]["requested_geography"] == "BR"
    assert payload["verdict"] != "NATIONAL_CLAIM_AUTHORIZED"
    assert payload["national_claim_authorized"] is False


def test_sc_scope_may_be_partial_but_never_flips_national_boolean() -> None:
    payload = evaluate_from_dict(_load("sc-scope.json"))
    assert payload["consumer"]["requested_geography"] == "SC"
    assert payload["verdict"] == "PARTIAL"
    assert payload["national_claim_authorized"] is False
    assert payload["partitions"]["by_status"]["NOT_APPLICABLE"] == 2
    assert payload["partitions"]["expected"] == 1
    assert payload["partitions"]["closed"] == 1
    assert "partial_does_not_authorize_national" in payload["reason_codes"]


def test_uf_sliced_same_org_is_found_not_duplicate() -> None:
    """SELECT grain is (org, uf). One CNPJ in two UFs must map FOUND, not DUPLICATE."""
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": "https://pncp.gov.br/api/pncp/v1/orgaos",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "retrieved_at": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
                "raw_hash": "raw-uf-slice",
                "method_version": "pncp-orgaos-publicantes-v1",
                "orgs": [
                    {"org_id": "11111111000191", "name": "Orgao A", "unit_count": 1, "uf": "SC"},
                    {"org_id": "22222222000191", "name": "Orgao B", "unit_count": 1, "uf": "SP"},
                ],
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [
                    {
                        "raw_org_id": "11111111000191",
                        "contract_count": 2,
                        "uf": "SC",
                        "last_seen": "2026-08-15T00:00:00Z",
                    },
                    {
                        "raw_org_id": "11111111000191",
                        "contract_count": 3,
                        "uf": "PR",
                        "last_seen": "2026-08-14T00:00:00Z",
                    },
                ],
            },
            "consulted": {"zero_confirmed": {"22222222000191": "raw:empty-complete"}},
            "request": {
                "geography": "BR",
                "period": "2026-01/2026-08",
                "source": "pncp",
                "grain": "publishing_org",
            },
        }
    )
    assert payload["mapping"]["duplicate"] == 0
    assert payload["mapping"]["mapped"] >= 1
    assert payload["partitions"]["by_status"]["FOUND"] == 1
    assert payload["partitions"]["by_status"]["ZERO_CONFIRMED"] == 1
    assert payload["partitions"]["by_status"]["BLOCKED"] == 0
    assert payload["universe"]["retrieved_at"] == "2026-08-16T00:00:00Z"
    assert payload["consumer"]["provenance"]["retrieved_at"] == "2026-08-16T00:00:00Z"
    assert payload["consumer"]["provenance"]["as_of"] == "2026-08-16T00:00:00Z"


def test_blocked_official_national_request() -> None:
    payload = evaluate_from_dict(_load("official-blocked-observed.json"))
    assert payload["verdict"] == "BLOCKED"
    assert payload["national_claim_authorized"] is False
    assert payload["universe"]["universe_kind"] == "OBSERVED_CORPUS"
    assert payload["consumer"]["coverage_pct"] is None
    assert "official_denominator_blocked" in payload["reason_codes"]
