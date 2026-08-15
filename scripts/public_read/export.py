"""Deterministic research-flagship export. No brand marks in the truth plane."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.public_read.claim_gate import ClaimDecision, evaluate_national_claim
from scripts.public_read.contract import FORBIDDEN_TRUTH_BRANDS, load_contract, query_budget
from scripts.public_read.models import ResearchPayload
from scripts.public_read.observability import observe_research_health
from scripts.public_read.series import project_series

EXPORT_FILENAME = "research-export.json"
_CLAIM_LANGUAGE = re.compile(r"\b(brasil|nacional)\b", re.IGNORECASE)
_STRUCTURAL_KEYS = frozenset(
    {
        "nacional_completo",
        "national_claim_allowed",
        "national_universe_id",
        "national_claim_rule",
        "national_denominator_incomplete",
    }
)


def canonical_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scan_forbidden_language(node: Any, *, allowed: bool, path: str = "") -> list[str]:
    if allowed:
        return []
    hits: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            if key in _STRUCTURAL_KEYS:
                hits.extend(_scan_forbidden_language(value, allowed=allowed, path=next_path))
                continue
            if _CLAIM_LANGUAGE.search(str(key)):
                hits.append(next_path)
            hits.extend(_scan_forbidden_language(value, allowed=allowed, path=next_path))
        return hits
    if isinstance(node, list):
        for index, item in enumerate(node):
            hits.extend(_scan_forbidden_language(item, allowed=allowed, path=f"{path}[{index}]"))
        return hits
    if isinstance(node, str) and _CLAIM_LANGUAGE.search(node):
        hits.append(path or node)
    return hits


def assert_truth_plane_clean(document: dict[str, Any] | bytes | str) -> None:
    raw = (
        document
        if isinstance(document, (bytes, bytearray))
        else (document if isinstance(document, str) else canonical_dumps(document))
    )
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    for brand in FORBIDDEN_TRUTH_BRANDS:
        if brand.lower() in text.lower():
            raise ValueError("truth plane contains forbidden brand mark")


def build_export_document(payload: ResearchPayload) -> dict[str, Any]:
    contract = load_contract()
    claim = evaluate_national_claim(payload)
    series = project_series(payload, claim)
    health = observe_research_health(payload, claim)
    document = {
        "schema": contract["schema"],
        "contract_version": contract["contract_version"],
        "contract_path": "docs/contracts/public-read-research-flagship-v1.json",
        "consumer": {
            "id": contract["consumer"]["id"],
            "repository": contract["consumer"]["repository"],
            "issues": contract["consumer"]["issues"],
            "pull_requests": contract["consumer"]["pull_requests"],
        },
        "wedge": {
            "id": contract["wedge"]["id"],
            "label": contract["wedge"]["label"],
        },
        "grain": contract["grain"],
        "keys": contract["keys"],
        "source_families": contract["source_families"],
        "value_semantics": {
            "contract_value": contract["value_semantics"]["contract_value"],
            "ticket_percentiles": contract["value_semantics"]["ticket_percentiles"],
            "unknown_policy": contract["value_semantics"]["unknown_policy"],
        },
        "as_of": payload.as_of,
        "freshness": contract["freshness"],
        "completeness": health["coverage_status"],
        "denominator": {
            "authority": "national_universe/1.0",
            "extra_1093_used_as_denominator": claim.extra_1093_used_as_denominator,
            "expected_partitions": claim.expected_partitions,
            "closed_partitions": claim.closed_partitions,
        },
        "provenance": {
            "fixture_id": payload.fixture_id,
            "catalog_hash": claim.catalog_hash,
            "reconciliation_hash": claim.reconciliation_hash,
            "national_universe_id": claim.national_universe_id,
            "method": payload.universe.method,
        },
        "query_budget": query_budget(),
        "query_budgets": contract["query_budgets"],
        "claim": {
            "national_claim_allowed": claim.national_claim_allowed,
            "nacional_completo": claim.nacional_completo,
            "reason_codes": list(claim.reason_codes),
            "extra_1093_used_as_denominator": claim.extra_1093_used_as_denominator,
            "publishable_geography": "BR" if claim.national_claim_allowed else None,
            "publishable_claim": (
                "Series covers the closed publishing-org denominator." if claim.national_claim_allowed else None
            ),
        },
        "series": series,
        "health": health,
        "unknown": {
            "policy": "UNKNOWN remains UNKNOWN",
            "reason_codes": list(claim.reason_codes),
        },
    }
    assert_truth_plane_clean(document)
    language_hits = _scan_forbidden_language(document, allowed=claim.national_claim_allowed)
    if language_hits:
        raise ValueError(f"refused claim language in fail-closed export: {language_hits}")
    hashed = canonical_dumps(document)
    document["content_hash"] = hashlib.sha256(hashed.encode("utf-8")).hexdigest()
    return document


def render_export_bytes(payload: ResearchPayload) -> bytes:
    return canonical_dumps(build_export_document(payload)).encode("utf-8")


def write_research_export(payload: ResearchPayload, output_dir: str | Path) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / EXPORT_FILENAME
    path.write_bytes(render_export_bytes(payload))
    return path


def load_export_artifact(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def claim_decision_from_artifact(artifact: dict[str, Any]) -> ClaimDecision:
    claim = artifact["claim"]
    health = artifact["health"]
    return ClaimDecision(
        national_claim_allowed=bool(claim["national_claim_allowed"]),
        nacional_completo=bool(claim["nacional_completo"]),
        reason_codes=tuple(claim.get("reason_codes") or ()),
        catalog_hash=artifact.get("provenance", {}).get("catalog_hash"),
        reconciliation_hash=artifact.get("provenance", {}).get("reconciliation_hash"),
        national_universe_id=artifact.get("provenance", {}).get("national_universe_id"),
        extra_1093_used_as_denominator=bool(claim.get("extra_1093_used_as_denominator")),
        expected_partitions=int(health.get("coverage_partitions_expected") or 0),
        closed_partitions=int(health.get("coverage_partitions_closed") or 0),
        reconciliation={},
    )
