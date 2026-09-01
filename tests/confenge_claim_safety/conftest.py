"""Fixtures for the claim-safety audit.

The feed builder is adapted from ``tests/test_confenge_feed_publication.py::_build``
(the only existing builder that satisfies ``_validate_authoritative_manifest``);
it is generalized here to take an arbitrary lead list so the claim-safety tests
can exercise ``--apply`` / ``rollback`` end to end on an isolated feed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.confenge_outreach_pipeline.party_role import PARTY_ROLE_POLICY_V1
from scripts.confenge_target_fit.company_key import canonical_target_membership

# The publication validator enforces a live source-freshness budget, so the feed
# fixture has to be generated "now" rather than pinned to a wall-clock literal.
NOW = datetime.now(UTC)
TODAY = NOW.date()

ADDENDUM_UNSAFE_TEXT = "Aditivos/alterações observados em contrato público recente ou ativo."
PORTFOLIO_REVIEW_TEXT = (
    "Em 2026-09-01, fato contratual público utilizável sem dor especializada dominante — "
    "objeto: {objeto}; órgão: {orgao}; UF {uf}."
)


def contract(
    *,
    contract_id: str,
    objeto: str,
    end_date: str | None,
    start_date: str | None = None,
    status: str | None = None,
    agency: str = "SECRETARIA DE ESTADO DA INFRAESTRUTURA",
    uf: str = "RR",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": contract_id,
        "object": objeto,
        "agency": agency,
        "uf": uf,
        "start_date": start_date,
        "end_date": end_date,
    }
    if status is not None:
        payload["status"] = status
    return payload


def lead(
    *,
    cnpj14: str,
    why_now_code: str,
    why_now: str,
    contracts: list[dict[str, Any]] | None = None,
    fact_to_mention: str | None = None,
) -> dict[str, Any]:
    contracts = contracts or []
    if fact_to_mention is None and contracts:
        first = contracts[0]
        fact_to_mention = f"objeto: {str(first['object'])[:140]}; órgão: {first['agency']}; UF {first['uf']}; R$ 1,000"
    return {
        "source_lead_id": f"target-fit:{cnpj14[:8]}:{cnpj14}",
        "company": {"cnpj14": cnpj14, "razao_social": f"EMPRESA {cnpj14[:8]}"},
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit_version": "confenge-target-fit-v2",
        "email_send_ready": True,
        "contractor_role": {
            "policy_version": PARTY_ROLE_POLICY_V1,
            "status": "CONTRACTOR_ROLE_CONFIRMED",
            "target_party_role": "SUPPLIER",
        },
        "contacts": [
            {
                "email": f"licitacao@{cnpj14[:8]}.example.com",
                "route_class": "ROLE_OR_DEPARTMENT",
                "source": "public_company_registry",
                "preferred_initial": True,
            }
        ],
        "contracts": contracts,
        "messaging_context": {
            "why_now_code": why_now_code,
            "why_now": why_now,
            "fact_to_mention": fact_to_mention or "",
        },
        "moment": {"code": why_now_code, "summary": why_now},
    }


def _serialize(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def build_feed(
    root: Path,
    leads: list[dict[str, Any]],
    *,
    snapshot: str = "snapshot-claim-safety",
    generated_at: datetime = NOW,
) -> Path:
    """Write an isolated feed directory that ``atomic_publish_directory`` accepts."""
    root.mkdir(parents=True, exist_ok=True)
    generated = generated_at.isoformat().replace("+00:00", "Z")
    source = {
        "system": "extra-cli",
        "run_id": f"run-{snapshot}",
        "snapshot_hash": snapshot,
        "repo_sha": "claim-safety-test",
        "datalake_watermark": generated,
    }
    chunk = {
        "schema_version": "confenge.outreach.v1",
        "generated_at": generated,
        "source": source,
        "pagination": {"chunk_index": 0, "has_more": False},
        "leads": leads,
    }
    raw = _serialize(chunk)
    (root / "chunk_0000.json").write_bytes(raw)

    cnpjs = [str(item["company"]["cnpj14"]) for item in leads]
    membership = canonical_target_membership(cnpjs)
    count = len(leads)
    manifest: dict[str, Any] = {
        "schema_version": "confenge.outreach.manifest.v1",
        "generated_at": generated,
        "source": source,
        "lead_count": count,
        "chunk_count": 1,
        "chunks": [
            {
                "file": "chunk_0000.json",
                "chunk_index": 0,
                "content_hash": hashlib.sha256(raw).hexdigest(),
                "byte_count": len(raw),
                "lead_count": count,
                "has_more": False,
            }
        ],
        "max_bytes_per_chunk": 512_000,
        "total_chunk_bytes": len(raw),
        "authoritative_target_fit": {
            "coverage_complete": True,
            "omission_preserves_authorization": False,
            "full_decision_count": count,
            "universe_count": count,
            "declared_universe_count": count,
            "shipped_lead_count": count,
            "feed_scope": "TARGET_CONFIRMED_MEMBERSHIP",
            "decision_class_distribution": {"TARGET_CONFIRMED": count},
            "ordering": {"watermarks_monotonic": True},
        },
        "authoritative_feed_scope": {
            "scope": "TARGET_CONFIRMED_MEMBERSHIP",
            "identity_key": "cnpj_root8",
            "decision_universe_count": count,
            "shipped_lead_count": count,
            "withheld_decision_count": 0,
            "branch_duplicates_collapsed": 0,
            "membership_hash_reproduced_from_feed": True,
        },
        "authoritative_target_membership": {
            **membership,
            "target_fit_class": "TARGET_CONFIRMED",
            "target_confirmed_count": count,
            "supplier_confirmed_count": count,
            "source_member_count": count,
            "membership_complete": True,
            "target_fit_policy_versions": ["confenge-target-fit-v2"],
            "target_party_role_distribution": {"SUPPLIER": count},
            "contractor_role_status_distribution": {"CONTRACTOR_ROLE_CONFIRMED": count},
        },
        "authoritative_party_roles": {
            "policy_version": PARTY_ROLE_POLICY_V1,
            "target_party_role_distribution": {"SUPPLIER": count},
            "status_distribution": {"CONTRACTOR_ROLE_CONFIRMED": count},
            "supplier_confirmed_count": count,
            "buyer_supplier_conflict_fails_closed": True,
        },
        "authoritative_source_freshness": {
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": "FRESH",
            "expires_at": (generated_at + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        },
        "authoritative_contact_projection": {
            "schema_id": "confenge.contact_discovery.projection_report.v1",
            "report_sha256": "a" * 64,
            "cohort_id": "cohort-claim-safety",
            "generated_at": generated,
            "population_hash": "b" * 64,
            "population_as_of": generated,
            "population_as_of_source": "target_fit_full_reconcile",
            "population_verified_at": generated,
            "population_coverage_ratio": 1.0,
            "population_publication_ready": True,
            "projection_hash": "c" * 64,
            "controlled_email_policy_version": "controlled-email-policy.v3",
            "discovery_policy_version": "dui.policy.v1",
            "input_evidence_version": "target-fit.test",
            "code_sha": "claim-safety-test",
            "coverage_complete": True,
            "terminal_coverage_complete": True,
            "terminal_equation": {"holds": True},
            "population_count": count,
            "membership_schema_version": membership["schema_version"],
            "membership_identity_key": membership["identity_key"],
            "membership_hash_algorithm": membership["hash_algorithm"],
            "membership_count": count,
            "membership_hash": membership["membership_hash"],
            "enrichment_states": {"EMAIL_ROUTE_READY": count},
            "recipient_states": {
                "RECIPIENT_ATTRIBUTED": count,
                "READY": count,
                "NO_PUBLIC_EMAIL_FOUND": 0,
                "BLOCKED_WITH_REASON": 0,
            },
            "output_preferred_route_class_distribution": {"ROLE_OR_DEPARTMENT": count},
            "input_declared": True,
            "input_preferred_route_count": count,
            "output_preferred_route_count": count,
            "preferred_routes_reconciled": True,
            "input_preferred_routes_hash": "preferred-route-hash",
            "output_preferred_routes_hash": "preferred-route-hash",
        },
        "deactivations": [],
        "deactivation_count": 0,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def default_leads() -> list[dict[str, Any]]:
    """One unsafe ADDENDUM lead (past end_date) plus one safe PORTFOLIO_REVIEW lead."""
    unsafe_contract = contract(
        contract_id="27532498000190-2-000011/2026",
        objeto=(
            "Acréscimo no valor e no prazo dos serviços de reforma em salas do prédio sede do "
            "Tribunal de Contas do Município do Rio de Janeiro - TCMRio, sob regime de Empreitada."
        ),
        end_date="2026-06-15",
    )
    safe_contract = contract(
        contract_id="53576563000199-2-000029/2026",
        objeto=(
            "Contratação de empresa especializada em execução de obras de EMPREENDIMENTOS "
            "HABITACIONAIS para construção de 50 (cinquenta) unidades habitacionais."
        ),
        end_date="2027-01-21",
    )
    return [
        lead(
            cnpj14="03518914000137",
            why_now_code="ADDENDUM",
            why_now=ADDENDUM_UNSAFE_TEXT,
            contracts=[unsafe_contract],
        ),
        lead(
            cnpj14="12345678000195",
            why_now_code="PORTFOLIO_REVIEW",
            why_now=PORTFOLIO_REVIEW_TEXT.format(
                objeto=str(safe_contract["object"])[:140],
                orgao=safe_contract["agency"],
                uf=safe_contract["uf"],
            ),
            contracts=[safe_contract],
        ),
    ]


@pytest.fixture()
def feed_dir(tmp_path: Path) -> Path:
    return build_feed(tmp_path / "build", default_leads())


@pytest.fixture()
def publish_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    """``(publish_dir, state_path, alert_ledger)`` for an isolated publication."""
    return tmp_path / "public", tmp_path / "state.json", tmp_path / "alerts.jsonl"
