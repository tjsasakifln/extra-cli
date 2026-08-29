"""Partition status assignment. Absence of consultation is never ZERO_CONFIRMED."""

from __future__ import annotations

from scripts.national_coverage.models import (
    CLOSED_PARTITION_STATUSES,
    ConsultedPartitions,
    CoverageRequest,
    PartitionState,
    PublishingOrg,
    VersionedUniverse,
    is_national_geography,
)
from scripts.national_coverage.policy import refuse_unconsulted_as_zero


def _applicable(org: PublishingOrg, request: CoverageRequest) -> bool:
    if is_national_geography(request.geography):
        return True
    wanted = request.geography.strip().upper()
    if org.uf is None:
        return True
    return org.uf.strip().upper() == wanted


def assign_partition_statuses(
    universe: VersionedUniverse,
    consulted: ConsultedPartitions,
    request: CoverageRequest,
) -> tuple[PartitionState, ...]:
    queried = set(consulted.queried) | set(consulted.found) | set(consulted.zero_confirmed) | set(consulted.failed)
    states: list[PartitionState] = []
    for org in universe.expected_orgs:
        if not _applicable(org, request):
            states.append(
                PartitionState(
                    partition_id=org.org_id,
                    status="NOT_APPLICABLE",
                    expected=False,
                    queried=False,
                    reason="outside_requested_geography",
                    uf=org.uf,
                )
            )
            continue
        if org.org_id in consulted.failed:
            states.append(
                PartitionState(
                    partition_id=org.org_id,
                    status="FAILED",
                    expected=True,
                    queried=True,
                    evidence_ref=consulted.failed[org.org_id],
                    reason="query_failed",
                    uf=org.uf,
                )
            )
            continue
        if org.org_id in consulted.blocked:
            states.append(
                PartitionState(
                    partition_id=org.org_id,
                    status="BLOCKED",
                    expected=True,
                    queried=org.org_id in queried,
                    evidence_ref=consulted.blocked[org.org_id],
                    reason="blocked",
                    uf=org.uf,
                )
            )
            continue
        if org.org_id in consulted.zero_confirmed:
            evidence = consulted.zero_confirmed[org.org_id]
            refuse_unconsulted_as_zero("ZERO_CONFIRMED", queried=True, evidence_ref=evidence)
            states.append(
                PartitionState(
                    partition_id=org.org_id,
                    status="ZERO_CONFIRMED",
                    expected=True,
                    queried=True,
                    evidence_ref=evidence,
                    reason="zero_confirmed_with_evidence",
                    uf=org.uf,
                )
            )
            continue
        if org.org_id in consulted.found:
            states.append(
                PartitionState(
                    partition_id=org.org_id,
                    status="FOUND",
                    expected=True,
                    queried=True,
                    evidence_ref=f"observed_corpus:{org.org_id}",
                    reason="observed_in_corpus",
                    uf=org.uf,
                )
            )
            continue
        states.append(
            PartitionState(
                partition_id=org.org_id,
                status="BLOCKED",
                expected=True,
                queried=False,
                evidence_ref="not_consulted_this_run",
                reason="not_consulted_this_run",
                uf=org.uf,
            )
        )
    return tuple(states)


def count_by_status(partitions: tuple[PartitionState, ...]) -> dict[str, int]:
    counts = {
        "FOUND": 0,
        "ZERO_CONFIRMED": 0,
        "BLOCKED": 0,
        "FAILED": 0,
        "NOT_APPLICABLE": 0,
    }
    for part in partitions:
        counts[str(part.status)] = counts.get(str(part.status), 0) + 1
    return counts


def expected_queried_closed(
    partitions: tuple[PartitionState, ...],
) -> tuple[int, int, int]:
    expected = sum(1 for part in partitions if part.expected)
    queried = sum(1 for part in partitions if part.queried)
    closed = sum(1 for part in partitions if part.expected and part.status in CLOSED_PARTITION_STATUSES)
    return expected, queried, closed
