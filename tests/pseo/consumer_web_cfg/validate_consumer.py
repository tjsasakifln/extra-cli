"""Vendored consumer validation rules from web-cfg scripts/pseo/schema.py (read-only).

Adapted for offline contract tests against extra-cli export snapshots.
Does not import or modify the web-cfg repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# From web-cfg scripts/pseo/schema.py — SCHEMA_VERSIONS_OK
SCHEMA_VERSIONS_OK = frozenset({"1.0.0", "1.1.0"})

# From web-cfg REQUIRED_FILES (icp_methodology is body for hash, not always required file list)
REQUIRED_FILES = [
    "manifest.json",
    "archetypes.json",
    "markets.json",
    "agencies.json",
    "prices.json",
    "competition.json",
    "opportunities.json",
    "problem_service.json",
    "schema.json",
]

DATASET_BODY_KEYS = (
    "archetypes",
    "markets",
    "agencies",
    "prices",
    "competition",
    "opportunities",
    "problem_service",
    "icp_methodology",
)

FORBIDDEN_PATTERNS = [
    re.compile(r'"score_total"\s*:', re.I),
    re.compile(r'"commercial_state"\s*:', re.I),
    re.compile(r'"human_notes"\s*:', re.I),
    re.compile(r'"human_decision"\s*:', re.I),
    re.compile(r'"suggested_offer"\s*:', re.I),
    re.compile(r'"next_human_step"\s*:', re.I),
    re.compile(r'"rank_position"\s*:', re.I),
    re.compile(r'"top20"\s*:', re.I),
    re.compile(r'"do_not_contact"\s*:', re.I),
]


class ConsumerContractError(Exception):
    pass


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_json(data: Any) -> str:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def validate_consumer_snapshot(data_dir: Path) -> dict[str, Any]:
    """Fail-closed consumer contract checks. Raises ConsumerContractError."""
    data_dir = Path(data_dir)
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (data_dir / name).exists():
            errors.append(f"missing file: {name}")
    if errors:
        raise ConsumerContractError("; ".join(errors))

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    sv = manifest.get("schema_version")
    if not sv:
        errors.append("manifest.schema_version missing")
    elif str(sv) not in SCHEMA_VERSIONS_OK:
        errors.append(f"unsupported schema_version for consumer: {sv}")

    for field in (
        "generated_at",
        "source_run_id",
        "dataset_hash",
        "checksums",
        "sources",
        "counts",
        "freshness",
        "limitations",
    ):
        if field not in manifest:
            errors.append(f"manifest missing {field}")

    checksums = manifest.get("checksums") or {}
    for name, expected in checksums.items():
        path = data_dir / name
        if not path.exists():
            errors.append(f"checksum target missing: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        actual = _sha256_text(text)
        if actual != expected:
            errors.append(f"checksum mismatch: {name}")

    # Forbidden commercial fields in raw JSON
    for path in sorted(data_dir.glob("*.json")):
        if path.name in {"export-descriptor.json", "CURRENT.json"}:
            continue
        raw = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(raw):
                errors.append(f"forbidden pattern {pat.pattern} in {path.name}")

    # dataset_hash recompose (consumer algorithm)
    body: dict[str, Any] = {}
    for key in DATASET_BODY_KEYS:
        p = data_dir / f"{key}.json"
        if p.exists():
            body[key] = json.loads(p.read_text(encoding="utf-8"))
    recomputed = _sha256_text(_canonical_json(body))
    if recomputed != manifest.get("dataset_hash"):
        errors.append(
            f"dataset_hash mismatch: manifest={manifest.get('dataset_hash')} recomputed={recomputed}"
        )

    # schema.json must exist and be JSON object
    schema = json.loads((data_dir / "schema.json").read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        errors.append("schema.json must be an object")

    if errors:
        raise ConsumerContractError("; ".join(errors))

    return {
        "ok": True,
        "schema_version": sv,
        "dataset_hash": manifest.get("dataset_hash"),
        "required_files": REQUIRED_FILES,
        "consumer": "web-cfg scripts/pseo/schema.py (vendored rules)",
    }
