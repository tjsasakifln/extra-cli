"""#345 — client-independent versioned Tender Dossier.

COMPLETE requires locatable claims and every required document.
Missing evidence is BLOCKED. A client-profile change never opens a revision
and never schedules HTTP/OCR.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

DossierState = Literal["BUILDING", "COMPLETE", "BLOCKED", "SUPERSEDED"]
CLIENT_COLUMN_MARKERS: tuple[str, ...] = (
    "score",
    "go_no_go",
    "client_id",
    "capacidade",
    "preferencia",
)


@dataclass(frozen=True)
class DossierClaim:
    claim_id: str
    value: Any
    source: str
    document_hash: str
    locator: str | None
    extractor_version: str
    policy_version: str
    evidence_state: str


@dataclass(frozen=True)
class DossierInputs:
    tender_id: str
    snapshot_id: str
    schema_version: str
    policy_version: str
    extractor_version: str
    document_hashes: tuple[str, ...]
    required_document_hashes: tuple[str, ...]
    claims: tuple[DossierClaim, ...]
    client_profile_hash: str | None = None


@dataclass(frozen=True)
class TenderDossier:
    tender_id: str
    dossier_version: int
    snapshot_id: str
    state: DossierState
    reason_code: str | None
    input_hash: str
    claims: tuple[DossierClaim, ...]
    next_action: str | None


def inputs_hash(inputs: DossierInputs) -> str:
    payload = {
        "tender_id": inputs.tender_id,
        "snapshot_id": inputs.snapshot_id,
        "schema_version": inputs.schema_version,
        "policy_version": inputs.policy_version,
        "extractor_version": inputs.extractor_version,
        "document_hashes": list(inputs.document_hashes),
        "required_document_hashes": list(inputs.required_document_hashes),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "value": claim.value,
                "source": claim.source,
                "document_hash": claim.document_hash,
                "locator": claim.locator,
                "extractor_version": claim.extractor_version,
                "policy_version": claim.policy_version,
                "evidence_state": claim.evidence_state,
            }
            for claim in inputs.claims
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def contains_client_column(payload: dict[str, Any]) -> bool:
    lowered = {str(key).casefold() for key in payload}
    return any(marker in lowered for marker in CLIENT_COLUMN_MARKERS)


def build_dossier(inputs: DossierInputs, *, previous: TenderDossier | None = None) -> TenderDossier:
    digest = inputs_hash(inputs)
    if previous is not None and previous.input_hash == digest:
        return previous

    missing = [doc for doc in inputs.required_document_hashes if doc not in inputs.document_hashes]
    if missing:
        return TenderDossier(
            tender_id=inputs.tender_id,
            dossier_version=(previous.dossier_version + 1) if previous else 1,
            snapshot_id=inputs.snapshot_id,
            state="BLOCKED",
            reason_code="MISSING_REQUIRED_DOCUMENT",
            input_hash=digest,
            claims=inputs.claims,
            next_action="fetch_required_document",
        )
    unlocated = [claim.claim_id for claim in inputs.claims if not claim.locator]
    if unlocated:
        return TenderDossier(
            tender_id=inputs.tender_id,
            dossier_version=(previous.dossier_version + 1) if previous else 1,
            snapshot_id=inputs.snapshot_id,
            state="BLOCKED",
            reason_code="CLAIM_WITHOUT_LOCATOR",
            input_hash=digest,
            claims=inputs.claims,
            next_action="locate_claim",
        )
    unobserved = [
        claim.claim_id
        for claim in inputs.claims
        if str(claim.evidence_state or "").casefold() not in {"observed", "verified"}
    ]
    if unobserved:
        return TenderDossier(
            tender_id=inputs.tender_id,
            dossier_version=(previous.dossier_version + 1) if previous else 1,
            snapshot_id=inputs.snapshot_id,
            state="BLOCKED",
            reason_code="CLAIM_WITHOUT_EVIDENCE",
            input_hash=digest,
            claims=inputs.claims,
            next_action="observe_claim_evidence",
        )
    version = 1
    if previous is not None:
        superseded_state: DossierState = "SUPERSEDED"
        version = previous.dossier_version + 1
        del superseded_state
    return TenderDossier(
        tender_id=inputs.tender_id,
        dossier_version=version,
        snapshot_id=inputs.snapshot_id,
        state="COMPLETE",
        reason_code=None,
        input_hash=digest,
        claims=inputs.claims,
        next_action=None,
    )


def client_profile_change_schedules_work(previous: TenderDossier, new_profile_hash: str) -> bool:
    """Changing only the client profile must not create a revision or schedule I/O."""
    del new_profile_hash
    return False


def same_inputs_same_hash(left: DossierInputs, right: DossierInputs) -> bool:
    return inputs_hash(left) == inputs_hash(right)
