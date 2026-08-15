"""Deterministic margin-defense export. No brand marks in the truth plane."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.public_read.export import assert_truth_plane_clean, canonical_dumps
from scripts.public_read.margin_defense import (
    FORBIDDEN_CONCLUSION_FIELDS,
    SCHEMA,
    project_margin_facts,
)

EXPORT_FILENAME = "margem-export.json"
CONTRACT_PATH = "docs/contracts/public-read-margin-defense-v1.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILE = REPO_ROOT / CONTRACT_PATH


def load_margin_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def _payload_records(raw: dict[str, Any] | list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(raw, list):
        raise ValueError("payload as_of is required")
    records = raw.get("records") or raw.get("contracts") or []
    as_of = str(raw.get("as_of") or "")
    if not as_of:
        raise ValueError("payload as_of is required")
    return as_of, list(records)


def _freshness_hours(as_of: str, observed_at: str | None) -> float | None:
    if not observed_at:
        return None
    try:
        cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (cutoff - observed).total_seconds() / 3600.0)


def build_margin_export(raw: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    contract = load_margin_contract()
    as_of, records = _payload_records(raw)
    facts = [project_margin_facts(record, as_of=as_of) for record in records]
    reason_codes = sorted({code for item in facts for code in item.reason_codes})
    known = sum(item.known_count for item in facts)
    field_total = sum(len(item.fields) for item in facts)
    coverage_ratio = "0" if field_total == 0 else format(known / field_total, ".6f")
    ages = [_freshness_hours(as_of, item.observed_at) for item in facts]
    measured_ages = [age for age in ages if age is not None]
    freshness_hours = max(measured_ages) if measured_ages else None
    stale = freshness_hours is not None and freshness_hours > float(contract["freshness"]["max_age_hours"])
    document = {
        "schema": SCHEMA,
        "contract_version": contract["contract_version"],
        "contract_path": CONTRACT_PATH,
        "consumer": {
            "id": contract["consumer"]["id"],
            "repository": contract["consumer"]["repository"],
            "issues": contract["consumer"]["issues"],
        },
        "wedge": contract["wedge"],
        "grain": contract["grain"],
        "keys": contract["keys"],
        "source_families": contract["source_families"],
        "value_semantics": contract["value_semantics"],
        "as_of": as_of,
        "freshness": {
            **contract["freshness"],
            "publication_age_hours": freshness_hours,
            "status": "STALE" if stale else "FRESH" if freshness_hours is not None else "UNKNOWN",
        },
        "coverage": {
            "record_count": len(facts),
            "known_fields": known,
            "field_total": field_total,
            "ratio": coverage_ratio,
            "status": "INCOMPLETE" if reason_codes else "COMPLETE",
        },
        "provenance": {
            "input_kind": "payload",
            "record_count": len(facts),
            "source_ids": sorted({item.source_id for item in facts if item.source_id}),
        },
        "reason_codes": reason_codes,
        "unknown": {
            "policy": contract["value_semantics"]["unknown_policy"],
            "reason_codes": reason_codes,
        },
        "forbidden_conclusion_fields": sorted(FORBIDDEN_CONCLUSION_FIELDS),
        "records": [item.as_dict() for item in facts],
    }
    assert_truth_plane_clean(document)
    present = set(document) & FORBIDDEN_CONCLUSION_FIELDS
    if present:
        raise ValueError(f"forbidden_conclusion_fields:{sorted(present)}")
    for item in document["records"]:
        leaked = FORBIDDEN_CONCLUSION_FIELDS.intersection(item) | FORBIDDEN_CONCLUSION_FIELDS.intersection(
            item.get("fields", {})
        )
        if leaked:
            raise ValueError(f"forbidden_conclusion_fields:{sorted(leaked)}")
    hashed = canonical_dumps(document)
    document["content_hash"] = hashlib.sha256(hashed.encode("utf-8")).hexdigest()
    return document


def render_margin_bytes(raw: dict[str, Any] | list[dict[str, Any]]) -> bytes:
    return canonical_dumps(build_margin_export(raw)).encode("utf-8")


def write_margin_export(raw: dict[str, Any] | list[dict[str, Any]], output_dir: str | Path) -> Path:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / EXPORT_FILENAME
    path.write_bytes(render_margin_bytes(raw))
    return path
