"""Evidence pack serialization, volatile stripping, and SHA-256 sums."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.ops.coverage_live_proof import EVIDENCE_SCHEMA_VERSION

VOLATILE_KEYS: frozenset[str] = frozenset(
    {
        "workflow_run_id",
        "run_id",
        "duration_seconds",
        "duration_ms",
        "started_at",
        "finished_at",
        "generated_at",
        "timestamp",
        "ephemeral_database",
        "proof_dsn_sanitized",
        "admin_dsn_sanitized",
    }
)


def strip_volatiles(value: Any) -> Any:
    """Remove timestamps, run IDs, and ephemeral names before the semantic hash."""
    if isinstance(value, dict):
        return {
            key: strip_volatiles(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [strip_volatiles(item) for item in value]
    return value


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def normalize_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = strip_volatiles(payload)
    if not isinstance(normalized, dict):
        raise TypeError("normalized evidence must be an object")
    return normalized


def semantic_hash(normalized: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_evidence_pack(output_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Write evidence.json, evidence.normalized.json, SHA256SUMS.

    ``normalized_semantic_hash`` is computed from the stripped payload and
    then stored on both the full and normalized documents.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    working = dict(payload)
    working.setdefault("evidence_schema_version", EVIDENCE_SCHEMA_VERSION)
    normalized = normalize_evidence(working)
    digest = semantic_hash(normalized)
    working["normalized_semantic_hash"] = digest
    normalized["normalized_semantic_hash"] = digest

    evidence_path = output_dir / "evidence.json"
    normalized_path = output_dir / "evidence.normalized.json"
    sums_path = output_dir / "SHA256SUMS"

    evidence_path.write_text(
        json.dumps(working, indent=2, sort_keys=True, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    normalized_path.write_bytes(canonical_json_bytes(normalized) + b"\n")

    artifacts = {
        "evidence.json": sha256_file(evidence_path),
        "evidence.normalized.json": sha256_file(normalized_path),
    }
    sums_lines = [f"{digest}  {name}" for name, digest in artifacts.items()]
    sums_path.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    artifacts["SHA256SUMS"] = sha256_file(sums_path)
    working["artifacts"] = artifacts
    # Rewrite evidence.json so the artifact hashes are part of the durable pack.
    evidence_path.write_text(
        json.dumps(working, indent=2, sort_keys=True, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    artifacts["evidence.json"] = sha256_file(evidence_path)
    sums_lines = [
        f"{artifacts['evidence.json']}  evidence.json",
        f"{artifacts['evidence.normalized.json']}  evidence.normalized.json",
    ]
    sums_path.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    artifacts["SHA256SUMS"] = sha256_file(sums_path)
    return {
        "payload": working,
        "normalized": normalized,
        "normalized_semantic_hash": digest,
        "artifacts": artifacts,
        "paths": {
            "evidence.json": str(evidence_path),
            "evidence.normalized.json": str(normalized_path),
            "SHA256SUMS": str(sums_path),
        },
    }
