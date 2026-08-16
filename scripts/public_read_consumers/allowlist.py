"""Strip unauthorized fields and refuse PII leakage."""

from __future__ import annotations

from typing import Any

from scripts.public_read_consumers.hashutil import find_pii_fields
from scripts.public_read_consumers.registry import get_consumer

ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "contract_version",
        "consumer_id",
        "consumer",
        "content_hash",
        "catalog_mode",
        "claimed_live",
        "producer_status",
        "official_live",
        "as_of",
        "generated_at",
        "reason_codes",
        "data_state",
        "publication_readiness",
    }
)

XRAY_DENIED_TOKENS = (
    "risco",
    "risk_score",
    "credit",
    "credito",
    "crédito",
    "dor",
    "irregularidade",
    "irregular",
    "capacidade",
    "consentimento",
    "consent",
    "market_share_total",
    "share_total",
)


def _leaf_name(path: str) -> str:
    name = path.split(".")[-1]
    return name.split("[", 1)[0]


def unauthorized_fields(document: dict[str, Any], *, consumer_id: str) -> list[str]:
    record = get_consumer(consumer_id)
    allowed = set(record.get("allowed_fields") or ())
    hits: list[str] = []
    for key in document:
        if key in ENVELOPE_KEYS or key in allowed:
            continue
        hits.append(key)
    return sorted(hits)


def project_allowed(document: dict[str, Any], *, consumer_id: str) -> dict[str, Any]:
    record = get_consumer(consumer_id)
    allowed = set(record.get("allowed_fields") or ())
    return {key: value for key, value in document.items() if key in ENVELOPE_KEYS or key in allowed}


def scan_pii(document: dict[str, Any]) -> list[str]:
    return find_pii_fields(document)


def scan_xray_denied(document: Any, *, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(document, dict):
        for key, value in document.items():
            next_path = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if any(token in lowered for token in XRAY_DENIED_TOKENS):
                hits.append(next_path)
            hits.extend(scan_xray_denied(value, path=next_path))
        return hits
    if isinstance(document, list):
        for index, item in enumerate(document):
            hits.extend(scan_xray_denied(item, path=f"{path}[{index}]"))
        return hits
    if isinstance(document, str):
        lowered = document.lower()
        if any(token in lowered for token in XRAY_DENIED_TOKENS):
            hits.append(path or document)
    return hits
