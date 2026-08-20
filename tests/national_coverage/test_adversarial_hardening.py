"""Adversarial fail-closed cases on the shipped evaluate path."""

from __future__ import annotations

import pytest

from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import NationalCoverageError


def test_evaluate_refuses_extra_1093_as_official_source() -> None:
    with pytest.raises(NationalCoverageError, match="forbidden_national_source"):
        evaluate_from_dict(
            {
                "official": {
                    "status": "AVAILABLE",
                    "source": "extra_1093",
                    "source_url": "https://example.invalid/extra-1093",
                    "competence": "contratos-2026",
                    "cutoff": "2026-08-16T00:00:00Z",
                    "as_of": "2026-08-16T00:00:00Z",
                    "raw_hash": "raw-extra",
                    "orgs": [{"org_id": "11111111000191", "name": "A", "unit_count": 1, "uf": "SC"}],
                },
                "request": {"geography": "BR", "period": "2026", "source": "pncp", "grain": "publishing_org"},
            }
        )


def test_one_hundred_percent_sc_still_not_national() -> None:
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": "https://pncp.gov.br/api/pncp/v1/orgaos",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
                "retrieved_at": "2026-08-16T00:00:00Z",
                "raw_hash": "raw-sc-100",
                "orgs": [
                    {"org_id": "11111111000191", "name": "Orgao SC", "unit_count": 1, "uf": "SC"},
                    {"org_id": "22222222000191", "name": "Orgao SP", "unit_count": 1, "uf": "SP"},
                ],
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [
                    {
                        "raw_org_id": "11111111000191",
                        "contract_count": 4,
                        "uf": "SC",
                        "last_seen": "2026-08-16T00:00:00Z",
                    }
                ],
            },
            "request": {"geography": "SC", "period": "2026", "source": "pncp", "grain": "publishing_org"},
        }
    )
    assert payload["partitions"]["expected"] == payload["partitions"]["closed"]
    assert payload["partitions"]["closed"] == 1
    assert payload["consumer"]["coverage_pct"] == 100.0
    assert payload["national_claim_authorized"] is False
    assert payload["verdict"] == "PARTIAL"
    assert payload["consumer"]["requested_geography"] == "SC"


def test_blocked_official_never_emits_numeric_national_coverage() -> None:
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "BLOCKED",
                "block_cause": "official_catalog_unavailable",
                "source": "pncp",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [{"raw_org_id": "11111111000191", "contract_count": 99, "uf": "SC"}],
            },
            "request": {"geography": "BR", "period": "2026", "source": "pncp", "grain": "publishing_org"},
        }
    )
    assert payload["verdict"] == "BLOCKED"
    assert payload["national_claim_authorized"] is False
    assert payload["consumer"]["coverage_pct"] is None
    assert payload["universe"]["universe_kind"] == "OBSERVED_CORPUS"


def test_unconsulted_partition_is_not_zero_confirmed() -> None:
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": "https://pncp.gov.br/api/pncp/v1/orgaos",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
                "raw_hash": "raw-unconsulted",
                "orgs": [
                    {"org_id": "11111111000191", "name": "A", "unit_count": 1, "uf": "SC"},
                    {"org_id": "22222222000191", "name": "B", "unit_count": 1, "uf": "SP"},
                ],
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [{"raw_org_id": "11111111000191", "contract_count": 1, "uf": "SC"}],
            },
            "consulted": {"use_observed_as_found": True},
            "request": {"geography": "BR", "period": "2026", "source": "pncp", "grain": "publishing_org"},
        }
    )
    assert payload["partitions"]["by_status"].get("ZERO_CONFIRMED", 0) == 0
    assert payload["partitions"]["by_status"]["BLOCKED"] >= 1
    assert payload["national_claim_authorized"] is False
    assert "unconsulted_partitions_remain" in payload["reason_codes"]


def test_stale_last_seen_is_measured_but_does_not_authorize_national() -> None:
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": "https://pncp.gov.br/api/pncp/v1/orgaos",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
                "raw_hash": "raw-stale",
                "orgs": [{"org_id": "11111111000191", "name": "A", "unit_count": 1, "uf": "SC"}],
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [
                    {
                        "raw_org_id": "11111111000191",
                        "contract_count": 1,
                        "uf": "SC",
                        "last_seen": "2020-01-01T00:00:00Z",
                    }
                ],
            },
            "consulted": {"zero_confirmed": {}},
            "freshness": {"window_hours": 48, "as_of": "2026-08-16T00:00:00Z"},
            "request": {"geography": "BR", "period": "2026", "source": "pncp", "grain": "publishing_org"},
        }
    )
    assert payload["freshness"]["stale_found"] >= 1
    assert payload["national_claim_authorized"] is False
