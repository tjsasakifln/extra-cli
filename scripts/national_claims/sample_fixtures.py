"""Canonical Goal 01–03 fixtures. No PII. No Extra-1.093-as-national."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from scripts.national_claims.lkg import make_lkg
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.models import POLICY_VERSION

AS_OF = "2026-08-15T00:00:00Z"
CUTOFF = "2026-08-15T00:00:00Z"
COMPETENCE = "contratos-2026"


def _national_orgs() -> list[dict[str, Any]]:
    return [
        {"org_id": "org-a", "name": "Orgao A", "unit_count": 1, "geography": "SP"},
        {"org_id": "org-b", "name": "Orgao B", "unit_count": 2, "geography": "RJ"},
        {"org_id": "org-sc", "name": "Orgao SC", "unit_count": 1, "geography": "SC"},
    ]


def _companions() -> dict[str, Any]:
    return {
        "icp_commercial": {
            "official_source": "icp-commercial",
            "competence": COMPETENCE,
            "cutoff": CUTOFF,
            "method_version": "icp-v1",
            "inclusion_rules": ["commercial_icp"],
            "exclusion_rules": ["national_publishing_orgs"],
            "orgs": [
                {"org_id": "icp-1", "name": "ICP Buyer 1", "unit_count": 1},
                {"org_id": "icp-2", "name": "ICP Buyer 2", "unit_count": 1},
            ],
        },
        "extra_1093_monitored": {
            "official_source": "sc_public_entities",
            "competence": COMPETENCE,
            "cutoff": CUTOFF,
            "method_version": "extra-1093-v1",
            "inclusion_rules": ["raio_200km_monitored"],
            "exclusion_rules": ["national_publishing_orgs"],
            "orgs": [
                {"org_id": "ent-001", "name": "Ente monitorado 1", "unit_count": 1},
                {"org_id": "ent-002", "name": "Ente monitorado 2", "unit_count": 1},
            ],
        },
        "observed_corpus": {
            "official_source": "snapshot",
            "competence": COMPETENCE,
            "cutoff": CUTOFF,
            "method_version": "observed-corpus-v1",
            "inclusion_rules": ["rows_present_in_snapshot"],
            "exclusion_rules": ["unobserved_orgs"],
            "orgs": [{"org_id": "org-a", "name": "Orgao A seen", "unit_count": 1}],
        },
    }


def _base_claim(**overrides: Any) -> dict[str, Any]:
    claim = {
        "claim_id": "claim-national-incomplete",
        "scope": "national",
        "period": "2026-01/2026-08",
        "sources": ["pncp"],
        "typology": "contratos",
        "geography": "BR",
        "snapshot": AS_OF,
        "cutoff": CUTOFF,
        "policy_version": POLICY_VERSION,
        "denominator_kind": "national",
        "infer_completeness_from_row_count": False,
    }
    claim.update(overrides)
    return claim


def _base_document() -> dict[str, Any]:
    return {
        "contract_version": "national-claims/1.0",
        "producer_sha": "fixture",
        "source_version": "pncp/1.0",
        "claim": _base_claim(),
        "universes": {
            "national": {
                "official_source": "pncp",
                "competence": COMPETENCE,
                "cutoff": CUTOFF,
                "method_version": "pncp-orgaos-publicantes-v1",
                "inclusion_rules": [
                    "official_publishing_org_catalog",
                    "competence_window",
                    "cutoff_inclusive",
                ],
                "exclusion_rules": [
                    "extra_1093_monitored_entes",
                    "icp_commercial_universe",
                    "observed_corpus_at_snapshot",
                    "row_count_as_completeness",
                ],
                "version_changes": ["initial fixture seed"],
                "owner": "contracts-truth",
                "review_cadence": "weekly",
                "orgs": _national_orgs(),
            },
            **_companions(),
        },
        "partitions": [],
        "evidence": [],
        "freshness": {
            "age_hours": 6,
            "lag_p99_hours": 3,
            "as_of": AS_OF,
            "layer": "publication",
        },
        "prior_lkg": None,
    }


def fixture_needs_data() -> dict[str, Any]:
    document = _base_document()
    document["claim"] = _base_claim(claim_id="claim-national-incomplete")
    document["partitions"] = [
        {
            "partition_id": "org-a",
            "expected": True,
            "attempted": True,
            "status": "FOUND",
            "pages_fetched": 2,
            "pages_expected": 2,
            "records": 4,
            "pagination_complete": True,
            "request_complete": True,
            "evidence_ref": "raw:org-a",
            "identity_mapped": True,
        },
        {
            "partition_id": "org-b",
            "expected": True,
            "attempted": False,
            "status": "UNKNOWN",
            "reason": "execution_absent",
        },
        {
            "partition_id": "org-sc",
            "expected": True,
            "attempted": False,
            "status": "BLOCKED",
            "evidence_ref": "not_consulted_this_run",
            "reason": "not_consulted_this_run",
        },
    ]
    document["evidence"] = [
        {
            "source": "pncp",
            "entity_id": "org-a",
            "canonical_entity_key": "org-a",
            "state": "success_with_data",
            "metadata": {},
        }
    ]
    return document


def fixture_authorized_limited() -> dict[str, Any]:
    document = _base_document()
    document["claim"] = _base_claim(
        claim_id="claim-sc-limited",
        scope="geo_limited",
        geography="SC",
        period="2026-01/2026-03",
    )
    document["partitions"] = [
        {
            "partition_id": "org-sc",
            "expected": True,
            "attempted": True,
            "status": "FOUND",
            "pages_fetched": 1,
            "pages_expected": 1,
            "records": 2,
            "pagination_complete": True,
            "request_complete": True,
            "evidence_ref": "raw:org-sc",
            "identity_mapped": True,
        }
    ]
    document["evidence"] = [
        {
            "source": "pncp",
            "entity_id": "org-sc",
            "canonical_entity_key": "org-sc",
            "state": "success_with_data",
            "metadata": {},
        }
    ]
    return document


def fixture_source_wide_only() -> dict[str, Any]:
    document = _base_document()
    document["claim"] = _base_claim(claim_id="claim-source-wide-only")
    document["partitions"] = [
        {
            "partition_id": "org-a",
            "expected": True,
            "attempted": False,
            "status": "UNKNOWN",
        },
        {
            "partition_id": "org-b",
            "expected": True,
            "attempted": False,
            "status": "UNKNOWN",
        },
        {
            "partition_id": "org-sc",
            "expected": True,
            "attempted": False,
            "status": "UNKNOWN",
        },
    ]
    document["evidence"] = [
        {
            "id": 3,
            "entity_id": None,
            "canonical_entity_key": None,
            "source": "pncp",
            "data_type": "bids",
            "state": "success_with_data",
            "run_id": 22,
            "count_obtained": 800,
            "count_persisted": 800,
            "metadata": {"pipeline": "resilient_cycle"},
        }
    ]
    return document


def fixture_unknown_partition() -> dict[str, Any]:
    document = fixture_needs_data()
    document["claim"] = _base_claim(claim_id="claim-unknown-partition")
    return document


def fixture_stale_lkg() -> dict[str, Any]:
    document = _base_document()
    document["claim"] = _base_claim(claim_id="claim-stale-with-lkg")
    document["freshness"] = {
        "age_hours": 96,
        "lag_p99_hours": 80,
        "as_of": AS_OF,
        "layer": "publication",
    }
    document["partitions"] = [
        {
            "partition_id": org["org_id"],
            "expected": True,
            "attempted": True,
            "status": "FOUND",
            "pages_fetched": 1,
            "pages_expected": 1,
            "records": 1,
            "pagination_complete": True,
            "request_complete": True,
            "evidence_ref": f"raw:{org['org_id']}",
            "identity_mapped": True,
        }
        for org in _national_orgs()
    ]
    authorized = deepcopy(document)
    authorized["freshness"] = {
        "age_hours": 6,
        "lag_p99_hours": 3,
        "as_of": "2026-08-14T00:00:00Z",
        "layer": "publication",
    }
    authorized["claim"] = _base_claim(claim_id="claim-prior-authorized")
    prior_request = request_from_dict(authorized)
    from scripts.national_claims.gate import decide

    prior_payload = decide(prior_request)
    lkg = make_lkg(
        claim_id=prior_payload["claim_id"],
        national_universe_id=prior_payload["national_universe_id"],
        catalog_hash=prior_payload["catalog_hash"],
        method_version=prior_payload["method_version"],
        source_version=prior_payload["source_version"],
        content_hash=prior_payload["content_hash"],
        authorized_at="2026-08-14T00:00:00Z",
        ttl_hours=48,
    )
    document["prior_lkg"] = {
        "claim_id": lkg.claim_id,
        "authorization_state": lkg.authorization_state,
        "national_universe_id": lkg.national_universe_id,
        "catalog_hash": lkg.catalog_hash,
        "method_version": lkg.method_version,
        "source_version": lkg.source_version,
        "content_hash": lkg.content_hash,
        "authorized_at": lkg.authorized_at,
        "expires_at": lkg.expires_at,
    }
    return document


def fixture_authorized_national() -> dict[str, Any]:
    document = _base_document()
    document["claim"] = _base_claim(claim_id="claim-national-fixture-closed")
    document["partitions"] = [
        {
            "partition_id": org["org_id"],
            "expected": True,
            "attempted": True,
            "status": "FOUND" if org["org_id"] != "org-b" else "ZERO_CONFIRMED",
            "pages_fetched": 1,
            "pages_expected": 1,
            "records": 0 if org["org_id"] == "org-b" else 2,
            "pagination_complete": True,
            "request_complete": True,
            "evidence_ref": f"raw:{org['org_id']}",
            "identity_mapped": org["org_id"] != "org-b",
        }
        for org in _national_orgs()
    ]
    document["evidence"] = [
        {
            "source": "pncp",
            "entity_id": "org-a",
            "canonical_entity_key": "org-a",
            "state": "success_with_data",
            "metadata": {},
        }
    ]
    return document


def all_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "needs-data": fixture_needs_data(),
        "authorized-limited": fixture_authorized_limited(),
        "source-wide-only": fixture_source_wide_only(),
        "unknown-partition": fixture_unknown_partition(),
        "stale-lkg": fixture_stale_lkg(),
        "authorized-national": fixture_authorized_national(),
    }
