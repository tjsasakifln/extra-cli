"""Fail-closed approval gate before processing more than the pilot universe."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PILOT_LIMIT = 30
PILOT_SCHEMA = "pilot-scale-approval/v1"


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PilotGateDecision:
    required: bool
    approved: bool
    code: str
    evidence: str
    approval_path: str = ""
    approval_sha256: str = ""
    universe_sha256: str = ""
    policy_sha256: str = ""
    pilot_entities: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PilotScaleBlockedError(RuntimeError):
    """Raised before scale work when pilot approval is absent or invalid."""

    def __init__(self, decision: PilotGateDecision):
        super().__init__(f"{decision.code}: {decision.evidence}")
        self.decision = decision


def _blocked(
    *,
    code: str,
    evidence: str,
    approval_path: Path | None,
    universe_sha256: str,
    policy_sha256: str,
) -> PilotScaleBlockedError:
    return PilotScaleBlockedError(
        PilotGateDecision(
            required=True,
            approved=False,
            code=code,
            evidence=evidence,
            approval_path=str(approval_path or ""),
            approval_sha256=(
                sha256_file(approval_path) if approval_path and approval_path.is_file() else ""
            ),
            universe_sha256=universe_sha256,
            policy_sha256=policy_sha256,
        )
    )


def require_pilot_approval(
    *,
    universe_path: Path,
    policy_path: Path,
    universe_entity_count: int,
    universe_entity_ids: set[str],
    approval_path: Path | None,
    scale_limit: int = PILOT_LIMIT,
) -> PilotGateDecision:
    """Validate a human-approved pilot before any scale processing starts."""
    missing_inputs = [
        f"{label} file missing: {path}"
        for label, path in (("universe", universe_path), ("policy", policy_path))
        if not path.is_file()
    ]
    if missing_inputs:
        raise PilotScaleBlockedError(
            PilotGateDecision(
                required=universe_entity_count > scale_limit,
                approved=False,
                code="PILOT_INPUT_MISSING",
                evidence="; ".join(missing_inputs),
                approval_path=str(approval_path or ""),
            )
        )
    universe_sha256 = sha256_file(universe_path)
    policy_sha256 = sha256_file(policy_path)
    if universe_entity_count <= scale_limit:
        return PilotGateDecision(
            required=False,
            approved=True,
            code="PILOT_NOT_REQUIRED",
            evidence=f"universe_entities={universe_entity_count} <= {scale_limit}",
            universe_sha256=universe_sha256,
            policy_sha256=policy_sha256,
        )
    if approval_path is None or not approval_path.is_file():
        raise _blocked(
            code="PILOT_APPROVAL_MISSING",
            evidence=f"universe_entities={universe_entity_count} > {scale_limit}",
            approval_path=approval_path,
            universe_sha256=universe_sha256,
            policy_sha256=policy_sha256,
        )

    try:
        artifact = json.loads(approval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _blocked(
            code="PILOT_APPROVAL_INVALID",
            evidence=f"approval artifact is not valid JSON: {exc}",
            approval_path=approval_path,
            universe_sha256=universe_sha256,
            policy_sha256=policy_sha256,
        ) from exc

    errors: list[str] = []
    if artifact.get("schema_version") != PILOT_SCHEMA:
        errors.append(f"schema_version must be {PILOT_SCHEMA}")
    if artifact.get("universe_sha256") != universe_sha256:
        errors.append("universe_sha256 mismatch")
    if artifact.get("policy_sha256") != policy_sha256:
        errors.append("policy_sha256 mismatch")

    entities = artifact.get("entities")
    if not isinstance(entities, list) or len(entities) != scale_limit:
        errors.append(f"entities must contain exactly {scale_limit} rows")
        entities = []
    entity_ids = [str(row.get("entity_id") or "") for row in entities if isinstance(row, dict)]
    if len(entity_ids) != len(set(entity_ids)) or any(not value for value in entity_ids):
        errors.append("entity_id values must be non-empty and unique")
    unknown = sorted(set(entity_ids) - universe_entity_ids)
    if unknown:
        errors.append(f"entities outside approved universe: {unknown[:3]}")

    declared_sources_raw = artifact.get("sources")
    declared_sources: list[str] = []
    if not isinstance(declared_sources_raw, list):
        errors.append("sources must be a list")
    else:
        for source_index, source_value in enumerate(declared_sources_raw):
            if not isinstance(source_value, str) or not source_value.strip():
                errors.append(f"sources[{source_index}] must be a non-empty string")
                continue
            declared_sources.append(source_value.strip())
        if len(declared_sources) < 2:
            errors.append("sources must declare at least two sources")
        if len(declared_sources) != len(set(declared_sources)):
            errors.append("sources must be unique")
    declared_source_set = set(declared_sources)

    strata: set[str] = set()
    for row_index, row in enumerate(entities):
        if not isinstance(row, dict):
            errors.append(f"entities[{row_index}] must be an object")
            continue
        stratum = str(row.get("stratum") or "").strip()
        if not stratum:
            errors.append(f"entities[{row_index}].stratum is required")
        else:
            strata.add(stratum)
        source_results = row.get("source_results")
        if not isinstance(source_results, list) or not source_results:
            errors.append(f"entities[{row_index}].source_results is required")
            continue
        entity_sources = [
            str(result.get("source") or "").strip()
            for result in source_results
            if isinstance(result, dict)
        ]
        source_counts = Counter(entity_sources)
        missing_sources = sorted(declared_source_set - set(entity_sources))
        extra_sources = sorted(set(entity_sources) - declared_source_set - {""})
        duplicate_sources = sorted(
            source for source, count in source_counts.items() if source and count != 1
        )
        if missing_sources:
            errors.append(
                f"entities[{row_index}].source_results missing declared sources: "
                f"{missing_sources}"
            )
        if extra_sources:
            errors.append(
                f"entities[{row_index}].source_results has undeclared sources: "
                f"{extra_sources}"
            )
        if duplicate_sources:
            errors.append(
                f"entities[{row_index}].source_results has duplicate sources: "
                f"{duplicate_sources}"
            )
        if len(source_results) != len(declared_sources):
            errors.append(
                f"entities[{row_index}].source_results must contain exactly one result "
                "for each declared source"
            )
        for source_index, result in enumerate(source_results):
            prefix = f"entities[{row_index}].source_results[{source_index}]"
            if not isinstance(result, dict):
                errors.append(f"{prefix} must be an object")
                continue
            source = str(result.get("source") or "").strip()
            if not source:
                errors.append(f"{prefix}.source is required")
            if result.get("request_completed") is not True or result.get("scope_complete") is not True:
                errors.append(f"{prefix} must prove request_completed and scope_complete")
            pagination = result.get("pagination")
            if not isinstance(pagination, dict):
                errors.append(f"{prefix}.pagination must be an object")
                pagination = {}
            fetched = pagination.get("pages_fetched")
            expected = pagination.get("pages_expected")
            if (
                pagination.get("complete") is not True
                or not _is_non_negative_int(fetched)
                or not _is_non_negative_int(expected)
                or fetched != expected
            ):
                errors.append(f"{prefix}.pagination is incomplete")
            records = result.get("records")
            zero_proof = result.get("zero_proof")
            if not _is_non_negative_int(records):
                errors.append(f"{prefix}.records must be a non-negative integer")
            elif zero_proof != ("success_zero" if records == 0 else "not_zero"):
                errors.append(f"{prefix}.zero_proof does not match records")
            if fetched == 0 and expected == 0 and records != 0:
                errors.append(f"{prefix}.zero-page pagination requires zero records")
            dedup = result.get("deduplication")
            if not isinstance(dedup, dict):
                errors.append(f"{prefix}.deduplication must be an object")
                dedup = {}
            before = dedup.get("input_records")
            after = dedup.get("output_records")
            removed = dedup.get("duplicates_removed")
            if (
                dedup.get("complete") is not True
                or not all(_is_non_negative_int(value) for value in (before, after, removed))
                or before - after != removed
                or after != records
            ):
                errors.append(f"{prefix}.deduplication is invalid")
            evidence_ref = str(result.get("evidence_path") or "")
            evidence_hash = str(result.get("evidence_sha256") or "")
            evidence_candidate = Path(evidence_ref)
            evidence_root = approval_path.parent.resolve()
            if evidence_candidate.is_absolute():
                errors.append(f"{prefix}.evidence_path must be relative to approval directory")
                continue
            evidence_path = (evidence_root / evidence_candidate).resolve()
            if not evidence_path.is_relative_to(evidence_root):
                errors.append(f"{prefix}.evidence_path must stay inside approval directory")
            elif not evidence_path.is_file():
                errors.append(f"{prefix}.evidence_path is missing")
            elif len(evidence_hash) != 64 or sha256_file(evidence_path) != evidence_hash:
                errors.append(f"{prefix}.evidence_sha256 mismatch")

    if len(strata) < 2:
        errors.append("pilot must include at least two strata")
    approval = artifact.get("human_approval") or {}
    if (
        approval.get("status") != "APPROVED"
        or not str(approval.get("approved_by") or "").strip()
        or not str(approval.get("approved_at") or "").strip()
    ):
        errors.append("human_approval must be APPROVED with approved_by and approved_at")

    if errors:
        code = (
            "PILOT_APPROVAL_HASH_MISMATCH"
            if any("sha256" in error for error in errors)
            else "PILOT_APPROVAL_INVALID"
        )
        raise _blocked(
            code=code,
            evidence="; ".join(errors[:8]),
            approval_path=approval_path,
            universe_sha256=universe_sha256,
            policy_sha256=policy_sha256,
        )

    return PilotGateDecision(
        required=True,
        approved=True,
        code="PILOT_APPROVED",
        evidence=(
            f"validated {scale_limit} entities across {len(strata)} strata and "
            f"{len(declared_source_set)} sources"
        ),
        approval_path=str(approval_path),
        approval_sha256=sha256_file(approval_path),
        universe_sha256=universe_sha256,
        policy_sha256=policy_sha256,
        pilot_entities=scale_limit,
    )
