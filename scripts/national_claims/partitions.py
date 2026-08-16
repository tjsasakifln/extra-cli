"""Partition reconciliation for the national-claims arbiter.

Absence of execution is UNKNOWN, never zero. ZERO_CONFIRMED is legal only
when the request and pagination are complete and an evidence ref exists.
Legacy live_universe labels of BLOCKED/not_consulted are remapped to
UNKNOWN so they cannot close a count.
"""

from __future__ import annotations

from scripts.national_claims.models import (
    CLOSED_PARTITION_STATUSES,
    PartitionReconciliation,
    PartitionRecord,
    PartitionStatus,
    VersionedUniverse,
)

LEGAL_STATUSES: frozenset[str] = frozenset(
    {"FOUND", "ZERO_CONFIRMED", "BLOCKED", "FAILED", "NOT_APPLICABLE", "UNKNOWN"}
)
LEGACY_NOT_CONSULTED_MARKERS = frozenset(
    {
        "not_consulted",
        "not_consulted_this_run",
        "unconsulted",
        "never_checked",
        "absent_execution",
    }
)


class PartitionReconciliationError(ValueError):
    """Partition set cannot be closed honestly."""


def _legacy_unconsulted(record: PartitionRecord) -> bool:
    reason = (record.reason or "").strip().lower()
    evidence = (record.evidence_ref or "").strip().lower()
    return reason in LEGACY_NOT_CONSULTED_MARKERS or evidence in LEGACY_NOT_CONSULTED_MARKERS


def normalize_partition(record: PartitionRecord) -> PartitionRecord:
    """Force honest status. Do not mutate the caller's object."""
    if not record.attempted or _legacy_unconsulted(record):
        return PartitionRecord(
            partition_id=record.partition_id,
            expected=record.expected,
            attempted=False,
            status="UNKNOWN",
            pages_fetched=record.pages_fetched,
            pages_expected=record.pages_expected,
            records=None if not record.attempted else record.records,
            pagination_complete=False,
            request_complete=False,
            raw_ref=record.raw_ref,
            evidence_ref=record.evidence_ref,
            checked_at=record.checked_at,
            as_of=record.as_of,
            freshness_status=record.freshness_status,
            identity_mapped=record.identity_mapped,
            reason=record.reason or "execution_absent",
            next_action=record.next_action or "consult_partition",
        )
    if record.status == "ZERO_CONFIRMED":
        proof_ok = record.request_complete and record.pagination_complete and bool(record.evidence_ref)
        if not proof_ok:
            return PartitionRecord(
                partition_id=record.partition_id,
                expected=record.expected,
                attempted=True,
                status="UNKNOWN",
                pages_fetched=record.pages_fetched,
                pages_expected=record.pages_expected,
                records=record.records,
                pagination_complete=record.pagination_complete,
                request_complete=record.request_complete,
                raw_ref=record.raw_ref,
                evidence_ref=record.evidence_ref,
                checked_at=record.checked_at,
                as_of=record.as_of,
                freshness_status=record.freshness_status,
                identity_mapped=record.identity_mapped,
                reason="zero_without_pagination_proof",
                next_action="complete_request_and_pagination",
            )
    if record.status == "FOUND" and not record.evidence_ref:
        return PartitionRecord(
            partition_id=record.partition_id,
            expected=record.expected,
            attempted=True,
            status="UNKNOWN",
            pages_fetched=record.pages_fetched,
            pages_expected=record.pages_expected,
            records=record.records,
            pagination_complete=record.pagination_complete,
            request_complete=record.request_complete,
            raw_ref=record.raw_ref,
            evidence_ref=record.evidence_ref,
            checked_at=record.checked_at,
            as_of=record.as_of,
            freshness_status=record.freshness_status,
            identity_mapped=record.identity_mapped,
            reason="found_without_evidence_ref",
            next_action="attach_raw_or_evidence_ref",
        )
    if record.status not in LEGAL_STATUSES:
        return PartitionRecord(
            partition_id=record.partition_id,
            expected=record.expected,
            attempted=record.attempted,
            status="UNKNOWN",
            pages_fetched=record.pages_fetched,
            pages_expected=record.pages_expected,
            records=record.records,
            pagination_complete=record.pagination_complete,
            request_complete=record.request_complete,
            raw_ref=record.raw_ref,
            evidence_ref=record.evidence_ref,
            checked_at=record.checked_at,
            as_of=record.as_of,
            freshness_status=record.freshness_status,
            identity_mapped=record.identity_mapped,
            reason=f"illegal_status:{record.status}",
            next_action="reclassify_partition_status",
        )
    return record


def reconcile_claim_partitions(
    universe: VersionedUniverse,
    records: tuple[PartitionRecord, ...],
    *,
    scoped_ids: frozenset[str] | None = None,
) -> PartitionReconciliation:
    """Close expected vs attempted vs closed. Counts never invent zeros."""
    expected_ids = {org.org_id for org in universe.expected_orgs}
    if scoped_ids is not None:
        expected_ids = expected_ids & set(scoped_ids)
    normalized = tuple(normalize_partition(item) for item in records)
    by_id = {item.partition_id: item for item in normalized}
    blockers: list[str] = []
    next_actions: list[str] = []
    missing = sorted(expected_ids - set(by_id))
    for partition_id in missing:
        blockers.append(f"missing_partition:{partition_id}")
        next_actions.append(f"consult:{partition_id}")
    unexpected = sorted(set(by_id) - {org.org_id for org in universe.expected_orgs})
    for partition_id in unexpected:
        blockers.append(f"unexpected_partition:{partition_id}")

    material = []
    for partition_id in sorted(expected_ids):
        if partition_id not in by_id:
            material.append(
                PartitionRecord(
                    partition_id=partition_id,
                    expected=True,
                    attempted=False,
                    status="UNKNOWN",
                    reason="execution_absent",
                    next_action=f"consult:{partition_id}",
                )
            )
            continue
        material.append(by_id[partition_id])

    by_status = {status: 0 for status in sorted(LEGAL_STATUSES)}
    attempted = 0
    closed = 0
    for record in material:
        status: PartitionStatus = record.status
        by_status[status] += 1
        if record.attempted:
            attempted += 1
        if status in CLOSED_PARTITION_STATUSES:
            closed += 1
        if record.next_action:
            next_actions.append(record.next_action)
        if status == "UNKNOWN" and record.expected:
            blockers.append(f"unknown_partition:{record.partition_id}")
        if status == "BLOCKED":
            blockers.append(f"blocked_partition:{record.partition_id}")
        if status == "FAILED":
            blockers.append(f"failed_partition:{record.partition_id}")

    return PartitionReconciliation(
        expected=len(expected_ids),
        attempted=attempted,
        closed=closed,
        by_status=by_status,
        records=tuple(material),
        blockers=tuple(blockers),
        next_actions=tuple(dict.fromkeys(next_actions)),
    )


def counts_close(reconciliation: PartitionReconciliation) -> bool:
    counted = sum(reconciliation.by_status.values())
    return (
        counted == reconciliation.expected
        and reconciliation.attempted <= reconciliation.expected
        and reconciliation.closed <= reconciliation.attempted
    )
