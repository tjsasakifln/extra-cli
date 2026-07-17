from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.coverage.coverage_contract import (
    FIXED_CANONICAL_DENOMINATOR,
    compute_operational_source_coverage,
    load_sla_config,
)


def _write_registry(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _evidence(*, verified: bool = True, provenance: bool = True) -> dict:
    evidence = {
        "type": "coverage_evidence",
        "dry_run": False,
        "stages": {
            "mapped": True,
            "accessible": True,
            "collected": True,
            "normalized": True,
            "reconciled": True,
            "verified_within_sla": verified,
        },
    }
    if provenance:
        evidence.update(
            {
                "pipeline_run_id": "run-1",
                "raw_uri": "s3://raw/run-1.json",
                "raw_sha256": "a" * 64,
                "normalized_record_ids": [123],
                "reconciliation_id": "match-1",
            }
        )
    return evidence


def test_m2_excludes_collected_even_with_recent_pipeline_evidence(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    _write_registry(
        registry,
        [
            {
                "canonical_id": "e1",
                "access_status": "collected",
                "last_success_at": datetime.now(UTC).isoformat(),
                "sla_hours": 24,
                "evidences": [_evidence()],
            }
        ],
    )
    result = compute_operational_source_coverage(
        FIXED_CANONICAL_DENOMINATOR, load_sla_config(), registry_path=registry
    )
    assert result.status == "READY"
    assert result.numerator == 0


def test_m2_requires_verified_stage_and_auditable_provenance(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    now = datetime.now(UTC).isoformat()
    _write_registry(
        registry,
        [
            {"canonical_id": "no-stage", "access_status": "verified", "last_success_at": now, "evidences": [_evidence(verified=False)]},
            {"canonical_id": "no-provenance", "access_status": "verified", "last_success_at": now, "evidences": [_evidence(provenance=False)]},
            {"canonical_id": "valid", "access_status": "verified", "last_success_at": now, "sla_hours": 24, "evidences": [_evidence()]},
        ],
    )
    result = compute_operational_source_coverage(
        FIXED_CANONICAL_DENOMINATOR, load_sla_config(), registry_path=registry
    )
    assert result.numerator == 1


def test_m2_excludes_verified_record_outside_its_sla(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    _write_registry(
        registry,
        [
            {
                "canonical_id": "stale",
                "access_status": "verified",
                "last_success_at": (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
                "sla_hours": 24,
                "evidences": [_evidence()],
            }
        ],
    )
    result = compute_operational_source_coverage(
        FIXED_CANONICAL_DENOMINATOR, load_sla_config(), registry_path=registry
    )
    assert result.numerator == 0


def test_m2_counts_distinct_canonical_entities(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    row = {
        "canonical_id": "same",
        "access_status": "verified",
        "last_success_at": datetime.now(UTC).isoformat(),
        "sla_hours": 24,
        "evidences": [_evidence()],
    }
    _write_registry(registry, [row, row])
    result = compute_operational_source_coverage(
        FIXED_CANONICAL_DENOMINATOR, load_sla_config(), registry_path=registry
    )
    assert result.numerator == 1


def test_m2_proxy_fallback_is_not_ready(tmp_path: Path) -> None:
    result = compute_operational_source_coverage(
        FIXED_CANONICAL_DENOMINATOR,
        load_sla_config(),
        registry_path=tmp_path / "missing.jsonl",
        session_dir=tmp_path,
    )
    assert result.status == "NOT_READY"
    assert result.numerator is None
