"""Evidence provenance helpers — honest absence vs non-inference."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DOCUMENT_NOT_AVAILABLE_IN_SOURCE = "DOCUMENT_NOT_AVAILABLE_IN_SOURCE"
# Explicitly NOT inferred:
AGENCY_DID_NOT_CREATE_DOCUMENT = "AGENCY_DID_NOT_CREATE_DOCUMENT"

FORBIDDEN_ABSENCE_INFERENCES = (
    AGENCY_DID_NOT_CREATE_DOCUMENT,
    "ORGAO_NAO_PRODUZIU_DOCUMENTO",
    "DOCUMENTO_INEXISTENTE_NO_PROCESSO",
)


@dataclass
class EvidenceRecord:
    source: str
    identifier: str | None
    url_or_ref: str | None
    publication_date: str | None
    capture_date: str | None
    content_hash: str | None
    parser: str
    version: str
    quality: str
    limitations: list[str] = field(default_factory=list)
    availability: str = "AVAILABLE"  # AVAILABLE | DOCUMENT_NOT_AVAILABLE_IN_SOURCE
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_document_lookup(
    *,
    source: str,
    identifier: str | None,
    url_or_ref: str | None,
    found: bool,
    publication_date: str | None = None,
    capture_date: str | None = None,
    content_hash: str | None = None,
    parser: str = "public_agency.evidence",
    version: str = "1.0.0",
    extra_limitations: list[str] | None = None,
) -> EvidenceRecord:
    """Record a document lookup without inventing process-level absence."""
    if found:
        return EvidenceRecord(
            source=source,
            identifier=identifier,
            url_or_ref=url_or_ref,
            publication_date=publication_date,
            capture_date=capture_date,
            content_hash=content_hash,
            parser=parser,
            version=version,
            quality="official_or_dataset_row",
            limitations=list(extra_limitations or []),
            availability="AVAILABLE",
        )
    return EvidenceRecord(
        source=source,
        identifier=identifier,
        url_or_ref=url_or_ref,
        publication_date=publication_date,
        capture_date=capture_date,
        content_hash=content_hash,
        parser=parser,
        version=version,
        quality="lookup_miss",
        limitations=[
            DOCUMENT_NOT_AVAILABLE_IN_SOURCE,
            "Absence in this source/dataset does not prove the Administration never created the document.",
            *(extra_limitations or []),
        ],
        availability=DOCUMENT_NOT_AVAILABLE_IN_SOURCE,
        notes=(
            f"Recorded as {DOCUMENT_NOT_AVAILABLE_IN_SOURCE}. "
            "Must not be rewritten as a claim that the agency never created the document "
            "in the administrative process."
        ),
    )


def assert_no_forbidden_absence_inference(text: str) -> None:
    upper = text.upper()
    for forbidden in FORBIDDEN_ABSENCE_INFERENCES:
        if forbidden.upper() in upper and DOCUMENT_NOT_AVAILABLE_IN_SOURCE not in text:
            # Allow mention only when explaining the distinction
            raise ValueError(f"forbidden absence inference present: {forbidden}")


def may_infer_agency_did_not_create(record: EvidenceRecord) -> bool:
    """Always False from source miss alone — process file not fully observed."""
    if record.availability == DOCUMENT_NOT_AVAILABLE_IN_SOURCE:
        return False
    return False
