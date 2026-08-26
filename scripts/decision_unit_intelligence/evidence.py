"""Field-level evidence helpers. Evidence is immutable once built."""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import re
import zlib
from typing import Any

from scripts.decision_unit_intelligence.models import (
    EpistemicClass,
    FieldAspect,
    FieldEvidence,
    now_iso,
    stable_id,
)

PAGE_DOCUMENT_WITNESS_SCHEMA = "dui.page_document_witness.v1"
MAX_PAGE_DOCUMENT_WITNESS_BYTES = 2_500_000
MAX_PAGE_DOCUMENT_WITNESS_COMPRESSED_BYTES = 1_000_000
MAX_PAGE_DOCUMENT_WITNESS_BASE64_CHARS = 4 * (
    (MAX_PAGE_DOCUMENT_WITNESS_COMPRESSED_BYTES + 2) // 3
)


def make_page_document_witness(content: str) -> dict[str, Any] | None:
    """Return bounded, replay-verifiable source bytes for a page attestation.

    Hash-only metadata is self-certifying.  The compressed witness lets every
    later publication gate recompute the digest from the exact UTF-8 bytes the
    extractor hashed. Pages outside the crawler's bounded evidence budget are
    retained as observations but cannot mint an account/mailbox attestation.
    """

    raw = str(content or "").encode("utf-8")
    if not raw or len(raw) > MAX_PAGE_DOCUMENT_WITNESS_BYTES:
        return None
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(compressed) > MAX_PAGE_DOCUMENT_WITNESS_COMPRESSED_BYTES:
        return None
    return {
        "schema": PAGE_DOCUMENT_WITNESS_SCHEMA,
        "encoding": "gzip+base64+utf8",
        "raw_size_bytes": len(raw),
        "compressed_size_bytes": len(compressed),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "content_gzip_b64": base64.b64encode(compressed).decode("ascii"),
    }


def verified_page_document_bytes(
    witness: Any,
    *,
    expected_sha256: str,
) -> bytes | None:
    """Decode a bounded witness and return bytes only when its digest matches."""

    if not isinstance(witness, dict):
        return None
    if witness.get("schema") != PAGE_DOCUMENT_WITNESS_SCHEMA:
        return None
    if witness.get("encoding") != "gzip+base64+utf8":
        return None
    expected = str(expected_sha256 or "").strip().lower()
    declared = str(witness.get("sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or declared != expected:
        return None
    encoded = witness.get("content_gzip_b64")
    if (
        not isinstance(encoded, str)
        or not encoded
        or len(encoded) > MAX_PAGE_DOCUMENT_WITNESS_BASE64_CHARS
    ):
        return None
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError, TypeError):
        return None
    if not compressed or len(compressed) > MAX_PAGE_DOCUMENT_WITNESS_COMPRESSED_BYTES:
        return None
    decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(compressed, MAX_PAGE_DOCUMENT_WITNESS_BYTES + 1)
        if decoder.unconsumed_tail or len(raw) > MAX_PAGE_DOCUMENT_WITNESS_BYTES:
            return None
        raw += decoder.flush()
    except zlib.error:
        return None
    try:
        declared_raw_size = int(witness.get("raw_size_bytes"))
        declared_compressed_size = int(witness.get("compressed_size_bytes"))
    except (TypeError, ValueError):
        return None
    if (
        not decoder.eof
        or decoder.unused_data
        or len(raw) > MAX_PAGE_DOCUMENT_WITNESS_BYTES
        or declared_raw_size != len(raw)
        or declared_compressed_size != len(compressed)
        or hashlib.sha256(raw).hexdigest() != expected
    ):
        return None
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return raw


def make_evidence(
    *,
    field: str,
    value: str | None,
    epistemic_class: EpistemicClass,
    source_type: str,
    source_url: str | None = None,
    source_id: str | None = None,
    document_id: str | None = None,
    document_sha256: str | None = None,
    page: int | None = None,
    section: str | None = None,
    evidence_snippet: str | None = None,
    observed_at: str | None = None,
    published_at: str | None = None,
    extraction_method: str | None = None,
    contract_id: str | None = None,
    process_id: str | None = None,
    aspects: list[FieldAspect] | None = None,
    extra: dict | None = None,
) -> FieldEvidence:
    resolved_observed_at = observed_at or now_iso()
    eid = stable_id(
        field,
        value or "",
        epistemic_class.value,
        source_type,
        source_url or "",
        source_id or "",
        document_id or "",
        document_sha256 or "",
        str(page or ""),
        section or "",
        evidence_snippet or "",
        observed_at or "",
        published_at or "",
        extraction_method or "",
    )
    if epistemic_class == EpistemicClass.OBSERVED and not (source_type and (source_url or document_id or source_id)):
        raise ValueError("OBSERVED evidence requires a source (url, document or source_id)")
    return FieldEvidence(
        evidence_id=eid,
        field=field,
        value=value,
        epistemic_class=epistemic_class,
        source_type=source_type,
        source_url=source_url,
        source_id=source_id,
        document_id=document_id,
        document_sha256=document_sha256,
        page=page,
        section=section,
        evidence_snippet=evidence_snippet,
        observed_at=resolved_observed_at,
        published_at=published_at,
        extraction_method=extraction_method,
        extractor_version="dui.extract.v2",
        contract_id=contract_id,
        process_id=process_id,
        aspects=aspects or [],
        extra=extra or {},
    )


def assert_not_promoted_to_observed(evidence: FieldEvidence) -> None:
    """Guardrail: inferred/technical signals must not be labeled OBSERVED."""
    if evidence.epistemic_class == EpistemicClass.OBSERVED:
        method = (evidence.extraction_method or "").lower()
        if any(tok in method for tok in ("infer", "pattern", "guess", "mx-only", "constructed")):
            raise ValueError(
                f"refusing OBSERVED label for inferred method {evidence.extraction_method!r}"
            )
    for aspect in evidence.aspects:
        if (
            aspect.epistemic_class == EpistemicClass.OBSERVED
            and aspect.method
            and any(tok in aspect.method.lower() for tok in ("infer", "pattern", "guess"))
        ):
            raise ValueError(f"aspect {aspect.field} cannot be OBSERVED via {aspect.method}")
