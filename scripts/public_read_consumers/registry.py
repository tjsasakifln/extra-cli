"""Named consumer registry. There is no arbitrary public-intelligence query."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = REPO_ROOT / "docs" / "contracts" / "public-read-consumers"
REGISTRY_PATH = CONTRACT_DIR / "registry.json"

REQUIRED_CONSUMER_KEYS = (
    "consumer_id",
    "decision",
    "schema",
    "schema_version",
    "grain",
    "keys",
    "source_tables",
    "allowed_fields",
    "value_semantics",
    "evidence_refs",
    "as_of",
    "freshness",
    "coverage",
    "unknown_policy",
    "suppression_policy",
    "max_rows",
    "pagination",
    "cache",
    "fail_closed_reason_codes",
    "invalidation_keys",
)


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("registry must be an object")
    return payload


def consumer_records() -> list[dict[str, Any]]:
    records = load_registry().get("consumers") or []
    if not isinstance(records, list):
        raise ValueError("registry.consumers must be a list")
    return [dict(item) for item in records if isinstance(item, dict)]


def list_consumer_ids() -> list[str]:
    return [str(item["consumer_id"]) for item in consumer_records() if item.get("consumer_id")]


def get_consumer(consumer_id: str) -> dict[str, Any]:
    aliases = {
        "contract-analysis": "web-cfg/contract-analysis",
        "web-cfg/contract-analysis": "web-cfg/contract-analysis",
        "market-answer": "web-cfg/market-answer/valor-tipico-contratos-pavimentacao",
        "market-answer-pavimentacao": "web-cfg/market-answer/valor-tipico-contratos-pavimentacao",
        "web-cfg/market-answer/valor-tipico-contratos-pavimentacao": (
            "web-cfg/market-answer/valor-tipico-contratos-pavimentacao"
        ),
        "b2g-xray": "web-cfg/b2g-xray",
        "xray": "web-cfg/b2g-xray",
        "web-cfg/b2g-xray": "web-cfg/b2g-xray",
    }
    resolved = aliases.get(consumer_id, consumer_id)
    for item in consumer_records():
        if item.get("consumer_id") == resolved:
            return item
    raise KeyError(f"unknown_consumer:{consumer_id}")


def load_consumer_contract(consumer_id: str) -> dict[str, Any]:
    record = get_consumer(consumer_id)
    rel = record.get("contract_path")
    if not rel:
        raise ValueError(f"consumer_missing_contract_path:{consumer_id}")
    path = REPO_ROOT / str(rel)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_consumer_record(record: dict[str, Any]) -> list[str]:
    missing = [key for key in REQUIRED_CONSUMER_KEYS if key not in record]
    return [f"missing:{key}" for key in missing]


def validate_registry() -> dict[str, Any]:
    errors: list[str] = []
    ids = list_consumer_ids()
    expected = {
        "web-cfg/contract-analysis",
        "web-cfg/market-answer/valor-tipico-contratos-pavimentacao",
        "web-cfg/b2g-xray",
    }
    if set(ids) != expected:
        errors.append(f"consumer_set_mismatch:{sorted(ids)}")
    if load_registry().get("generic_query_endpoint"):
        errors.append("generic_query_endpoint_forbidden")
    for record in consumer_records():
        errors.extend(f"{record.get('consumer_id')}:{item}" for item in validate_consumer_record(record))
    return {"ok": not errors, "errors": errors, "consumer_ids": ids}
