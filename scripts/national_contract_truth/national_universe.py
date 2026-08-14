"""#302 — versioned national denominator of publishing orgs/units.

Separated from Extra's commercial 1.093-entity universe. "Nacional completo"
is emitted only when every partition of the denominator closes with evidence.
Replaying the same raws/hashes reproduces the catalog and reconciliation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

SCHEMA_VERSION = "national-universe/1.0"
EXTRA_COMMERCIAL_DENOMINATOR = 1093

PartitionStatus = Literal["FOUND", "ZERO_CONFIRMED", "BLOCKED", "FAILED"]


class NationalUniverseError(ValueError):
    """National completeness cannot be claimed."""


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class PublishingOrg:
    org_id: str
    source: str
    competence: str
    name: str
    unit_count: int = 1


@dataclass(frozen=True)
class NationalUniverse:
    national_universe_id: str
    source: str
    competence: str
    cutoff: str
    orgs: tuple[PublishingOrg, ...]
    method: str

    @property
    def org_count(self) -> int:
        return len(self.orgs)

    @property
    def unit_count(self) -> int:
        return sum(o.unit_count for o in self.orgs)

    @property
    def catalog_hash(self) -> str:
        return sha256_payload(
            {
                "national_universe_id": self.national_universe_id,
                "source": self.source,
                "competence": self.competence,
                "cutoff": self.cutoff,
                "orgs": [asdict(o) for o in self.orgs],
                "method": self.method,
            }
        )


@dataclass(frozen=True)
class PartitionResult:
    partition_id: str
    status: PartitionStatus
    expected: bool = True
    evidence: str | None = None


def build_universe(
    *,
    source: str,
    competence: str,
    cutoff: str,
    orgs: tuple[PublishingOrg, ...],
    method: str,
) -> NationalUniverse:
    if not source or not competence or not cutoff:
        raise NationalUniverseError("source, competence and cutoff are required")
    if not orgs:
        raise NationalUniverseError("denominator has zero publishing orgs")
    if any(o.unit_count < 1 for o in orgs):
        raise NationalUniverseError("unit_count must be >= 1")
    uid = sha256_payload(
        {"source": source, "competence": competence, "cutoff": cutoff, "method": method}
    )[:16]
    return NationalUniverse(
        national_universe_id=f"nu-{source}-{competence}-{uid}",
        source=source,
        competence=competence,
        cutoff=cutoff,
        orgs=orgs,
        method=method,
    )


def reconcile_partitions(
    universe: NationalUniverse,
    results: tuple[PartitionResult, ...],
) -> dict[str, Any]:
    expected_ids = {o.org_id for o in universe.orgs}
    seen = {r.partition_id for r in results}
    blockers: list[str] = []
    if expected_ids != seen:
        blockers.append(f"partition_set_mismatch:expected={sorted(expected_ids)} got={sorted(seen)}")
    by_status = {status: 0 for status in ("FOUND", "ZERO_CONFIRMED", "BLOCKED", "FAILED")}
    for result in results:
        if result.status not in by_status:
            blockers.append(f"illegal_status:{result.status}")
            continue
        if result.status in {"FOUND", "ZERO_CONFIRMED"} and not result.evidence:
            blockers.append(f"missing_evidence:{result.partition_id}")
        by_status[result.status] += 1
    closed = (
        not blockers
        and by_status["BLOCKED"] == 0
        and by_status["FAILED"] == 0
        and by_status["FOUND"] + by_status["ZERO_CONFIRMED"] == universe.org_count
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "national_universe_id": universe.national_universe_id,
        "source": universe.source,
        "competence": universe.competence,
        "cutoff": universe.cutoff,
        "catalog_hash": universe.catalog_hash,
        "org_count": universe.org_count,
        "unit_count": universe.unit_count,
        "method": universe.method,
        "expected_partitions": universe.org_count,
        "consulted_partitions": len(results),
        "by_status": by_status,
        "nacional_completo": closed,
        "extra_1093_used_as_denominator": False,
        "extra_commercial_denominator": EXTRA_COMMERCIAL_DENOMINATOR,
        "blockers": blockers,
    }
    payload["reconciliation_hash"] = sha256_payload(payload)
    if blockers:
        raise NationalUniverseError(";".join(blockers))
    return payload
