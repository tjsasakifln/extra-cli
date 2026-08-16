"""Versioned comparable-contracts/1.0 serializer and content hash."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.contract_comparables.constants import (
    CATALOG_FIXTURE,
    CONSUMER_FAMILY,
    CONSUMER_ID,
    CONTRACT_VERSION,
    FORBIDDEN_CLAIM_TOKENS,
    FORBIDDEN_METRIC_KEYS,
    METHOD_VERSION,
    OFFICIAL_LIVE,
    POLICY_VERSION,
    QUESTION,
    QUESTION_ID,
    REASON_FIXTURE_NOT_LIVE,
    REASON_STATISTICAL_DIFF,
    SCHEMA,
    SCHEMA_ALIAS,
    STATUS_COMPARABLE,
    VALUE_SEMANTIC_CANONICAL,
)
from scripts.contract_comparables.models import PeerGroupResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "contract-comparables" / "comparable-contracts-v1.json"

REQUIRED_DOCUMENT_FIELDS = (
    "schema",
    "accepted_schemas",
    "contract_version",
    "method_version",
    "policy_version",
    "peer_group_id",
    "contract_id",
    "target_contract_id",
    "status",
    "question",
    "question_id",
    "consumer",
    "as_of",
    "inclusion_rules",
    "exclusion_rules",
    "typology",
    "typology_confidence",
    "geography",
    "period",
    "regime",
    "modality",
    "porte",
    "value_semantic",
    "unit",
    "monetary_normalization",
    "universe",
    "coverage",
    "denominator",
    "total_n",
    "usable_n",
    "peer_count",
    "missingness",
    "suppression",
    "outlier_treatment",
    "peer_ids",
    "peer_refs",
    "evidence_refs",
    "match_quality",
    "metrics",
    "percentiles",
    "reason_codes",
    "limitations",
    "method",
    "freshness",
    "catalog_mode",
    "source",
    "content_hash",
    "producer_sha",
)


def canonical_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash_for(payload: dict[str, Any]) -> str:
    copy = {key: value for key, value in payload.items() if key != "content_hash"}
    return hashlib.sha256(canonical_dumps(copy).encode("utf-8")).hexdigest()


def producer_sha(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("CONTRACT_COMPARABLES_PRODUCER_SHA")
    if env:
        return env
    if not Path("/usr/bin/git").is_file():
        return "unknown"
    try:
        sha = subprocess.check_output(
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = subprocess.call(
            ["/usr/bin/git", "diff", "--quiet"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return sha if dirty == 0 else f"{sha}-dirty"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def peer_group_id(seed: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_dumps(seed).encode("utf-8")).hexdigest()
    return f"pg-{digest[:16]}"


def _assert_no_forbidden_language(payload: dict[str, Any]) -> None:
    blob = fold_for_scan(canonical_dumps(payload))
    for token in FORBIDDEN_CLAIM_TOKENS:
        if fold_for_scan(token) in blob:
            raise ValueError(f"forbidden claim language in document: {token}")
    metrics = payload.get("metrics") or {}
    for key in FORBIDDEN_METRIC_KEYS:
        if key in metrics:
            raise ValueError(f"forbidden metric key: {key}")


def fold_for_scan(text: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(character for character in nfkd if not unicodedata.combining(character))


def serialize_result(result: PeerGroupResult) -> dict[str, Any]:
    request = result.request
    focal = result.focal
    peer_ids = [peer.recorte.contract.contract_id for peer in result.peers]
    evidence_refs = [
        ref
        for ref in [focal.contract.evidence_ref, *[peer.recorte.contract.evidence_ref for peer in result.peers]]
        if ref
    ]
    match_quality = [
        {
            "contract_id": peer.recorte.contract.contract_id,
            "distance": peer.match_distance,
            "quality": peer.match_quality,
        }
        for peer in result.peers
    ]
    metrics_public = result.metrics.as_public_dict() if result.metrics else {}
    percentiles = (metrics_public.get("valor") or {}).get("percentiles") or {}
    reason_codes = list(result.reason_codes)
    if request.catalog_mode == CATALOG_FIXTURE and REASON_FIXTURE_NOT_LIVE not in reason_codes:
        reason_codes.append(REASON_FIXTURE_NOT_LIVE)
    if result.metrics and result.metrics.outlier_flag and REASON_STATISTICAL_DIFF not in reason_codes:
        reason_codes.append(REASON_STATISTICAL_DIFF)
    if request.catalog_mode == OFFICIAL_LIVE:
        raise ValueError("this producer never labels a fixture or incomplete live slice official_live")
    seed = {
        "schema": SCHEMA,
        "method_version": METHOD_VERSION,
        "policy_version": request.policy_version or POLICY_VERSION,
        "question_id": request.question_id,
        "consumer_id": request.consumer_id,
        "focal": focal.contract.contract_id,
        "as_of": request.as_of,
        "typology": focal.typology,
        "geography": {"uf": focal.uf, "region": focal.region},
        "period": {"year": focal.year},
        "regime": focal.regime,
        "value_semantic": VALUE_SEMANTIC_CANONICAL,
        "peer_ids": peer_ids,
        "status": result.status,
    }
    group_id = peer_group_id(seed)
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "accepted_schemas": [SCHEMA, SCHEMA_ALIAS],
        "contract_version": CONTRACT_VERSION,
        "method_version": METHOD_VERSION,
        "policy_version": request.policy_version or POLICY_VERSION,
        "peer_group_id": group_id,
        "contract_id": focal.contract.contract_id,
        "target_contract_id": focal.contract.contract_id,
        "canonical_contract_ids": [focal.contract.contract_id],
        "status": result.status,
        "question": QUESTION,
        "question_id": QUESTION_ID,
        "consumer": {"id": request.consumer_id or CONSUMER_ID, "family": CONSUMER_FAMILY},
        "as_of": request.as_of,
        "inclusion_rules": list(result.inclusion_rules),
        "exclusion_rules": list(result.exclusion_rules),
        "typology": {
            "label": focal.typology,
            "confidence": focal.typology_confidence,
            "scope": focal.scope,
        },
        "typology_confidence": focal.typology_confidence,
        "geography": {"uf": focal.uf, "region": focal.region, "municipio": focal.contract.municipio},
        "period": {"year": focal.year, "data_referencia": focal.contract.data_referencia},
        "regime": focal.regime,
        "modality": focal.modalidade,
        "porte": focal.porte,
        "value_semantic": focal.value_semantic,
        "unit": focal.unit,
        "monetary_normalization": request.monetary_normalization,
        "universe": {
            "total_n": result.total_n,
            "eligible_n": result.eligible_n,
            "usable_n": result.usable_n,
            "source": request.source,
        },
        "coverage": {
            "usable_over_total": round(result.coverage, 4),
            "missingness": round(result.missingness, 4),
            "eligible_n": result.eligible_n,
        },
        "denominator": {
            "kind": "usable_known_valor_integral_nominal",
            "unknown_policy": "UNKNOWN_never_zero_never_silent_denominator",
            "n": result.usable_n,
        },
        "total_n": result.total_n,
        "usable_n": result.usable_n,
        "peer_count": result.usable_n,
        "missingness": {"ratio": round(result.missingness, 4), "unknown_excluded": True},
        "suppression": {"peer_ids_emitted": not result.suppressed, "aggregate_only": result.suppressed},
        "outlier_treatment": result.outlier_treatment,
        "peer_ids": peer_ids if not result.suppressed else [],
        "peer_refs": (
            [{"contract_id": item, "authorized": True} for item in peer_ids] if not result.suppressed else []
        ),
        "peers": [peer.as_dict() for peer in result.peers] if not result.suppressed else [],
        "comparisons": [peer.as_dict() for peer in result.peers] if not result.suppressed else [],
        "evidence_refs": evidence_refs,
        "match_quality": match_quality,
        "metrics": metrics_public,
        "percentiles": percentiles,
        "reason_codes": reason_codes,
        "limitations": list(result.limitations),
        "method": {
            "id": METHOD_VERSION,
            "policy": request.policy_version or POLICY_VERSION,
            "question_id": QUESTION_ID,
            "no_llm": True,
            "no_embeddings_authority": True,
        },
        "freshness": {
            "policy": "contracts-freshness-slo-v1",
            "as_of": request.as_of,
            "max_age_hours": 48,
        },
        "catalog_mode": request.catalog_mode,
        "source": request.source,
        "producer_sha": producer_sha(request.producer_sha),
        "exclusions": [item.as_dict() for item in result.exclusions],
        "valid": None,
    }
    if result.status != STATUS_COMPARABLE:
        document["metrics"] = metrics_public
    document.pop("valid", None)
    if "valid" in document:
        raise AssertionError("official comparable-contracts/1.0 documents must not emit valid")
    document["content_hash"] = content_hash_for(document)
    for field in REQUIRED_DOCUMENT_FIELDS:
        if field not in document:
            raise ValueError(f"missing required document field: {field}")
    if document["catalog_mode"] == OFFICIAL_LIVE:
        raise ValueError("official_live is forbidden unless a live official pack is proven")
    if document["catalog_mode"] == CATALOG_FIXTURE and document["source"] != "fixture":
        raise ValueError("fixture catalog_mode requires source=fixture")
    _assert_no_forbidden_language(document)
    return document


def validate_against_schema(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_DOCUMENT_FIELDS:
        if field not in document:
            errors.append(f"missing:{field}")
    if document.get("schema") not in {SCHEMA, SCHEMA_ALIAS}:
        errors.append("schema")
    if document.get("status") not in {"COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE"}:
        errors.append("status")
    if "valid" in document:
        errors.append("unexpected_valid")
    if document.get("catalog_mode") == OFFICIAL_LIVE:
        errors.append("official_live")
    hashed = content_hash_for(document)
    if document.get("content_hash") != hashed:
        errors.append("content_hash")
    if SCHEMA_PATH.exists():
        try:
            import jsonschema
        except ImportError:
            return errors
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        errors.extend(f"{'/'.join(str(part) for part in error.path)}: {error.message}" for error in validator.iter_errors(document))
    return errors
