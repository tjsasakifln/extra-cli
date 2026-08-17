"""Append-only reconciliation. Conflicts are grouped, never silently resolved."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace

from scripts.official_contract_semantics.constants import RECONCILE_VERSION
from scripts.official_contract_semantics.identity import refuse_root_establishment_merge
from scripts.official_contract_semantics.models import OfficialContractObservation
from scripts.official_contract_semantics.serialize import content_hash

CONFLICT_DIMENSIONS = (
    "unit",
    "quantity",
    "execution_regime",
    "procurement_modality",
    "value_amount",
    "value_semantic",
    "period_start",
    "period_end",
    "supplier_identifier",
    "amendment_type",
    "amendment_value_delta",
    "amendment_term_delta",
)


def _subject_key(item: OfficialContractObservation) -> str:
    return item.contract_identifier or item.process_identifier or item.source_document_id or item.observation_id


def _value_tuple(item: OfficialContractObservation) -> tuple[object, ...]:
    return tuple(getattr(item, name) for name in CONFLICT_DIMENSIONS)


def conflict_group_id_for(subject: str, left: OfficialContractObservation, right: OfficialContractObservation) -> str:
    return content_hash(
        {
            "reconcile_version": RECONCILE_VERSION,
            "subject": subject,
            "dimensions": CONFLICT_DIMENSIONS,
            "members": sorted((left.observation_id, right.observation_id)),
        }
    )


def _explicit_supersession(newer: OfficialContractObservation, older: OfficialContractObservation) -> bool:
    if newer.supersedes_observation_id and newer.supersedes_observation_id == older.observation_id:
        return True
    if (
        newer.supersedes_document_id
        and older.source_document_id
        and newer.supersedes_document_id == older.source_document_id
    ):
        return True
    if (
        newer.supersedes_document_id
        and older.source_document_sha256
        and newer.supersedes_document_id == older.source_document_sha256
    ):
        return True
    return False


def _cnpj_conflict(left: OfficialContractObservation, right: OfficialContractObservation) -> bool:
    if not left.supplier_identifier or not right.supplier_identifier:
        return False
    if left.supplier_identifier == right.supplier_identifier:
        return False
    if refuse_root_establishment_merge(left.supplier_identifier, right.supplier_identifier):
        return True
    return True


def _semantic_conflict(left: OfficialContractObservation, right: OfficialContractObservation) -> bool:
    if _cnpj_conflict(left, right):
        return True
    comparable = False
    differed = False
    for name in CONFLICT_DIMENSIONS:
        a = getattr(left, name)
        b = getattr(right, name)
        if a is None or b is None:
            continue
        comparable = True
        if a != b:
            if name == "value_semantic":
                continue
            if name == "value_amount" and left.value_semantic != right.value_semantic:
                continue
            differed = True
    return comparable and differed


def reconcile(
    observations: Iterable[OfficialContractObservation],
) -> tuple[OfficialContractObservation, ...]:
    material = list(observations)
    by_id: dict[str, OfficialContractObservation] = {}
    for item in material:
        previous = by_id.get(item.observation_id)
        if previous is None:
            by_id[item.observation_id] = item
            continue
        # Same id + same content: idempotent skip. Different document hash cannot share id.
        by_id[item.observation_id] = previous

    current = list(by_id.values())
    grouped: dict[str, list[OfficialContractObservation]] = defaultdict(list)
    for item in current:
        grouped[_subject_key(item)].append(item)

    superseded: set[str] = set()
    successors: dict[str, str] = {}
    for subject, members in grouped.items():
        for newer in members:
            for older in members:
                if newer.observation_id == older.observation_id:
                    continue
                if _explicit_supersession(newer, older):
                    superseded.add(older.observation_id)
                    successors[older.observation_id] = newer.observation_id

    conflict_ids: dict[str, str] = {}
    for subject, members in grouped.items():
        live = [item for item in members if item.observation_id not in superseded]
        for index, left in enumerate(live):
            for right in live[index + 1 :]:
                if not _semantic_conflict(left, right):
                    continue
                group_id = conflict_group_id_for(subject, left, right)
                conflict_ids[left.observation_id] = group_id
                conflict_ids[right.observation_id] = group_id

    updated: list[OfficialContractObservation] = []
    for item in current:
        status = item.status
        conflict_group_id = item.conflict_group_id
        extra = dict(item.extra)
        extra["reconcile_version"] = RECONCILE_VERSION
        if item.observation_id in superseded:
            status = "superseded_by_official_evidence"
            extra["superseded_by_observation_id"] = successors.get(item.observation_id)
        elif item.observation_id in conflict_ids:
            status = "conflicted"
            conflict_group_id = conflict_ids[item.observation_id]
        updated.append(replace(item, status=status, conflict_group_id=conflict_group_id, extra=extra))
    return tuple(sorted(updated, key=lambda item: (item.observation_id, item.source_document_sha256 or "")))
