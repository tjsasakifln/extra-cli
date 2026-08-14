"""#307 — apply contract rectifications with immutable bitemporal history.

Identical payload updates last_seen only. A newer upstream payload creates
a new immutable version and moves the current pointer. A late older payload
never overwrites a newer version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

MATERIAL_FIELDS: tuple[str, ...] = (
    "valor",
    "objeto",
    "fornecedor",
    "vigencia_inicio",
    "vigencia_fim",
    "data_assinatura",
    "status",
)

CorrectionAction = Literal["CREATE", "TOUCH_LAST_SEEN", "NEW_VERSION", "REJECT_STALE"]


@dataclass(frozen=True)
class ContractVersion:
    version: int
    material_hash: str
    valid_from_source: datetime
    valid_to: datetime | None
    observed_at: datetime
    raw_hash: str
    run_id: str
    attempt_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class IncomingCorrection:
    payload: dict[str, Any]
    source_updated_at: datetime
    observed_at: datetime
    raw_hash: str
    run_id: str
    attempt_id: str


@dataclass(frozen=True)
class CorrectionDecision:
    action: CorrectionAction
    current_version: int | None
    next_version: int | None
    reason: str
    material_hash: str


def material_hash(payload: dict[str, Any]) -> str:
    """Canonical hash of the material contract fields only."""
    material = {field: payload.get(field) for field in MATERIAL_FIELDS}
    encoded = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def next_version_number(existing: list[ContractVersion]) -> int:
    """Deterministic next version; never reuses a number under concurrency."""
    if not existing:
        return 1
    return max(item.version for item in existing) + 1


def decide_correction(
    current: ContractVersion | None,
    incoming: IncomingCorrection,
    *,
    existing: list[ContractVersion] | None = None,
) -> CorrectionDecision:
    incoming_hash = material_hash(incoming.payload)
    if current is None:
        return CorrectionDecision(
            action="CREATE",
            current_version=None,
            next_version=next_version_number(existing or []),
            reason="first_observation",
            material_hash=incoming_hash,
        )
    if incoming_hash == current.material_hash:
        return CorrectionDecision(
            action="TOUCH_LAST_SEEN",
            current_version=current.version,
            next_version=None,
            reason="identical_material_payload",
            material_hash=incoming_hash,
        )
    if incoming.source_updated_at < current.valid_from_source:
        return CorrectionDecision(
            action="REJECT_STALE",
            current_version=current.version,
            next_version=None,
            reason="late_older_payload",
            material_hash=incoming_hash,
        )
    versions = list(existing or [current])
    return CorrectionDecision(
        action="NEW_VERSION",
        current_version=current.version,
        next_version=next_version_number(versions),
        reason="material_rectification",
        material_hash=incoming_hash,
    )


def apply_correction(
    versions: list[ContractVersion],
    incoming: IncomingCorrection,
) -> tuple[list[ContractVersion], CorrectionDecision]:
    """Return a new version list. Never mutates the previous version payload."""
    current = max(versions, key=lambda item: item.version) if versions else None
    decision = decide_correction(current, incoming, existing=versions)
    if decision.action in ("TOUCH_LAST_SEEN", "REJECT_STALE"):
        return list(versions), decision
    created = ContractVersion(
        version=decision.next_version or 1,
        material_hash=decision.material_hash,
        valid_from_source=incoming.source_updated_at,
        valid_to=None,
        observed_at=incoming.observed_at,
        raw_hash=incoming.raw_hash,
        run_id=incoming.run_id,
        attempt_id=incoming.attempt_id,
        payload=dict(incoming.payload),
    )
    closed: list[ContractVersion] = []
    for item in versions:
        if item.version == (current.version if current else None) and item.valid_to is None:
            closed.append(
                ContractVersion(
                    version=item.version,
                    material_hash=item.material_hash,
                    valid_from_source=item.valid_from_source,
                    valid_to=incoming.observed_at,
                    observed_at=item.observed_at,
                    raw_hash=item.raw_hash,
                    run_id=item.run_id,
                    attempt_id=item.attempt_id,
                    payload=dict(item.payload),
                )
            )
        else:
            closed.append(item)
    return [*closed, created], decision


def snapshot_as_of(versions: list[ContractVersion], as_of: datetime) -> ContractVersion | None:
    """Replay the current pointer as of an observation instant."""
    visible = [
        item for item in versions if item.observed_at <= as_of and (item.valid_to is None or item.valid_to > as_of)
    ]
    if not visible:
        return None
    return max(visible, key=lambda item: item.version)
